import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, AuditResult, MedicalRecord, MedicalRecordRevision, User
from app.modules.medical_records.schemas import (
    MedicalRecordCreateRequest,
    MedicalRecordPublic,
    MedicalRecordRevisionPublic,
    MedicalRecordUpdateRequest,
)
from app.modules.medical_records.service import create_record, get_record, list_records, update_record

router = APIRouter()


def _audit(request: Request, user: User, action: AuditAction, record: MedicalRecord) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="medical_record",
        resource_id=record.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/patients/{patient_id}/medical-records", response_model=list[MedicalRecordPublic])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MedicalRecord]:
    records = list_records(db, patient_id, user)
    record_audit_event(
        action=AuditAction.MEDICAL_RECORD_VIEWED,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="medical_record_list",
        resource_id=patient_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"count": len(records)},
    )
    return records


@router.post("/patients/{patient_id}/medical-records", response_model=MedicalRecordPublic, status_code=201)
def create(
    patient_id: uuid.UUID,
    payload: MedicalRecordCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MedicalRecord:
    record = create_record(db, patient_id, payload, user)
    _audit(request, user, AuditAction.MEDICAL_RECORD_CREATED, record)
    return record


@router.get("/medical-records/{record_id}", response_model=MedicalRecordPublic)
def detail(
    record_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MedicalRecord:
    record = get_record(db, record_id, user)
    _audit(request, user, AuditAction.MEDICAL_RECORD_VIEWED, record)
    return record


@router.patch("/medical-records/{record_id}", response_model=MedicalRecordPublic)
def update(
    record_id: uuid.UUID,
    payload: MedicalRecordUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MedicalRecord:
    record = update_record(db, record_id, payload, user)
    _audit(request, user, AuditAction.MEDICAL_RECORD_UPDATED, record)
    return record


@router.get("/medical-records/{record_id}/revisions", response_model=list[MedicalRecordRevisionPublic])
def revisions(
    record_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MedicalRecordRevision]:
    record = get_record(db, record_id, user)
    _audit(request, user, AuditAction.MEDICAL_RECORD_VIEWED, record)
    return (
        db.query(MedicalRecordRevision)
        .filter(MedicalRecordRevision.record_id == record.id)
        .order_by(MedicalRecordRevision.version)
        .all()
    )
