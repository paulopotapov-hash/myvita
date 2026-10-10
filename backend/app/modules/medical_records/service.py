"""Medical records (clinical notes).

P2.5 visibility policy (see MedicalRecordVisibility):

- A new record is INTERNAL to the care team unless its author explicitly shares
  it on creation.
- Only a professional with EDIT_MEDICAL_RECORDS on an active care assignment
  can share or unshare, through dedicated operations (`share_record`,
  `unshare_record`). A content edit never changes visibility.
- Every visibility change bumps the version and writes a revision naming the
  professional, so the history of what was shared, by whom and when is kept;
  the router audits it as MEDICAL_RECORD_SHARED / MEDICAL_RECORD_UNSHARED.
- A patient reads only SHARED and LEGACY_SHARED records of their own file. Any
  other record answers exactly like a missing one (404), and the revision
  history is staff-only. Checks run on every request, so unsharing (or the end
  of a care assignment) takes effect immediately, whatever links exist.
- Making a record newly readable by the patient notifies them, in the same
  transaction, with generic text and a deep link that is re-checked on open.
  Confirming a legacy record (already readable) does not notify.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.clinical_access import ClinicalAction, clinical_access, clinical_staff
from app.models import (
    PATIENT_READABLE_VISIBILITIES,
    MedicalRecord,
    MedicalRecordRevision,
    MedicalRecordVisibility,
    Patient,
    Staff,
    User,
    UserRole,
)
from app.modules.medical_records.schemas import MedicalRecordCreateRequest, MedicalRecordUpdateRequest
from app.modules.notifications.events import NotificationEvent, NotificationTarget, TargetType, notify


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registo clínico não encontrado.")


def _stale_version() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="O registo clínico foi alterado por outro utilizador. Recarregue antes de guardar.",
    )


def list_records(
    db: Session, patient_id: uuid.UUID, user: User, *, offset: int = 0, limit: int = 50
) -> tuple[list[MedicalRecord], int]:
    clinical_access(db, patient_id, user, ClinicalAction.VIEW_MEDICAL_RECORDS)
    query = db.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id, MedicalRecord.clinic_id == user.clinic_id
    )
    if user.role == UserRole.PATIENT:
        query = query.filter(MedicalRecord.patient_visibility.in_(PATIENT_READABLE_VISIBILITIES))
    total = query.count()
    rows = (
        query.order_by(MedicalRecord.created_at.desc(), MedicalRecord.id.desc()).offset(offset).limit(limit).all()
    )
    return rows, total


def get_record(db: Session, record_id: uuid.UUID, user: User) -> MedicalRecord:
    record = (
        db.query(MedicalRecord)
        .filter(MedicalRecord.id == record_id, MedicalRecord.clinic_id == user.clinic_id)
        .first()
    )
    if record is None:
        raise _not_found()
    clinical_access(db, record.patient_id, user, ClinicalAction.VIEW_MEDICAL_RECORDS)
    if user.role == UserRole.PATIENT and not record.patient_visibility.patient_can_read:
        raise _not_found()
    return record


def list_revisions(db: Session, record_id: uuid.UUID, user: User) -> tuple[MedicalRecord, list[MedicalRecordRevision]]:
    """Edit history is internal to the care team: a patient gets the same 404 as for a missing record."""
    record = get_record(db, record_id, user)
    if user.role == UserRole.PATIENT:
        raise _not_found()
    rows = (
        db.query(MedicalRecordRevision)
        .filter(MedicalRecordRevision.record_id == record.id)
        .order_by(MedicalRecordRevision.version)
        .all()
    )
    return record, rows


def _snapshot(db: Session, record: MedicalRecord, staff: Staff) -> None:
    db.add(
        MedicalRecordRevision(
            record_id=record.id,
            editor_staff_id=staff.id,
            version=record.version,
            title=record.title,
            content=record.content,
            patient_visibility=record.patient_visibility,
        )
    )


def _notify_patient_of_share(db: Session, record: MedicalRecord, patient: Patient) -> None:
    """Recipient comes from the record's own patient row, never from the request."""
    notify(
        db,
        NotificationEvent.MEDICAL_RECORD_SHARED,
        clinic_id=record.clinic_id,
        recipient_user_id=patient.user_id,
        target=NotificationTarget(TargetType.MEDICAL_RECORD, record.id),
        # One notification per sharing event: re-sharing after an unshare is a new
        # event (new version); a retried request of the same event is not.
        dedupe_key=f"{record.id}:v{record.version}",
    )


def create_record(
    db: Session, patient_id: uuid.UUID, payload: MedicalRecordCreateRequest, user: User
) -> MedicalRecord:
    patient = clinical_access(db, patient_id, user, ClinicalAction.EDIT_MEDICAL_RECORDS)
    staff = clinical_staff(db, user, patient_id, ClinicalAction.EDIT_MEDICAL_RECORDS)
    record = MedicalRecord(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        author_staff_id=staff.id,
        title=payload.title,
        content=payload.content,
        patient_visibility=MedicalRecordVisibility.INTERNAL,
        version=1,
    )
    if payload.share_with_patient:
        record.patient_visibility = MedicalRecordVisibility.SHARED
        record.visibility_changed_at = datetime.now(UTC)
        record.visibility_changed_by_staff_id = staff.id
    db.add(record)
    db.flush()
    _snapshot(db, record, staff)
    if payload.share_with_patient:
        _notify_patient_of_share(db, record, patient)
    db.commit()
    db.refresh(record)
    return record


def _locked_for_edit(
    db: Session, record_id: uuid.UUID, user: User, expected_version: int | None
) -> tuple[MedicalRecord, Staff, Patient]:
    record = get_record(db, record_id, user)
    patient = clinical_access(db, record.patient_id, user, ClinicalAction.EDIT_MEDICAL_RECORDS)
    staff = clinical_staff(db, user, record.patient_id, ClinicalAction.EDIT_MEDICAL_RECORDS)
    # Lock + reload so concurrent edits and visibility changes get distinct, gapless versions.
    db.refresh(record, with_for_update=True)
    # Optimistic concurrency (feature/messages-backend contract): the client
    # states the version it worked on; a stale request is refused, never merged.
    if expected_version is not None and record.version != expected_version:
        db.rollback()
        raise _stale_version()
    return record, staff, patient


def update_record(
    db: Session, record_id: uuid.UUID, payload: MedicalRecordUpdateRequest, user: User
) -> MedicalRecord:
    """Content edit. Visibility is kept as is (an edit of a shared record stays visible to the patient)."""
    record, staff, _patient = _locked_for_edit(db, record_id, user, payload.expected_version)
    record.version += 1
    record.title = payload.title
    record.content = payload.content
    _snapshot(db, record, staff)
    db.commit()
    db.refresh(record)
    return record


def share_record(
    db: Session, record_id: uuid.UUID, expected_version: int, user: User
) -> tuple[MedicalRecord, MedicalRecordVisibility | None]:
    """Explicitly share the reviewed version with the patient.

    Returns the record and its previous visibility, or None when nothing changed
    (already explicitly shared: a repeated request is not a new sharing event).
    """
    record, staff, patient = _locked_for_edit(db, record_id, user, None)
    if record.patient_visibility == MedicalRecordVisibility.SHARED:
        db.rollback()
        return record, None
    if record.version != expected_version:
        db.rollback()
        raise _stale_version()
    previous = record.patient_visibility
    record.patient_visibility = MedicalRecordVisibility.SHARED
    record.visibility_changed_at = datetime.now(UTC)
    record.visibility_changed_by_staff_id = staff.id
    record.version += 1
    _snapshot(db, record, staff)
    # Only a record the patient could not read yet is news to them: confirming a
    # legacy record records the decision without notifying.
    if not previous.patient_can_read:
        _notify_patient_of_share(db, record, patient)
    db.commit()
    db.refresh(record)
    return record, previous


def unshare_record(
    db: Session, record_id: uuid.UUID, user: User
) -> tuple[MedicalRecord, MedicalRecordVisibility | None]:
    """Make the record internal again. Patient access ends with this commit.

    Withdrawing access only reduces exposure, so it is never refused for a stale
    version: a concurrent edit must not keep a record visible.
    """
    record, staff, _patient = _locked_for_edit(db, record_id, user, None)
    if record.patient_visibility == MedicalRecordVisibility.INTERNAL:
        db.rollback()
        return record, None
    previous = record.patient_visibility
    record.patient_visibility = MedicalRecordVisibility.INTERNAL
    record.visibility_changed_at = datetime.now(UTC)
    record.visibility_changed_by_staff_id = staff.id
    record.version += 1
    _snapshot(db, record, staff)
    db.commit()
    db.refresh(record)
    return record, previous
