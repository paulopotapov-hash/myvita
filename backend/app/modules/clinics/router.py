import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.audit import audit_request
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import REGISTRATION_RATE_LIMIT, limiter
from app.core.security import get_optional_user, set_session_cookie
from app.models import AuditAction, Clinic, User
from app.modules.clinics.schemas import ClinicOnboardingRequest, ClinicPublic, ClinicSummary
from app.modules.clinics.service import get_visible_clinic, list_visible_clinics, onboard_clinic

router = APIRouter()


@router.post("", response_model=ClinicPublic, status_code=201)
@limiter.limit(REGISTRATION_RATE_LIMIT)
def create_clinic(
    request: Request, payload: ClinicOnboardingRequest, response: Response, db: Session = Depends(get_db)
) -> Clinic:
    if not settings.ALLOW_PUBLIC_CLINIC_ONBOARDING:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registo público de clínicas desativado.",
        )
    clinic, admin_user = onboard_clinic(db, payload)
    set_session_cookie(response, admin_user)  # auto-login the new admin
    audit_request(
        request,
        action=AuditAction.CLINIC_CREATED,
        actor=admin_user,
        clinic_id=clinic.id,
        resource_type="clinic",
        resource_id=clinic.id,
    )
    return clinic


@router.get("", response_model=list[ClinicSummary])
def list_clinics(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> list[Clinic]:
    """
    Clinic directory limited to what the caller may see: clinics that opted in
    via PUBLIC_CLINIC_IDS (only while public patient registration is enabled)
    plus the caller's own clinic. Anonymous callers with nothing public get an
    empty page, so the platform's client list is not enumerable. Paginated;
    total in `X-Total-Count`.
    """
    clinics, total = list_visible_clinics(db, user, offset=(page - 1) * page_size, limit=page_size)
    response.headers["X-Total-Count"] = str(total)
    return clinics


@router.get("/{clinic_id}", response_model=ClinicSummary)
def clinic_detail(
    clinic_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> Clinic:
    """One clinic under the same visibility policy as the list. 404 whether the clinic is private or absent."""
    return get_visible_clinic(db, clinic_id, user)
