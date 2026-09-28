import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.clinical_access import clinical_staff
from app.core.database import get_db
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, INVITATION_PUBLIC_RATE_LIMIT, limiter
from app.core.security import require_roles, set_session_cookie
from app.models import AuditAction, AuditResult, User, UserRole
from app.modules.auth.router import _public_user
from app.modules.auth.schemas import UserPublic
from app.modules.invitations.schemas import (
    InvitationAcceptRequest,
    InvitationCreated,
    InvitationPreview,
    InvitationPreviewRequest,
    PatientInvitationCreateRequest,
    StaffInvitationCreateRequest,
)
from app.modules.invitations.service import accept_invitation, create_invitation, invitation_preview

router = APIRouter()
_admin_only = require_roles(UserRole.CLINIC_ADMIN)
_staff_or_admin = require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN)


def _audit(
    request: Request,
    actor: User,
    action: AuditAction,
    invitation_id: uuid.UUID,
    clinic_id: uuid.UUID,
) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=clinic_id,
        actor_user_id=actor.id,
        actor_email=actor.email,
        resource_type="invitation",
        resource_id=invitation_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/staff", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def invite_staff(
    payload: StaffInvitationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin_only),
) -> InvitationCreated:
    assert admin.clinic_id is not None
    invitation, token = create_invitation(
        db,
        clinic_id=admin.clinic_id,
        inviter_id=admin.id,
        email=str(payload.email),
        full_name=payload.full_name,
        role=UserRole.STAFF,
        staff_role=payload.staff_role,
        specialty=payload.specialty,
    )
    _audit(request, admin, AuditAction.INVITATION_CREATED, invitation.id, invitation.clinic_id)
    public = InvitationCreated.model_validate({**invitation.__dict__, "token": token})
    return public


@router.post("/patients", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def invite_patient(
    payload: PatientInvitationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(_staff_or_admin),
) -> InvitationCreated:
    assert actor.clinic_id is not None
    if actor.role == UserRole.STAFF:
        clinical_staff(db, actor)
    invitation, token = create_invitation(
        db,
        clinic_id=actor.clinic_id,
        inviter_id=actor.id,
        email=str(payload.email),
        full_name=payload.full_name,
        role=UserRole.PATIENT,
    )
    _audit(request, actor, AuditAction.INVITATION_CREATED, invitation.id, invitation.clinic_id)
    return InvitationCreated.model_validate({**invitation.__dict__, "token": token})


@router.post("/preview", response_model=InvitationPreview)
@limiter.limit(INVITATION_PUBLIC_RATE_LIMIT)
def preview(
    payload: InvitationPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> InvitationPreview:
    invitation, clinic = invitation_preview(db, payload.token)
    return InvitationPreview(
        clinic_name=clinic.name,
        email=invitation.email,
        full_name=invitation.full_name,
        role=invitation.role,
        staff_role=invitation.staff_role,
        expires_at=invitation.expires_at,
    )


@router.post("/accept", response_model=UserPublic)
@limiter.limit(INVITATION_PUBLIC_RATE_LIMIT)
def accept(
    payload: InvitationAcceptRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserPublic:
    invitation, user = accept_invitation(db, payload.token, payload.password)
    set_session_cookie(response, user)
    _audit(request, user, AuditAction.INVITATION_ACCEPTED, invitation.id, invitation.clinic_id)
    return _public_user(db, user)
