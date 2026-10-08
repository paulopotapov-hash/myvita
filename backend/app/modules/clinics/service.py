import uuid

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, false, or_
from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import Clinic, User, UserRole
from app.modules.clinics.schemas import ClinicOnboardingRequest


def _visibility(user: User | None) -> ColumnElement[bool]:
    """The single policy for who may see which clinic in the directory.

    A clinic is visible when (a) public patient registration is enabled AND the
    clinic is on the PUBLIC_CLINIC_IDS allowlist, or (b) it is the caller's own
    clinic. Nothing else — list and detail both go through here.
    """
    conditions: list[ColumnElement[bool]] = []
    if settings.ALLOW_PUBLIC_PATIENT_REGISTRATION and settings.PUBLIC_CLINIC_IDS:
        conditions.append(Clinic.id.in_(settings.PUBLIC_CLINIC_IDS))
    if user is not None and user.clinic_id is not None:
        conditions.append(Clinic.id == user.clinic_id)
    return or_(*conditions) if conditions else false()


def _visible_clinics(db: Session, user: User | None) -> Query[Clinic]:
    return db.query(Clinic).filter(_visibility(user))


def list_visible_clinics(
    db: Session, user: User | None, *, offset: int, limit: int
) -> tuple[list[Clinic], int]:
    query = _visible_clinics(db, user)
    total = query.count()
    return query.order_by(Clinic.name, Clinic.id).offset(offset).limit(limit).all(), total


def get_visible_clinic(db: Session, clinic_id: uuid.UUID, user: User | None) -> Clinic:
    """404 for both "does not exist" and "not visible to you" — no existence oracle."""
    clinic = _visible_clinics(db, user).filter(Clinic.id == clinic_id).first()
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clínica não encontrada.")
    return clinic


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
