import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import audit_request
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
    audit_request(
        request,
        action=action,
        actor=user,
        resource_type="medical_record",
        resource_id=record.id,
        metadata={"patient_id": record.patient_id},
    )


@router.get("/patients/{patient_id}/medical-records", response_model=list[MedicalRecordPublic])
def list_for_patient(
    patient_id: uuid.UUID,
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MedicalRecord]:
    records, total = list_records(db, patient_id, user, offset=(page - 1) * page_size, limit=page_size)
    response.headers["X-Total-Count"] = str(total)
    audit_request(
        request,
        action=AuditAction.MEDICAL_RECORD_VIEWED,
        actor=user,
        resource_type="medical_record_list",
        resource_id=patient_id,
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
