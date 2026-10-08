import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.audit import audit_request
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, REGISTRATION_RATE_LIMIT, limiter
from app.core.security import get_current_clinic_id, get_current_user, require_roles, set_session_cookie
from app.models import AuditAction, Patient, User, UserRole
from app.modules.patients.schemas import (
    PatientPublic,
    PatientRegisterRequest,
    PatientSummary,
    PatientUpdateRequest,
)
from app.modules.patients.service import (
    deactivate_patient,
    get_patient_for_user,
    list_patients_for_clinic,
    register_patient,
    update_patient,
)

router = APIRouter()

# See app/modules/appointments/router.py for why this is a module-level
# variable instead of an inline require_roles(...) call in the signature.
_staff_or_admin_only = require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN)
_admin_only = require_roles(UserRole.CLINIC_ADMIN)


def _public(patient: Patient) -> PatientPublic:
    return PatientPublic(
        id=patient.id,
        clinic_id=patient.clinic_id,
        full_name=patient.user.full_name,
        birth_date=patient.birth_date,
        phone=patient.phone,
        national_health_number=patient.national_health_number,
        is_active=patient.user.is_active,
    )


def _summary(patient: Patient) -> PatientSummary:
    return PatientSummary(
        id=patient.id,
        clinic_id=patient.clinic_id,
        full_name=patient.user.full_name,
        is_active=patient.user.is_active,
    )


@router.post("/register", response_model=PatientPublic, status_code=201)
@limiter.limit(REGISTRATION_RATE_LIMIT)
def register(
    request: Request, payload: PatientRegisterRequest, response: Response, db: Session = Depends(get_db)
) -> PatientPublic:
    if not settings.ALLOW_PUBLIC_PATIENT_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registo público de pacientes desativado.",
        )
    patient, user = register_patient(db, payload)
    set_session_cookie(response, user)  # auto-login after successful registration
    audit_request(
        request,
        action=AuditAction.PATIENT_CREATED,
        actor=user,
        clinic_id=patient.clinic_id,
        resource_type="patient",
        resource_id=patient.id,
    )
    return PatientPublic(
        id=patient.id,
        clinic_id=patient.clinic_id,
        full_name=user.full_name,
        birth_date=patient.birth_date,
        phone=patient.phone,
        national_health_number=patient.national_health_number,
        is_active=user.is_active,
    )


@router.get("", response_model=list[PatientSummary])
def list_mine(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    staff_user: User = Depends(_staff_or_admin_only),
) -> list[PatientSummary]:
    """
    Patient directory for the caller's own clinic — needed so staff can
    pick a patient when creating an appointment, and so appointment lists
    can show a name instead of a bare UUID. Never a cross-clinic listing:
    clinic_id always comes from the staff member's own session.
    """
    if search is not None and not search.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Pesquisa vazia.")
    patients, total = list_patients_for_clinic(
        db,
        clinic_id,
        offset=(page - 1) * page_size,
        limit=page_size,
        search=search,
    )
    response.headers["X-Total-Count"] = str(total)
    audit_request(
        request,
        action=AuditAction.STAFF_VIEWED_PATIENT,
        actor=staff_user,
        resource_type="patient_list",
        metadata={"count": len(patients)},
    )
    return [_summary(p) for p in patients]


@router.get("/{patient_id}", response_model=PatientPublic)
def detail(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PatientPublic:
    patient = get_patient_for_user(db, patient_id, user)
    audit_request(
        request,
        action=(
            AuditAction.PATIENT_VIEWED_OWN_RECORD
            if user.role == UserRole.PATIENT
            else AuditAction.STAFF_VIEWED_PATIENT
        ),
        actor=user,
        resource_type="patient",
        resource_id=patient.id,
    )
    return _public(patient)


@router.patch("/{patient_id}", response_model=PatientPublic)
def update(
    patient_id: uuid.UUID,
    payload: PatientUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PatientPublic:
    patient = update_patient(db, patient_id, payload, user)
    audit_request(
        request,
        action=AuditAction.PATIENT_UPDATED,
        actor=user,
        resource_type="patient",
        resource_id=patient.id,
    )
    return _public(patient)


@router.post("/{patient_id}/deactivate", response_model=PatientSummary)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def deactivate(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    admin: User = Depends(_admin_only),
) -> PatientSummary:
    patient = deactivate_patient(db, patient_id, clinic_id)
    audit_request(
        request,
        action=AuditAction.USER_DISABLED,
        actor=admin,
        resource_type="user",
        resource_id=patient.user_id,
        metadata={"patient_id": patient.id},
    )
    return _summary(patient)
