"""Tenant-scoped clinical history. Consent events are append-only."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.pagination import DEFAULT_PAGE_SIZE, Limit, Offset
from app.core.security import ClinicalPermission, require_permission
from app.models import (
    AuditAction,
    AuditResult,
    Consent,
    MedicalRecord,
    MedicalRecordRevision,
    Notification,
    Patient,
    User,
)
from app.modules.clinical.schemas import (
    ConsentCreate,
    ConsentPublic,
    NotificationPublic,
    RecordCreate,
    RecordPublic,
    RecordRevisionPublic,
    RecordUpdate,
)

router = APIRouter()
_record_read = require_permission(ClinicalPermission.MEDICAL_RECORD_READ)
_record_write = require_permission(ClinicalPermission.MEDICAL_RECORD_WRITE)
_consent_read = require_permission(ClinicalPermission.CONSENT_READ)
_consent_record = require_permission(ClinicalPermission.CONSENT_RECORD)
_notification_read = require_permission(ClinicalPermission.NOTIFICATION_READ)


def _patient(db: Session, patient_id: uuid.UUID, user: User, *, write: bool = False) -> Patient:
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.clinic_id == user.clinic_id).first()
    if patient is None or (user.role.value == "patient" and (write or patient.user_id != user.id)):
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")
    return patient


def _item[T: MedicalRecord | Consent](
    db: Session, model: type[T], item_id: uuid.UUID, user: User
) -> T:
    item = db.query(model).filter(model.id == item_id, model.clinic_id == user.clinic_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Recurso não encontrado.")
    return item


def _audit(request: Request, user: User, action: AuditAction, resource: str, resource_id: uuid.UUID) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type=resource,
        resource_id=resource_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/medical-records", response_model=RecordPublic, status_code=201)
def create_record(
    payload: RecordCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_record_write),
) -> MedicalRecord:
    _patient(db, payload.patient_id, user, write=True)
    item = MedicalRecord(**payload.model_dump(), clinic_id=user.clinic_id, author_user_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.MEDICAL_RECORD_CREATED, "medical_record", item.id)
    return item


@router.get("/patients/{patient_id}/medical-records", response_model=list[RecordPublic])
def list_records(
    patient_id: uuid.UUID,
    request: Request,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
    db: Session = Depends(get_db),
    user: User = Depends(_record_read),
) -> list[MedicalRecord]:
    _patient(db, patient_id, user)
    items = (
        db.query(MedicalRecord)
        .filter(MedicalRecord.clinic_id == user.clinic_id, MedicalRecord.patient_id == patient_id)
        .order_by(MedicalRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    _audit(request, user, AuditAction.MEDICAL_RECORD_VIEWED, "patient", patient_id)
    return items


@router.patch("/medical-records/{item_id}", response_model=RecordPublic)
def update_record(
    item_id: uuid.UUID,
    payload: RecordUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_record_write),
) -> MedicalRecord:
    item = _item(db, MedicalRecord, item_id, user)
    values = payload.model_dump(exclude_unset=True)
    if any(value is None for value in values.values()):
        raise HTTPException(status_code=422, detail="Título e conteúdo não podem ser nulos.")
    db.add(
        MedicalRecordRevision(
            record_id=item.id,
            clinic_id=item.clinic_id,
            patient_id=item.patient_id,
            editor_user_id=user.id,
            version=item.version,
            title=item.title,
            content=item.content,
        )
    )
    for key, value in values.items():
        setattr(item, key, value)
    item.version += 1
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.MEDICAL_RECORD_UPDATED, "medical_record", item.id)
    return item


@router.get("/medical-records/{item_id}/revisions", response_model=list[RecordRevisionPublic])
def list_record_revisions(
    item_id: uuid.UUID,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
    db: Session = Depends(get_db),
    user: User = Depends(_record_read),
) -> list[MedicalRecordRevision]:
    item = _item(db, MedicalRecord, item_id, user)
    _patient(db, item.patient_id, user)
    return (
        db.query(MedicalRecordRevision)
        .filter(MedicalRecordRevision.record_id == item.id, MedicalRecordRevision.clinic_id == user.clinic_id)
        .order_by(MedicalRecordRevision.version.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post("/consents", response_model=ConsentPublic, status_code=201)
def create_consent(
    payload: ConsentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_consent_record),
) -> Consent:
    patient = _patient(db, payload.patient_id, user)
    if user.role.value == "patient" and patient.user_id != user.id:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")
    item = Consent(**payload.model_dump(), clinic_id=user.clinic_id, recorded_by_user_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.CONSENT_RECORDED, "consent", item.id)
    return item


@router.get("/patients/{patient_id}/consents", response_model=list[ConsentPublic])
def list_consents(
    patient_id: uuid.UUID,
    request: Request,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
    db: Session = Depends(get_db),
    user: User = Depends(_consent_read),
) -> list[Consent]:
    _patient(db, patient_id, user)
    items = (
        db.query(Consent)
        .filter(Consent.clinic_id == user.clinic_id, Consent.patient_id == patient_id)
        .order_by(Consent.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    _audit(request, user, AuditAction.CONSENT_VIEWED, "patient", patient_id)
    return items


@router.get("/notifications", response_model=list[NotificationPublic])
def list_notifications(
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
    db: Session = Depends(get_db),
    user: User = Depends(_notification_read),
) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.recipient_user_id == user.id, Notification.clinic_id == user.clinic_id)
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.patch("/notifications/{item_id}/read", response_model=NotificationPublic)
def read_notification(
    item_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(_notification_read)
) -> Notification:
    item = (
        db.query(Notification)
        .filter(
            Notification.id == item_id,
            Notification.recipient_user_id == user.id,
            Notification.clinic_id == user.clinic_id,
        )
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Notificação não encontrada.")
    item.is_read = True
    db.commit()
    db.refresh(item)
    return item
