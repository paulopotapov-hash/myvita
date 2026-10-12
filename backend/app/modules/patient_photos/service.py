"""Patient profile photos: upload, the doctor's approval, removal, and serving the image.

Rules (see app/models/patient_photo.py for the data and the retention decision):
- The patient uploads their own photo: it is normalised first (images.py), stored in the
  private document storage, and becomes their one `pending` photo. A previous pending
  photo, and a previous rejection notice, are deleted.
- Only a DOCTOR with an active care assignment to the patient approves or rejects it.
  Approving deletes the previous approved photo; rejecting deletes the image and keeps
  only the reason, which the patient sees until their next upload.
- The patient may remove their pending or approved photo; it is deleted.
- The image is served to the patient (their pending and approved photos), to staff who
  may open the patient's file (`VIEW_PATIENT`; approved photo only) and to the approving
  doctors (pending photo too). Anyone else gets the same 403/404 as for the patient file.

Deleting a photo deletes its row in the same transaction that queues its file in
`storage_deletions`; the file is removed right after the commit, and if that fails the
background job (app/jobs) retries until it is gone.
"""

import io
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.clinical_access import ClinicalAction, clinical_access, staff_profile
from app.core.config import settings
from app.models import (
    ClinicalCareAssignment,
    Patient,
    PatientPhoto,
    PatientPhotoStatus,
    Staff,
    StaffRole,
    StorageDeletion,
    User,
    UserRole,
)
from app.modules.documents.storage import LocalDocumentStorage
from app.modules.notifications.events import NotificationEvent, NotificationTarget, TargetType, notify
from app.modules.patient_photos.images import PhotoRejected, normalise

logger = logging.getLogger("myvita.patient_photos")
_NOT_FOUND = "Foto não encontrada."
NOT_PENDING = "Esta foto já não está à espera de aprovação."
DOCTORS_ONLY = "Só o médico associado ao paciente aprova ou rejeita a foto."


def storage() -> LocalDocumentStorage:
    return LocalDocumentStorage(settings.DOCUMENT_STORAGE_DIR)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


@dataclass(frozen=True)
class Deleted:
    """A photo deleted by an action, for the caller's audit (identifiers only)."""

    photo_id: uuid.UUID
    patient_id: uuid.UUID
    cause: str  # "replaced", "superseded", "rejected", "removed"


@dataclass
class Outcome:
    photo: PatientPhoto | None
    deleted: list[Deleted]
    keys: list[str]  # files to remove after the commit


def _own_patient(db: Session, user: User, *, lock: bool = False) -> Patient:
    if user.role != UserRole.PATIENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Só o próprio paciente gere a sua foto.")
    query = db.query(Patient).filter(Patient.user_id == user.id, Patient.clinic_id == user.clinic_id)
    patient = (query.with_for_update() if lock else query).first()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Perfil de paciente não encontrado.")
    return patient


def approving_doctors(db: Session, patient: Patient) -> list[Staff]:
    return (
        db.query(Staff)
        .join(ClinicalCareAssignment, ClinicalCareAssignment.staff_id == Staff.id)
        .filter(
            ClinicalCareAssignment.patient_id == patient.id,
            ClinicalCareAssignment.clinic_id == patient.clinic_id,
            ClinicalCareAssignment.active.is_(True),
            Staff.staff_role == StaffRole.DOCTOR,
        )
        .all()
    )


def approver(db: Session, user: User, patient_id: uuid.UUID) -> Staff | None:
    """The caller as an approving doctor of this patient, or None."""
    staff = staff_profile(db, user)
    if staff is None or staff.staff_role != StaffRole.DOCTOR:
        return None
    assigned = (
        db.query(ClinicalCareAssignment.id)
        .filter(
            ClinicalCareAssignment.patient_id == patient_id,
            ClinicalCareAssignment.staff_id == staff.id,
            ClinicalCareAssignment.clinic_id == user.clinic_id,
            ClinicalCareAssignment.active.is_(True),
        )
        .first()
    )
    return staff if assigned is not None else None


def _photos(db: Session, patient_id: uuid.UUID) -> dict[PatientPhotoStatus, PatientPhoto]:
    return {photo.status: photo for photo in db.query(PatientPhoto).filter(PatientPhoto.patient_id == patient_id)}


def _delete(db: Session, outcome: Outcome, photo: PatientPhoto, cause: str) -> None:
    """Delete the row now; queue its file (if any) in the same transaction."""
    if photo.storage_key is not None:
        db.add(StorageDeletion(storage_key=photo.storage_key))
        outcome.keys.append(photo.storage_key)
    if photo.status != PatientPhotoStatus.REJECTED:
        outcome.deleted.append(Deleted(photo_id=photo.id, patient_id=photo.patient_id, cause=cause))
    db.delete(photo)
    db.flush()


def remove_files(db: Session, keys: list[str]) -> int:
    """Remove queued files; a failure stays queued for the background job. Returns how many went."""
    store = storage()
    done = 0
    for key in keys:
        deletion = db.get(StorageDeletion, key)
        if deletion is None or deletion.deleted_at is not None:
            continue
        deletion.attempts += 1
        deletion.last_attempt_at = datetime.now(UTC)
        try:
            store.delete(key)
        except OSError as exc:
            # Never the key or a path in the log: the error class is enough to investigate.
            logger.warning("patient_photo_file_delete_failed error=%s", type(exc).__name__)
        else:
            deletion.deleted_at = datetime.now(UTC)
            done += 1
        db.commit()
    return done


def retry_file_deletions(db: Session, limit: int = 200) -> int:
    """Background job: remove files whose deletion failed or was interrupted."""
    keys = [
        key
        for (key,) in db.query(StorageDeletion.storage_key)
        .filter(StorageDeletion.deleted_at.is_(None))
        .order_by(StorageDeletion.requested_at)
        .limit(limit)
    ]
    return remove_files(db, keys)


def upload(db: Session, user: User, data: bytes) -> Outcome:
    patient = _own_patient(db, user, lock=True)  # one upload at a time per patient
    try:
        jpeg = normalise(data)
    except PhotoRejected as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    store = storage()
    key = store.new_key()
    store.save(key, io.BytesIO(jpeg))
    outcome = Outcome(photo=None, deleted=[], keys=[])
    try:
        current = _photos(db, patient.id)
        if PatientPhotoStatus.PENDING in current:
            _delete(db, outcome, current[PatientPhotoStatus.PENDING], "replaced")
        if PatientPhotoStatus.REJECTED in current:
            _delete(db, outcome, current[PatientPhotoStatus.REJECTED], "replaced")
        photo = PatientPhoto(
            clinic_id=patient.clinic_id,
            patient_id=patient.id,
            status=PatientPhotoStatus.PENDING,
            storage_key=key,
            uploaded_by_user_id=user.id,
        )
        db.add(photo)
        db.flush()
        for doctor in approving_doctors(db, patient):
            notify(
                db,
                NotificationEvent.PATIENT_PHOTO_SUBMITTED,
                clinic_id=patient.clinic_id,
                recipient_user_id=doctor.user_id,
                target=NotificationTarget(TargetType.PATIENT, patient.id),
                dedupe_key=str(photo.id),
            )
        db.commit()
    except BaseException:
        db.rollback()
        store.delete(key)  # nothing refers to it
        raise
    db.refresh(photo)
    outcome.photo = photo
    remove_files(db, outcome.keys)
    return outcome


def _locked_photo(db: Session, user: User, photo_id: uuid.UUID) -> PatientPhoto:
    photo = (
        db.query(PatientPhoto)
        .filter(PatientPhoto.id == photo_id, PatientPhoto.clinic_id == user.clinic_id)
        .with_for_update()
        .first()
    )
    if photo is None:
        raise _not_found()
    return photo


def _decide(db: Session, user: User, photo_id: uuid.UUID) -> tuple[PatientPhoto, Staff, Patient]:
    photo = _locked_photo(db, user, photo_id)
    doctor = approver(db, user, photo.patient_id)
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DOCTORS_ONLY)
    if photo.status != PatientPhotoStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NOT_PENDING)
    patient = db.get(Patient, photo.patient_id)
    assert patient is not None
    return photo, doctor, patient


def approve(db: Session, user: User, photo_id: uuid.UUID) -> Outcome:
    photo, doctor, patient = _decide(db, user, photo_id)
    outcome = Outcome(photo=photo, deleted=[], keys=[])
    previous = _photos(db, patient.id).get(PatientPhotoStatus.APPROVED)
    if previous is not None:
        _delete(db, outcome, previous, "superseded")
    photo.status = PatientPhotoStatus.APPROVED
    photo.decided_by_staff_id, photo.decided_at = doctor.id, datetime.now(UTC)
    notify(
        db,
        NotificationEvent.PATIENT_PHOTO_APPROVED,
        clinic_id=patient.clinic_id,
        recipient_user_id=patient.user_id,
        target=NotificationTarget(TargetType.PATIENT, patient.id),
        dedupe_key=str(photo.id),
    )
    db.commit()
    db.refresh(photo)
    remove_files(db, outcome.keys)
    return outcome


def reject(db: Session, user: User, photo_id: uuid.UUID, reason: str) -> Outcome:
    photo, doctor, patient = _decide(db, user, photo_id)
    outcome = Outcome(photo=photo, deleted=[], keys=[])
    assert photo.storage_key is not None
    db.add(StorageDeletion(storage_key=photo.storage_key))
    outcome.keys.append(photo.storage_key)
    outcome.deleted.append(Deleted(photo_id=photo.id, patient_id=patient.id, cause="rejected"))
    photo.status = PatientPhotoStatus.REJECTED
    photo.storage_key = None
    photo.rejection_reason = reason
    photo.decided_by_staff_id, photo.decided_at = doctor.id, datetime.now(UTC)
    notify(
        db,
        NotificationEvent.PATIENT_PHOTO_REJECTED,
        clinic_id=patient.clinic_id,
        recipient_user_id=patient.user_id,
        target=NotificationTarget(TargetType.PATIENT, patient.id),
        dedupe_key=str(photo.id),
    )
    db.commit()
    db.refresh(photo)
    remove_files(db, outcome.keys)
    return outcome


def remove(db: Session, user: User, photo_id: uuid.UUID) -> Outcome:
    patient = _own_patient(db, user, lock=True)
    photo = (
        db.query(PatientPhoto)
        .filter(PatientPhoto.id == photo_id, PatientPhoto.patient_id == patient.id)
        .with_for_update()
        .first()
    )
    if photo is None or photo.status == PatientPhotoStatus.REJECTED:
        raise _not_found()
    outcome = Outcome(photo=None, deleted=[], keys=[])
    _delete(db, outcome, photo, "removed")
    db.commit()
    remove_files(db, outcome.keys)
    return outcome


def image(db: Session, user: User, photo_id: uuid.UUID) -> bytes:
    """The stored JPEG, if the caller may see this photo (403/404 otherwise)."""
    photo = db.query(PatientPhoto).filter(PatientPhoto.id == photo_id, PatientPhoto.clinic_id == user.clinic_id).first()
    if photo is None or photo.storage_key is None:
        raise _not_found()
    if user.role == UserRole.PATIENT:
        if _own_patient(db, user).id != photo.patient_id:
            raise _not_found()
    else:
        clinical_access(db, photo.patient_id, user, ClinicalAction.VIEW_PATIENT)
        if photo.status != PatientPhotoStatus.APPROVED and approver(db, user, photo.patient_id) is None:
            raise _not_found()
    with storage().open(photo.storage_key) as handle:
        return handle.read()


def mine(db: Session, user: User) -> dict[PatientPhotoStatus, PatientPhoto]:
    return _photos(db, _own_patient(db, user).id)


def for_staff(db: Session, user: User, patient_id: uuid.UUID) -> tuple[PatientPhoto | None, PatientPhoto | None, bool]:
    """(approved photo, pending photo if the caller approves, whether the caller approves)."""
    clinical_access(db, patient_id, user, ClinicalAction.VIEW_PATIENT)
    photos = _photos(db, patient_id)
    reviews = approver(db, user, patient_id) is not None
    return photos.get(PatientPhotoStatus.APPROVED), photos.get(PatientPhotoStatus.PENDING) if reviews else None, reviews


def pending_count(db: Session, user: User) -> int:
    """Pending photos this doctor may approve (for the staff inbox); 0 for anyone else."""
    staff = staff_profile(db, user)
    if staff is None or staff.staff_role != StaffRole.DOCTOR:
        return 0
    assigned = db.query(ClinicalCareAssignment.patient_id).filter(
        ClinicalCareAssignment.staff_id == staff.id,
        ClinicalCareAssignment.clinic_id == user.clinic_id,
        ClinicalCareAssignment.active.is_(True),
    )
    return (
        db.query(PatientPhoto)
        .filter(PatientPhoto.status == PatientPhotoStatus.PENDING, PatientPhoto.patient_id.in_(assigned))
        .count()
    )

