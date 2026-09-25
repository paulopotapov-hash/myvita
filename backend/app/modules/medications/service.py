import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.clinical_access import accessible_patient, clinical_staff
from app.models import Medication, MedicationStatus, User
from app.modules.medications.schemas import (
    MedicationCreateRequest,
    MedicationDeactivateRequest,
    MedicationUpdateRequest,
)


def list_medications(
    db: Session,
    patient_id: uuid.UUID,
    user: User,
    *,
    medication_status: MedicationStatus | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Medication], int]:
    accessible_patient(db, patient_id, user)
    query = db.query(Medication).filter(
        Medication.patient_id == patient_id, Medication.clinic_id == user.clinic_id
    )
    if medication_status is not None:
        query = query.filter(Medication.status == medication_status)
    total = query.count()
    medications = (
        query.order_by(Medication.created_at.desc(), Medication.id.desc()).offset(offset).limit(limit).all()
    )
    return medications, total


def get_medication(db: Session, medication_id: uuid.UUID, user: User) -> Medication:
    medication = (
        db.query(Medication)
        .filter(Medication.id == medication_id, Medication.clinic_id == user.clinic_id)
        .first()
    )
    if medication is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicação não encontrada.")
    accessible_patient(db, medication.patient_id, user)
    return medication


def create_medication(
    db: Session, patient_id: uuid.UUID, payload: MedicationCreateRequest, user: User
) -> Medication:
    patient = accessible_patient(db, patient_id, user, write=True)
    staff = clinical_staff(db, user)
    medication = Medication(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        prescribed_by_staff_id=staff.id,
        **payload.model_dump(),
    )
    db.add(medication)
    db.commit()
    db.refresh(medication)
    return medication


def update_medication(
    db: Session, medication_id: uuid.UUID, payload: MedicationUpdateRequest, user: User
) -> Medication:
    medication = get_medication(db, medication_id, user)
    accessible_patient(db, medication.patient_id, user, write=True)
    clinical_staff(db, user)
    if medication.status != MedicationStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Medicação já terminada.")
    changes = payload.model_dump(exclude_unset=True)
    if (
        changes.get("status") in {MedicationStatus.COMPLETED, MedicationStatus.DISCONTINUED}
        and "end_date" not in changes
    ):
        changes["end_date"] = date.today()
    for field, value in changes.items():
        setattr(medication, field, value)
    if medication.end_date is not None and medication.end_date < medication.start_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Data final inválida.")
    db.commit()
    db.refresh(medication)
    return medication


def deactivate_medication(
    db: Session,
    medication_id: uuid.UUID,
    payload: MedicationDeactivateRequest | None,
    user: User,
) -> Medication:
    medication = get_medication(db, medication_id, user)
    accessible_patient(db, medication.patient_id, user, write=True)
    clinical_staff(db, user)
    if medication.status != MedicationStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Medicação já terminada.")
    requested_end = payload.end_date if payload is not None else None
    end_date = requested_end or max(date.today(), medication.start_date)
    if end_date < medication.start_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Data final inválida.")
    medication.status = MedicationStatus.DISCONTINUED
    medication.end_date = end_date
    db.commit()
    db.refresh(medication)
    return medication
