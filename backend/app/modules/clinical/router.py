"""Tenant-scoped clinical history. Consent events are append-only."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models import (
    AuditAction,
    AuditResult,
    Consent,
    MedicalRecord,
    Medication,
    Notification,
    Patient,
    User,
    UserRole,
)
from app.modules.clinical.schemas import (
    ConsentCreate,
    ConsentPublic,
    MedicationCreate,
    MedicationPublic,
    MedicationUpdate,
    NotificationPublic,
    RecordCreate,
    RecordPublic,
    RecordUpdate,
)

router = APIRouter()
_staff = require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN)


def _patient(db: Session, patient_id: uuid.UUID, user: User, *, write: bool = False) -> Patient:
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.clinic_id == user.clinic_id).first()
    if patient is None or (user.role == UserRole.PATIENT and (write or patient.user_id != user.id)):
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")
    return patient


def _item[T: MedicalRecord | Medication | Consent](db: Session, model: type[T], item_id: uuid.UUID, user: User) -> T:
    item = db.query(model).filter(model.id == item_id, model.clinic_id == user.clinic_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Recurso não encontrado.")
    return item


def _audit(request: Request, user: User, action: AuditAction, resource: str, resource_id: uuid.UUID) -> None:
    record_audit_event(
        action=action, result=AuditResult.SUCCESS, clinic_id=user.clinic_id,
        actor_user_id=user.id, actor_email=user.email, resource_type=resource,
        resource_id=resource_id, ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/medical-records", response_model=RecordPublic, status_code=201)
def create_record(payload: RecordCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(_staff)) -> MedicalRecord:
    _patient(db, payload.patient_id, user, write=True)
    item = MedicalRecord(**payload.model_dump(), clinic_id=user.clinic_id, author_user_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.MEDICAL_RECORD_CREATED, "medical_record", item.id)
    return item


@router.get("/patients/{patient_id}/medical-records", response_model=list[RecordPublic])
def list_records(patient_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[MedicalRecord]:
    _patient(db, patient_id, user)
    items = db.query(MedicalRecord).filter(MedicalRecord.clinic_id == user.clinic_id, MedicalRecord.patient_id == patient_id).order_by(MedicalRecord.created_at.desc()).all()
    _audit(request, user, AuditAction.MEDICAL_RECORD_VIEWED, "patient", patient_id)
    return items


@router.patch("/medical-records/{item_id}", response_model=RecordPublic)
def update_record(item_id: uuid.UUID, payload: RecordUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(_staff)) -> MedicalRecord:
    item = _item(db, MedicalRecord, item_id, user)
    if item.author_user_id != user.id and user.role != UserRole.CLINIC_ADMIN:
        raise HTTPException(status_code=403, detail="Sem permissão para alterar este registo.")
    values = payload.model_dump(exclude_unset=True)
    if any(value is None for value in values.values()):
        raise HTTPException(status_code=422, detail="Título e conteúdo não podem ser nulos.")
    for key, value in values.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.MEDICAL_RECORD_UPDATED, "medical_record", item.id)
    return item


@router.post("/medications", response_model=MedicationPublic, status_code=201)
def create_medication(payload: MedicationCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(_staff)) -> Medication:
    _patient(db, payload.patient_id, user, write=True)
    item = Medication(**payload.model_dump(), clinic_id=user.clinic_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.MEDICATION_CREATED, "medication", item.id)
    return item


@router.get("/patients/{patient_id}/medications", response_model=list[MedicationPublic])
def list_medications(patient_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Medication]:
    _patient(db, patient_id, user)
    items = db.query(Medication).filter(Medication.clinic_id == user.clinic_id, Medication.patient_id == patient_id).order_by(Medication.created_at.desc()).all()
    _audit(request, user, AuditAction.MEDICATION_VIEWED, "patient", patient_id)
    return items


@router.patch("/medications/{item_id}", response_model=MedicationPublic)
def update_medication(item_id: uuid.UUID, payload: MedicationUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(_staff)) -> Medication:
    item = _item(db, Medication, item_id, user)
    values = payload.model_dump(exclude_unset=True)
    if "end_date" in values and values["end_date"] is not None and values["end_date"] < item.start_date:
        raise HTTPException(status_code=422, detail="Data de fim anterior à data de início.")
    if any(values.get(key) is None for key in ("name", "dose", "frequency", "is_active") if key in values):
        raise HTTPException(status_code=422, detail="Campo obrigatório não pode ser nulo.")
    for key, value in values.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.MEDICATION_UPDATED, "medication", item.id)
    return item


@router.post("/consents", response_model=ConsentPublic, status_code=201)
def create_consent(payload: ConsentCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Consent:
    patient = _patient(db, payload.patient_id, user)
    if user.role == UserRole.PATIENT and patient.user_id != user.id:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")
    item = Consent(**payload.model_dump(), clinic_id=user.clinic_id, recorded_by_user_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.CONSENT_RECORDED, "consent", item.id)
    return item


@router.get("/patients/{patient_id}/consents", response_model=list[ConsentPublic])
def list_consents(patient_id: uuid.UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Consent]:
    _patient(db, patient_id, user)
    items = db.query(Consent).filter(Consent.clinic_id == user.clinic_id, Consent.patient_id == patient_id).order_by(Consent.created_at.desc()).all()
    _audit(request, user, AuditAction.CONSENT_VIEWED, "patient", patient_id)
    return items


@router.get("/notifications", response_model=list[NotificationPublic])
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Notification]:
    return db.query(Notification).filter(Notification.recipient_user_id == user.id, Notification.clinic_id == user.clinic_id).order_by(Notification.created_at.desc()).all()


@router.patch("/notifications/{item_id}/read", response_model=NotificationPublic)
def read_notification(item_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Notification:
    item = db.query(Notification).filter(Notification.id == item_id, Notification.recipient_user_id == user.id, Notification.clinic_id == user.clinic_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Notificação não encontrada.")
    item.is_read = True
    db.commit()
    db.refresh(item)
    return item
