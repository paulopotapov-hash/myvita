import uuid
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.pagination import DEFAULT_PAGE_SIZE, Limit, Offset
from app.core.security import ClinicalPermission, require_permission
from app.models import AuditAction, AuditResult, Medication, Patient, User
from app.modules.medications.schemas import (
    MedicationCreate,
    MedicationCreateLegacy,
    MedicationPublic,
    MedicationStop,
    MedicationUpdate,
)

router = APIRouter()
_read = require_permission(ClinicalPermission.MEDICATION_READ)
_write = require_permission(ClinicalPermission.MEDICATION_WRITE)


def _audit(request: Request, user: User, action: AuditAction, resource_type: str, resource_id: uuid.UUID) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def _audit_not_found(request: Request, user: User, resource_type: str, resource_id: uuid.UUID) -> None:
    record_audit_event(
        action=AuditAction.PERMISSION_DENIED,
        result=AuditResult.DENIED,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"path": request.url.path},
    )


def _patient(db: Session, patient_id: uuid.UUID, user: User, request: Request) -> Patient:
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.clinic_id == user.clinic_id).first()
    if patient is None or (user.role.value == "patient" and patient.user_id != user.id):
        _audit_not_found(request, user, "patient", patient_id)
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")
    return patient


def _medication(db: Session, medication_id: uuid.UUID, user: User, request: Request) -> Medication:
    item = (
        db.query(Medication)
        .join(Patient, Medication.patient_id == Patient.id)
        .filter(
            Medication.id == medication_id,
            Medication.clinic_id == user.clinic_id,
            Patient.clinic_id == user.clinic_id,
        )
        .first()
    )
    if item is None:
        _audit_not_found(request, user, "medication", medication_id)
        raise HTTPException(status_code=404, detail="Medicação não encontrada.")
    _patient(db, item.patient_id, user, request)
    return item


@router.post("/patients/{patient_id}/medications", response_model=MedicationPublic, status_code=201)
def create_medication(
    patient_id: uuid.UUID,
    payload: MedicationCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_write),
) -> Medication:
    _patient(db, patient_id, user, request)
    item = Medication(
        **payload.model_dump(),
        clinic_id=user.clinic_id,
        patient_id=patient_id,
        created_by_user_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.MEDICATION_CREATED, "medication", item.id)
    return item


@router.post("/medications", response_model=MedicationPublic, status_code=201, include_in_schema=False)
def create_medication_legacy(
    payload: MedicationCreateLegacy,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_write),
) -> Medication:
    patient_id = payload.patient_id
    _patient(db, patient_id, user, request)
    values = payload.model_dump(exclude={"patient_id"})
    item = Medication(
        **values,
        clinic_id=user.clinic_id,
        patient_id=patient_id,
        created_by_user_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.MEDICATION_CREATED, "medication", item.id)
    return item


@router.get("/patients/{patient_id}/medications", response_model=list[MedicationPublic])
def list_medications(
    patient_id: uuid.UUID,
    request: Request,
    is_active: bool | None = Query(default=None),
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
    db: Session = Depends(get_db),
    user: User = Depends(_read),
) -> list[Medication]:
    _patient(db, patient_id, user, request)
    query = db.query(Medication).filter(
        Medication.clinic_id == user.clinic_id, Medication.patient_id == patient_id
    )
    if is_active is not None:
        query = query.filter(Medication.is_active == is_active)
    items = query.order_by(Medication.created_at.desc(), Medication.id.desc()).offset(offset).limit(limit).all()
    _audit(request, user, AuditAction.MEDICATION_VIEWED, "patient", patient_id)
    return items


@router.get("/medications/{medication_id}", response_model=MedicationPublic)
def get_medication(
    medication_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_read),
) -> Medication:
    item = _medication(db, medication_id, user, request)
    _audit(request, user, AuditAction.MEDICATION_VIEWED, "medication", item.id)
    return item


@router.patch("/medications/{medication_id}", response_model=MedicationPublic)
def update_medication(
    medication_id: uuid.UUID,
    payload: MedicationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_write),
) -> Medication:
    item = _medication(db, medication_id, user, request)
    values = payload.model_dump(exclude_unset=True)
    was_active = item.is_active
    start_date = values.get("start_date", item.start_date)
    end_date = values.get("end_date", item.end_date)
    if end_date is not None and end_date < start_date:
        raise HTTPException(status_code=422, detail="Data de fim anterior à data de início.")
    for key, value in values.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    action = (
        AuditAction.MEDICATION_DEACTIVATED
        if was_active and values.get("is_active") is False
        else AuditAction.MEDICATION_UPDATED
    )
    _audit(request, user, action, "medication", item.id)
    return item


@router.post("/medications/{medication_id}/deactivate", response_model=MedicationPublic)
def deactivate_medication(
    medication_id: uuid.UUID,
    request: Request,
    payload: MedicationStop | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(_write),
) -> Medication:
    item = _medication(db, medication_id, user, request)
    end_date = payload.end_date if payload else None
    if end_date is not None and end_date < item.start_date:
        raise HTTPException(status_code=422, detail="Data de fim anterior à data de início.")
    item.is_active = False
    item.end_date = end_date or item.end_date or max(date.today(), item.start_date)
    db.commit()
    db.refresh(item)
    _audit(request, user, AuditAction.MEDICATION_DEACTIVATED, "medication", item.id)
    return item
