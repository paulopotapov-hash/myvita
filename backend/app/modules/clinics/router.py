from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.rate_limit import REGISTRATION_RATE_LIMIT, limiter
from app.core.security import set_session_cookie
from app.models import AuditAction, AuditResult, Clinic
from app.modules.clinics.schemas import ClinicOnboardingRequest, ClinicPublic, ClinicSummary
from app.modules.clinics.service import onboard_clinic

router = APIRouter()


@router.post("", response_model=ClinicPublic, status_code=201)
@limiter.limit(REGISTRATION_RATE_LIMIT)
def create_clinic(
    request: Request, payload: ClinicOnboardingRequest, response: Response, db: Session = Depends(get_db)
) -> Clinic:
    clinic, admin_user = onboard_clinic(db, payload)
    set_session_cookie(response, admin_user)  # auto-login the new admin
    record_audit_event(
        action=AuditAction.CLINIC_CREATED,
        result=AuditResult.SUCCESS,
        clinic_id=clinic.id,
        actor_user_id=admin_user.id,
        actor_email=admin_user.email,
        resource_type="clinic",
        resource_id=clinic.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return clinic


@router.get("", response_model=list[ClinicSummary])
def list_clinics(db: Session = Depends(get_db)) -> list[Clinic]:
    """
    Public, minimal clinic directory — just id + name — so a patient
    sign-up form can offer a clinic picker. No sensitive clinic data here.
    """
    return db.query(Clinic).order_by(Clinic.name).all()
