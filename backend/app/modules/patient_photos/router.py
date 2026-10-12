"""Patient profile photos (see service.py). Every response that carries an image is
private: no caching, no sniffing, inline, and never a file name from the upload."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, client_ip, record_audit_event
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, AuditResult, PatientPhoto, PatientPhotoStatus, User
from app.modules.patient_photos import service
from app.modules.patient_photos.images import MAX_BYTES, TOO_LARGE
from app.modules.patient_photos.schemas import (
    PHOTO_REQUIREMENTS,
    MyPhotoOut,
    PatientPhotoStaffOut,
    PendingCount,
    PhotoRef,
    PhotoRejectIn,
    PhotoRejection,
)

router = APIRouter()
_CHUNK = 64 * 1024


def _audit(request: Request, user: User, action: AuditAction, photo_id: uuid.UUID, patient_id: uuid.UUID, operation: str | None = None) -> None:
    # Identifiers only: never the image, a file name or the rejection reason.
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="patient_photo",
        resource_id=photo_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"patient_id": str(patient_id), **({"operation": operation} if operation else {})},
    )


def _audit_deleted(request: Request, user: User, outcome: service.Outcome) -> None:
    for deleted in outcome.deleted:
        _audit(request, user, AuditAction.PATIENT_PHOTO_DELETED, deleted.photo_id, deleted.patient_id, deleted.cause)


def _ref(photo: PatientPhoto | None) -> PhotoRef | None:
    return PhotoRef(id=photo.id, created_at=photo.created_at) if photo is not None else None


def _mine(db: Session, user: User) -> MyPhotoOut:
    photos = service.mine(db, user)
    rejected = photos.get(PatientPhotoStatus.REJECTED)
    return MyPhotoOut(
        approved=_ref(photos.get(PatientPhotoStatus.APPROVED)),
        pending=_ref(photos.get(PatientPhotoStatus.PENDING)),
        rejected=PhotoRejection(reason=rejected.rejection_reason or "", rejected_at=rejected.decided_at) if rejected else None,
        requirements=list(PHOTO_REQUIREMENTS),
    )


@router.get("/mine", response_model=MyPhotoOut)
def my_photo(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> MyPhotoOut:
    return _mine(db, user)


@router.post("", response_model=MyPhotoOut, status_code=201)
def upload(
    request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> MyPhotoOut:
    """The patient's new photo (JPEG or PNG, up to 5 MB): normalised, then pending approval."""
    data = bytearray()
    while chunk := file.file.read(_CHUNK):
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=TOO_LARGE)
    outcome = service.upload(db, user, bytes(data))
    assert outcome.photo is not None
    _audit(request, user, AuditAction.PATIENT_PHOTO_UPLOADED, outcome.photo.id, outcome.photo.patient_id)
    _audit_deleted(request, user, outcome)
    return _mine(db, user)


@router.post("/{photo_id}/remove", response_model=MyPhotoOut)
def remove(photo_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> MyPhotoOut:
    """The patient removes their pending or approved photo: deleted at once, file and record."""
    outcome = service.remove(db, user, photo_id)
    for deleted in outcome.deleted:
        _audit(request, user, AuditAction.PATIENT_PHOTO_REMOVED, deleted.photo_id, deleted.patient_id)
    _audit_deleted(request, user, outcome)
    return _mine(db, user)


@router.post("/{photo_id}/approve", response_model=PatientPhotoStaffOut)
def approve(photo_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> PatientPhotoStaffOut:
    with audit_denials(request, user, "patient_photo", photo_id):
        outcome = service.approve(db, user, photo_id)
    assert outcome.photo is not None
    _audit(request, user, AuditAction.PATIENT_PHOTO_APPROVED, outcome.photo.id, outcome.photo.patient_id)
    _audit_deleted(request, user, outcome)
    return _staff(db, user, outcome.photo.patient_id)


@router.post("/{photo_id}/reject", response_model=PatientPhotoStaffOut)
def reject(
    photo_id: uuid.UUID, payload: PhotoRejectIn, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PatientPhotoStaffOut:
    """Reject with a reason the patient reads; the image is deleted at once."""
    with audit_denials(request, user, "patient_photo", photo_id):
        outcome = service.reject(db, user, photo_id, payload.reason)
    assert outcome.photo is not None
    _audit(request, user, AuditAction.PATIENT_PHOTO_REJECTED, outcome.photo.id, outcome.photo.patient_id)
    _audit_deleted(request, user, outcome)
    return _staff(db, user, outcome.photo.patient_id)


def _staff(db: Session, user: User, patient_id: uuid.UUID) -> PatientPhotoStaffOut:
    approved, pending, can_review = service.for_staff(db, user, patient_id)
    return PatientPhotoStaffOut(approved=_ref(approved), pending=_ref(pending), can_review=can_review)


@router.get("/patients/{patient_id}", response_model=PatientPhotoStaffOut)
def patient_photo(
    patient_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> PatientPhotoStaffOut:
    with audit_denials(request, user, "patient_photo", patient_id):
        return _staff(db, user, patient_id)


@router.get("/pending-count", response_model=PendingCount)
def pending(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> PendingCount:
    """Pending photos the calling doctor may approve (0 for anyone else)."""
    return PendingCount(count=service.pending_count(db, user))


@router.get("/{photo_id}/image")
def photo_image(photo_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    with audit_denials(request, user, "patient_photo", photo_id):
        content = service.image(db, user, photo_id)
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'inline; filename="foto.jpg"',
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )
