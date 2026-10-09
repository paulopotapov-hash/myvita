import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.clinical_access import ClinicalAction, clinical_access, clinical_staff
from app.models import MedicalRecord, MedicalRecordRevision, User
from app.modules.medical_records.schemas import MedicalRecordCreateRequest, MedicalRecordUpdateRequest


def list_records(
    db: Session, patient_id: uuid.UUID, user: User, *, offset: int = 0, limit: int = 50
) -> tuple[list[MedicalRecord], int]:
    clinical_access(db, patient_id, user, ClinicalAction.VIEW_MEDICAL_RECORDS)
    query = db.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id, MedicalRecord.clinic_id == user.clinic_id
    )
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registo clínico não encontrado.")
    clinical_access(db, record.patient_id, user, ClinicalAction.VIEW_MEDICAL_RECORDS)
    return record


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
        version=1,
    )
    db.add(record)
    db.flush()
    db.add(
        MedicalRecordRevision(
            record_id=record.id,
            editor_staff_id=staff.id,
            version=1,
            title=record.title,
            content=record.content,
        )
    )
    db.commit()
    db.refresh(record)
    return record


def update_record(
    db: Session, record_id: uuid.UUID, payload: MedicalRecordUpdateRequest, user: User
) -> MedicalRecord:
    record = get_record(db, record_id, user)
    clinical_access(db, record.patient_id, user, ClinicalAction.EDIT_MEDICAL_RECORDS)
    staff = clinical_staff(db, user, record.patient_id, ClinicalAction.EDIT_MEDICAL_RECORDS)
    # Lock + reload so concurrent edits get distinct, gapless versions.
    db.refresh(record, with_for_update=True)
    # Optimistic concurrency (feature/messages-backend contract): the client
    # states the version it edited; a stale edit is refused, never merged.
    if record.version != payload.expected_version:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O registo clínico foi alterado por outro utilizador. Recarregue antes de guardar.",
        )
    record.version += 1
    record.title = payload.title
    record.content = payload.content
    db.add(
        MedicalRecordRevision(
            record_id=record.id,
            editor_staff_id=staff.id,
            version=record.version,
            title=record.title,
            content=record.content,
        )
    )
    db.commit()
    db.refresh(record)
    return record
