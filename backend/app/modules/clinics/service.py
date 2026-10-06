from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Clinic, User, UserRole
from app.modules.clinics.schemas import ClinicOnboardingRequest


def onboard_clinic(db: Session, payload: ClinicOnboardingRequest) -> tuple[Clinic, User]:
    if db.query(User).filter(User.email == payload.admin_email).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe uma conta com este email.",
        )

    if payload.nif and db.query(Clinic).filter(Clinic.nif == payload.nif).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe uma clínica registada com este NIF.",
        )

    clinic = Clinic(
        name=payload.clinic_name,
        nif=payload.nif,
        address=payload.address,
        phone=payload.phone,
    )
    db.add(clinic)
    db.flush()  # need clinic.id before creating the admin user

    admin_user = User(
        email=payload.admin_email,
        full_name=payload.admin_full_name,
        hashed_password=hash_password(payload.admin_password),
        role=UserRole.CLINIC_ADMIN,
        clinic_id=clinic.id,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(clinic)
    db.refresh(admin_user)
    return clinic, admin_user
