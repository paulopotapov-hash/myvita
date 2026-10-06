import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import audit_denials, record_access
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditAction, MedicalRecord, MedicalRecordRevision, User
from app.modules.medical_records.schemas import (
    MedicalRecordCreateRequest,
    MedicalRecordPublic,
    MedicalRecordRevisionPublic,
    MedicalRecordUpdateRequest,
)
from app.modules.medical_records.service import create_record, get_record, list_records, update_record

router = APIRouter()


def _audit(request: Request, user: User, action: AuditAction, record: MedicalRecord) -> None:
    record_access(request, user, action, "medical_record", record.id)


@router.get("/patients/{patient_id}/medical-records", response_model=list[MedicalRecordPublic])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MedicalRecord]:
    with audit_denials(request, user, "medical_record", patient_id):
        records = list_records(db, patient_id, user)
    record_access(
        request, user, AuditAction.MEDICAL_RECORD_VIEWED, "medical_record_list", patient_id, metadata={"count": len(records)}
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
    with audit_denials(request, user, "medical_record", patient_id):
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
    with audit_denials(request, user, "medical_record", record_id):
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
    with audit_denials(request, user, "medical_record", record_id):
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
    with audit_denials(request, user, "medical_record", record_id):
        record = get_record(db, record_id, user)
    _audit(request, user, AuditAction.MEDICAL_RECORD_VIEWED, record)
    return (
        db.query(MedicalRecordRevision)
        .filter(MedicalRecordRevision.record_id == record.id)
        .order_by(MedicalRecordRevision.version)
        .all()
    )
