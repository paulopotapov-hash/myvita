import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.clinical_access import accessible_patient, clinical_staff
from app.models import MedicalRecord, MedicalRecordRevision, User
from app.modules.medical_records.schemas import MedicalRecordCreateRequest, MedicalRecordUpdateRequest


def list_records(db: Session, patient_id: uuid.UUID, user: User) -> list[MedicalRecord]:
    accessible_patient(db, patient_id, user)
    return (
        db.query(MedicalRecord)
        .filter(MedicalRecord.patient_id == patient_id, MedicalRecord.clinic_id == user.clinic_id)
        .order_by(MedicalRecord.created_at.desc(), MedicalRecord.id.desc())
        .all()
    )


def get_record(db: Session, record_id: uuid.UUID, user: User) -> MedicalRecord:
    record = (
        db.query(MedicalRecord)
        .filter(MedicalRecord.id == record_id, MedicalRecord.clinic_id == user.clinic_id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registo clínico não encontrado.")
    accessible_patient(db, record.patient_id, user)
    return record


def create_record(
    db: Session, patient_id: uuid.UUID, payload: MedicalRecordCreateRequest, user: User
) -> MedicalRecord:
    patient = accessible_patient(db, patient_id, user, write=True)
    staff = clinical_staff(db, user)
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
    accessible_patient(db, record.patient_id, user, write=True)
    staff = clinical_staff(db, user)
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
