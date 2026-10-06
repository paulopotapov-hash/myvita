import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.rate_limit import REGISTRATION_RATE_LIMIT, limiter
from app.core.security import get_current_clinic_id, get_current_user, require_roles, set_session_cookie
from app.models import AuditAction, AuditResult, Patient, User, UserRole
from app.modules.patients.schemas import PatientPublic, PatientRegisterRequest, PatientUpdateRequest
from app.modules.patients.service import (
    get_patient_for_user,
    list_patients_for_clinic,
    register_patient,
    update_patient,
)

router = APIRouter()

# See app/modules/appointments/router.py for why this is a module-level
# variable instead of an inline require_roles(...) call in the signature.
_staff_or_admin_only = require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN)


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


@router.post("/register", response_model=PatientPublic, status_code=201)
@limiter.limit(REGISTRATION_RATE_LIMIT)
def register(
    request: Request, payload: PatientRegisterRequest, response: Response, db: Session = Depends(get_db)
) -> PatientPublic:
    patient, user = register_patient(db, payload)
    set_session_cookie(response, user)  # auto-login after successful registration
    record_audit_event(
        action=AuditAction.PATIENT_CREATED,
        result=AuditResult.SUCCESS,
        clinic_id=patient.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="patient",
        resource_id=patient.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
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


@router.get("", response_model=list[PatientPublic])
def list_mine(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    clinic_id: str = Depends(get_current_clinic_id),
    staff_user: User = Depends(_staff_or_admin_only),
) -> list[PatientPublic]:
    """
    Patient directory for the caller's own clinic — needed so staff can
    pick a patient when creating an appointment, and so appointment lists
    can show a name instead of a bare UUID. Never a cross-clinic listing:
    clinic_id always comes from the staff member's own session.
    """
    patients, total = list_patients_for_clinic(db, clinic_id, offset=(page - 1) * page_size, limit=page_size)
    response.headers["X-Total-Count"] = str(total)
    record_audit_event(
        action=AuditAction.STAFF_VIEWED_PATIENT,
        result=AuditResult.SUCCESS,
        clinic_id=clinic_id,
        actor_user_id=staff_user.id,
        actor_email=staff_user.email,
        resource_type="patient_list",
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"count": len(patients)},
    )
    return [_public(p) for p in patients]


@router.get("/{patient_id}", response_model=PatientPublic)
def detail(
    patient_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PatientPublic:
    patient = get_patient_for_user(db, patient_id, user)
    record_audit_event(
        action=(
            AuditAction.PATIENT_VIEWED_OWN_RECORD
            if user.role == UserRole.PATIENT
            else AuditAction.STAFF_VIEWED_PATIENT
        ),
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="patient",
        resource_id=patient.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
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
    record_audit_event(
        action=AuditAction.PATIENT_UPDATED,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type="patient",
        resource_id=patient.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _public(patient)
