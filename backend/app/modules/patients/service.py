from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Clinic, Patient, User, UserRole
from app.modules.patients.schemas import PatientRegisterRequest


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
