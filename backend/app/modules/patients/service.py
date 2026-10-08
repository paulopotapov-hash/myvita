import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.core.clinical_access import accessible_patient, is_clinical_staff
from app.core.config import settings
from app.core.security import hash_password
from app.models import Clinic, Patient, User, UserRole
from app.modules.patients.schemas import PatientRegisterRequest, PatientUpdateRequest


def register_patient(db: Session, payload: PatientRegisterRequest) -> tuple[Patient, User]:
    """Public self-registration (POST /patients/register)."""
    clinic = db.get(Clinic, payload.clinic_id)
    # Only clinics that opted in (PUBLIC_CLINIC_IDS, same allowlist as the public
    # directory) accept self-registration. A non-public clinic gets exactly the
    # unknown-clinic response, so registration is not a clinic-existence oracle.
    if clinic is None or clinic.id not in settings.PUBLIC_CLINIC_IDS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clínica não encontrada.",
        )
    return create_patient_account(db, clinic, payload)


def create_patient_account(
    db: Session, clinic: Clinic, payload: PatientRegisterRequest
) -> tuple[Patient, User]:
    """Creates a patient user + profile in `clinic`. No public-registration policy
    is applied here: callers are trusted (the public endpoint above, after its
    allowlist check, and operator tooling such as scripts/seed_staging.py)."""
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
    db: Session, clinic_id: str, *, offset: int = 0, limit: int = 50, search: str | None = None
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
    if search:
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(User.full_name.ilike(f"%{escaped}%", escape="\\"))
    total = query.count()
    patients = query.order_by(User.full_name, Patient.id).offset(offset).limit(limit).all()
    return patients, total


def get_patient_for_user(db: Session, patient_id: uuid.UUID, user: User) -> Patient:
    patient = accessible_patient(db, patient_id, user)
    _ = patient.user
    return patient


def update_patient(db: Session, patient_id: uuid.UUID, payload: PatientUpdateRequest, user: User) -> Patient:
    changes = payload.model_dump(exclude_unset=True)
    patient = (
        db.query(Patient)
        .options(selectinload(Patient.user))
        .filter(Patient.id == patient_id, Patient.clinic_id == user.clinic_id)
        .first()
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    if user.role == UserRole.PATIENT:
        if patient.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
        if set(changes) != {"phone"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="O paciente só pode alterar o próprio telefone."
            )
    elif not is_clinical_staff(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas profissionais clínicos podem alterar dados demográficos.",
        )
    for field, value in changes.items():
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    return patient


def deactivate_patient(db: Session, patient_id: uuid.UUID, clinic_id: str) -> Patient:
    patient = (
        db.query(Patient)
        .options(selectinload(Patient.user))
        .filter(Patient.id == patient_id, Patient.clinic_id == clinic_id)
        .first()
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    if patient.user.is_active:
        patient.user.is_active = False
        patient.user.token_epoch += 1
        db.commit()
        db.refresh(patient)
    return patient
