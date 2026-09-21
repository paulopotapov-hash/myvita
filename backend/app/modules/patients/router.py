from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.rate_limit import REGISTRATION_RATE_LIMIT, limiter
from app.core.security import get_current_clinic_id, require_roles, set_session_cookie
from app.models import AuditAction, AuditResult, User, UserRole
from app.modules.patients.schemas import PatientPublic, PatientRegisterRequest
from app.modules.patients.service import list_patients_for_clinic, register_patient

router = APIRouter()

# See app/modules/appointments/router.py for why this is a module-level
# variable instead of an inline require_roles(...) call in the signature.
_staff_or_admin_only = require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN)


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
    )


@router.get("", response_model=list[PatientPublic])
def list_mine(
    request: Request,
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
    patients = list_patients_for_clinic(db, clinic_id)
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
    return [
        PatientPublic(
            id=p.id,
            clinic_id=p.clinic_id,
            full_name=p.user.full_name,
            birth_date=p.birth_date,
            phone=p.phone,
        )
        for p in patients
    ]
