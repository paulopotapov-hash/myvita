import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.audit import client_ip, record_audit_event
from app.core.database import get_db
from app.core.rate_limit import AUTHENTICATED_WRITE_RATE_LIMIT, limiter
from app.core.security import require_roles
from app.models import AuditAction, AuditResult, User, UserRole
from app.modules.users import service
from app.modules.users.schemas import AccountSummary, PasswordResetIssued

router = APIRouter()
_clinic_admin_only = require_roles(UserRole.CLINIC_ADMIN)


def _summary(view: service.AccountView) -> AccountSummary:
    user = view.user
    return AccountSummary(
        id=user.id,
        full_name=user.full_name,
        role=user.role,
        staff_role=view.staff_role,
        email=None if user.role == UserRole.PATIENT else user.email,
        is_active=user.is_active,
        mfa_enabled=view.mfa_enabled,
        must_change_password=user.must_change_password,
    )


def _single(db: Session, user: User) -> AccountSummary:
    return _summary(service.account_view(db, user))


def _audit(
    request: Request, admin: User, action: AuditAction, target: User, metadata: dict[str, Any] | None = None
) -> None:
    record_audit_event(
        action=action,
        result=AuditResult.SUCCESS,
        clinic_id=admin.clinic_id,
        actor_user_id=admin.id,
        actor_email=admin.email,
        resource_type="user",
        resource_id=target.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"target_role": target.role.value, **(metadata or {})},
    )


@router.get("", response_model=list[AccountSummary])
def list_accounts(
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(_clinic_admin_only),
) -> list[AccountSummary]:
    assert admin.clinic_id is not None
    views, total = service.list_accounts(db, admin.clinic_id, offset=(page - 1) * page_size, limit=page_size)
    response.headers["X-Total-Count"] = str(total)
    return [_summary(view) for view in views]


@router.post("/{user_id}/deactivate", response_model=AccountSummary)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def deactivate(
    user_id: uuid.UUID, request: Request, db: Session = Depends(get_db), admin: User = Depends(_clinic_admin_only)
) -> AccountSummary:
    assert admin.clinic_id is not None
    target = service.deactivate(db, service.get_clinic_user(db, user_id, admin.clinic_id), admin)
    _audit(request, admin, AuditAction.USER_DISABLED, target)
    return _single(db, target)


@router.post("/{user_id}/reactivate", response_model=AccountSummary)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def reactivate(
    user_id: uuid.UUID, request: Request, db: Session = Depends(get_db), admin: User = Depends(_clinic_admin_only)
) -> AccountSummary:
    assert admin.clinic_id is not None
    target = service.reactivate(db, service.get_clinic_user(db, user_id, admin.clinic_id), admin)
    _audit(request, admin, AuditAction.USER_ENABLED, target)
    return _single(db, target)


@router.post("/{user_id}/password-reset", response_model=PasswordResetIssued, status_code=201)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def issue_password_reset(
    user_id: uuid.UUID, request: Request, db: Session = Depends(get_db), admin: User = Depends(_clinic_admin_only)
) -> PasswordResetIssued:
    assert admin.clinic_id is not None
    target = service.get_clinic_user(db, user_id, admin.clinic_id)
    token, expires_at = service.issue_password_reset(db, target, admin)
    # The token is returned to the admin exactly once and never audited.
    _audit(request, admin, AuditAction.PASSWORD_RESET_ISSUED, target, {"expires_at": expires_at.isoformat()})
    return PasswordResetIssued(user_id=target.id, token=token, expires_at=expires_at)


@router.post("/{user_id}/require-password-change", response_model=AccountSummary)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def require_password_change(
    user_id: uuid.UUID, request: Request, db: Session = Depends(get_db), admin: User = Depends(_clinic_admin_only)
) -> AccountSummary:
    assert admin.clinic_id is not None
    target = service.require_password_change(db, service.get_clinic_user(db, user_id, admin.clinic_id), admin)
    _audit(request, admin, AuditAction.PASSWORD_CHANGE_REQUIRED, target)
    return _single(db, target)


@router.post("/{user_id}/mfa/reset", response_model=AccountSummary)
@limiter.limit(AUTHENTICATED_WRITE_RATE_LIMIT)
def reset_mfa(
    user_id: uuid.UUID, request: Request, db: Session = Depends(get_db), admin: User = Depends(_clinic_admin_only)
) -> AccountSummary:
    assert admin.clinic_id is not None
    target = service.reset_mfa(db, service.get_clinic_user(db, user_id, admin.clinic_id), admin)
    _audit(request, admin, AuditAction.MFA_RESET, target)
    return _single(db, target)
