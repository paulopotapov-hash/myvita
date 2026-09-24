import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_password
from app.models import Clinic, Patient, User, UserRole
from app.modules.patients.schemas import PatientRegisterRequest, PatientUpdateRequest


def register_patient(db: Session, payload: PatientRegisterRequest) -> tuple[Patient, User]:
    clinic = db.get(Clinic, payload.clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clínica não encontrada.",
        )

    if db.query(User).filter(User.email == payload.email).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe uma conta com este email.",
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.PATIENT,
        clinic_id=clinic.id,
    )
    db.add(user)
    db.flush()

    patient = Patient(
        user_id=user.id,
        clinic_id=clinic.id,
        birth_date=payload.birth_date,
        phone=payload.phone,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    db.refresh(user)
    return patient, user


def list_patients_for_clinic(
    db: Session, clinic_id: str, *, offset: int = 0, limit: int = 50
) -> tuple[list[Patient], int]:
    """
    Staff/clinic_admin only (enforced in the router) — the patient directory
    for their own clinic. `clinic_id` always comes from the authenticated
    staff member's own session, never from a client-supplied filter.
    """
    query = (
        db.query(Patient)
        .options(selectinload(Patient.user))
        .filter(Patient.clinic_id == clinic_id)
        .join(User, Patient.user_id == User.id)
    )
    total = query.count()
    patients = query.order_by(User.full_name, Patient.id).offset(offset).limit(limit).all()
    return patients, total


def get_patient_for_user(db: Session, patient_id: uuid.UUID, user: User) -> Patient:
    patient = (
        db.query(Patient)
        .options(selectinload(Patient.user))
        .filter(Patient.id == patient_id, Patient.clinic_id == user.clinic_id)
        .first()
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    if user.role == UserRole.PATIENT and patient.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    return patient


def update_patient(db: Session, patient_id: uuid.UUID, payload: PatientUpdateRequest, user: User) -> Patient:
    patient = get_patient_for_user(db, patient_id, user)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    return patient
