import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.clinical_access import ClinicalAction, clinical_access, has_role_action, staff_profile
from app.core.security import hash_password
from app.models import Clinic, ClinicalCareAssignment, Patient, Staff, StaffRole, User, UserRole
from app.modules.patients.schemas import (
    PatientIdentifiersUpdateRequest,
    PatientRegisterRequest,
    PatientUpdateRequest,
)
from app.modules.users import service as users_service


def register_patient(db: Session, payload: PatientRegisterRequest) -> tuple[Patient, User]:
    clinic = db.get(Clinic, payload.clinic_id)
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clínica não encontrada.",
        )

    if db.query(User).filter(User.email_matches(payload.email)).first() is not None:
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
    db: Session, clinic_id: str, user: User, *, offset: int = 0, limit: int = 50, search: str | None = None
) -> tuple[list[Patient], int]:
    """
    Staff/clinic_admin only (enforced in the router) — the patient directory
    for their own clinic. `clinic_id` always comes from the authenticated
    staff member's own session, never from a client-supplied filter.
    `search` is a case-insensitive substring match on the name, applied after
    the role/assignment scoping so it can never widen what the caller may see.
    """
    query = (
        db.query(Patient)
        .options(selectinload(Patient.user))
        .filter(Patient.clinic_id == clinic_id)
        .join(User, Patient.user_id == User.id)
    )
    if user.role == UserRole.STAFF:
        staff = staff_profile(db, user)
        if staff is None or (
            staff.staff_role != StaffRole.ADMIN
            and not has_role_action(staff.staff_role, ClinicalAction.VIEW_PATIENT)
        ):
            return [], 0
        if staff.staff_role == StaffRole.ADMIN:
            pass  # The existing access matrix permits a basic, operational directory for clinic administrators.
        else:
            query = query.join(
                ClinicalCareAssignment,
                (ClinicalCareAssignment.patient_id == Patient.id)
                & (ClinicalCareAssignment.clinic_id == Patient.clinic_id),
            ).filter(
                ClinicalCareAssignment.staff_id == staff.id,
                ClinicalCareAssignment.active.is_(True),
            )
    elif user.role != UserRole.CLINIC_ADMIN:
        return [], 0
    if search:
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(User.full_name.ilike(f"%{escaped}%", escape="\\"))
    total = query.count()
    patients = query.order_by(User.full_name, Patient.id).offset(offset).limit(limit).all()
    return patients, total


def get_patient_for_user(db: Session, patient_id: uuid.UUID, user: User) -> Patient:
    patient = clinical_access(db, patient_id, user, ClinicalAction.VIEW_PATIENT)
    _ = patient.user
    return patient


# What the patient may change in their own record: contact data only.
PATIENT_EDITABLE_FIELDS = frozenset({"phone", "address_street", "address_postal_code", "address_locality"})
DUPLICATE_NIF_MESSAGE = "Já existe um paciente nesta clínica com este NIF."


def update_patient(
    db: Session, patient_id: uuid.UUID, payload: PatientUpdateRequest, user: User
) -> tuple[Patient, list[str]]:
    """Apply contact changes; returns the patient and the names of the fields that changed."""
    changes = payload.model_dump(exclude_unset=True)
    if user.role == UserRole.PATIENT:
        patient = (
            db.query(Patient)
            .options(selectinload(Patient.user))
            .filter(Patient.id == patient_id, Patient.clinic_id == user.clinic_id)
            .first()
        )
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
        if patient.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
        if not set(changes) <= PATIENT_EDITABLE_FIELDS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="O paciente só pode alterar o próprio telefone e a morada.",
            )
    else:
        patient = clinical_access(db, patient_id, user, ClinicalAction.EDIT_PATIENT)
        patient = db.query(Patient).options(selectinload(Patient.user)).filter(Patient.id == patient.id).one()
    changed = _apply(patient, changes)
    db.commit()
    db.refresh(patient)
    return patient, changed


def _apply(patient: Patient, changes: dict[str, object]) -> list[str]:
    changed = []
    for field, value in changes.items():
        if getattr(patient, field) != value:
            setattr(patient, field, value)
            changed.append(field)
    return sorted(changed)


def _identifier_patient(db: Session, patient_id: uuid.UUID, user: User, action: ClinicalAction) -> Patient:
    patient = clinical_access(db, patient_id, user, action)
    return db.query(Patient).options(selectinload(Patient.user)).filter(Patient.id == patient.id).one()


def get_identification(db: Session, patient_id: uuid.UUID, user: User) -> tuple[Patient, bool]:
    """Patient (for the masked identification card) and whether the caller may edit it."""
    patient = _identifier_patient(db, patient_id, user, ClinicalAction.VIEW_PATIENT_IDENTIFIERS)
    return patient, can_manage_identifiers(db, patient.id, user)


def can_manage_identifiers(db: Session, patient_id: uuid.UUID, user: User) -> bool:
    try:
        clinical_access(db, patient_id, user, ClinicalAction.MANAGE_PATIENT_IDENTIFIERS)
    except HTTPException:
        return False
    return True


def reveal_identifiers(db: Session, patient_id: uuid.UUID, user: User) -> Patient:
    """Full identifiers; the router audits every successful reveal."""
    return _identifier_patient(db, patient_id, user, ClinicalAction.VIEW_PATIENT_IDENTIFIERS)


def update_identifiers(
    db: Session, patient_id: uuid.UUID, payload: PatientIdentifiersUpdateRequest, user: User
) -> tuple[Patient, list[str]]:
    """Change NIF / NISS / Nº de utente. NIF is unique per clinic when filled in."""
    patient = _identifier_patient(db, patient_id, user, ClinicalAction.MANAGE_PATIENT_IDENTIFIERS)
    changes = payload.model_dump(exclude_unset=True)
    nif = changes.get("nif")
    if nif is not None and nif != patient.nif:
        duplicate = (
            db.query(Patient.id)
            .filter(Patient.clinic_id == patient.clinic_id, Patient.nif == nif, Patient.id != patient.id)
            .first()
        )
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_NIF_MESSAGE)
    changed = _apply(patient, changes)
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent registration of the same NIF
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DUPLICATE_NIF_MESSAGE) from exc
    db.refresh(patient)
    return patient, changed


def deactivate_patient(db: Session, patient_id: uuid.UUID, clinic_id: str, actor: User) -> Patient:
    patient = (
        db.query(Patient)
        .options(selectinload(Patient.user))
        .filter(Patient.id == patient_id, Patient.clinic_id == clinic_id)
        .first()
    )
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente não encontrado.")
    # Shared lifecycle rules: revoke sessions and outstanding reset links.
    users_service.deactivate(db, patient.user, actor)
    db.refresh(patient)
    return patient


def assign_clinical_staff(
    db: Session, patient_id: uuid.UUID, staff_id: uuid.UUID, clinic_id: str, actor: User
) -> ClinicalCareAssignment:
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.clinic_id == clinic_id).first()
    staff = db.query(Staff).filter(Staff.id == staff_id, Staff.clinic_id == clinic_id).first()
    if patient is None or staff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente ou profissional não encontrado.")
    if staff.staff_role not in {StaffRole.DOCTOR, StaffRole.NURSE, StaffRole.PHYSIOTHERAPIST}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Função não clínica.")
    existing = (
        db.query(ClinicalCareAssignment)
        .filter(
            ClinicalCareAssignment.patient_id == patient.id,
            ClinicalCareAssignment.staff_id == staff.id,
            ClinicalCareAssignment.active.is_(True),
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profissional já associado ao paciente.")
    assignment = ClinicalCareAssignment(
        clinic_id=patient.clinic_id,
        patient_id=patient.id,
        staff_id=staff.id,
        assigned_by_user_id=actor.id,
    )
    db.add(assignment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Profissional já associado ao paciente."
        ) from exc
    db.refresh(assignment)
    return assignment


def end_clinical_assignment(
    db: Session, patient_id: uuid.UUID, staff_id: uuid.UUID, clinic_id: str
) -> ClinicalCareAssignment:
    assignment = (
        db.query(ClinicalCareAssignment)
        .filter(
            ClinicalCareAssignment.clinic_id == clinic_id,
            ClinicalCareAssignment.patient_id == patient_id,
            ClinicalCareAssignment.staff_id == staff_id,
            ClinicalCareAssignment.active.is_(True),
        )
        .first()
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associação clínica não encontrada.")
    assignment.active = False
    assignment.ended_at = datetime.now(UTC)
    db.commit()
    db.refresh(assignment)
    return assignment
