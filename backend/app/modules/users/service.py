"""
Clinic-admin account administration: deactivate/reactivate, issue password
reset links, require a password change, reset a lost MFA device.

Guard rails shared by every operation:
- the target must belong to the admin's own clinic (otherwise 404, never
  revealing that the account exists elsewhere);
- an admin never acts on their own account here (self-service endpoints
  exist for that);
- credential operations (reset link, forced change, MFA reset) are not
  available against another clinic admin: that would let one admin take
  over another admin's identity and blur the audit trail. Recovering a
  clinic admin is an operator procedure (docs/security/account-lifecycle.md).
- deactivation never deletes anything: clinical history stays intact.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Staff, StaffRole, User, UserMfa, UserRole
from app.modules.auth import mfa_service, password_reset


@dataclass(frozen=True)
class AccountView:
    user: User
    staff_role: StaffRole | None
    mfa_enabled: bool


def get_clinic_user(db: Session, user_id: uuid.UUID, clinic_id: uuid.UUID | str) -> User:
    user = db.query(User).filter(User.id == user_id, User.clinic_id == clinic_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada.")
    return user


def _reject_self(target: User, actor: User, *, detail: str = "Esta ação não pode ser aplicada à própria conta.") -> None:
    if target.id == actor.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _reject_admin_credentials(target: User) -> None:
    if target.role == UserRole.CLINIC_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="As credenciais de outro administrador não podem ser geridas a partir desta conta.",
        )


def list_accounts(db: Session, clinic_id: uuid.UUID | str, *, offset: int, limit: int) -> tuple[list[AccountView], int]:
    query = db.query(User).filter(User.clinic_id == clinic_id)
    total = query.count()
    users = query.order_by(User.role, User.full_name, User.id).offset(offset).limit(limit).all()
    ids = [user.id for user in users]
    staff_roles = {
        staff.user_id: staff.staff_role for staff in db.query(Staff).filter(Staff.user_id.in_(ids)).all()
    }
    enabled = {
        row.user_id
        for row in db.query(UserMfa.user_id).filter(UserMfa.user_id.in_(ids), UserMfa.enabled_at.is_not(None)).all()
    }
    return [AccountView(user, staff_roles.get(user.id), user.id in enabled) for user in users], total


def account_view(db: Session, user: User) -> AccountView:
    staff = db.query(Staff).filter(Staff.user_id == user.id).first()
    enabled = (
        db.query(UserMfa.user_id).filter(UserMfa.user_id == user.id, UserMfa.enabled_at.is_not(None)).first()
        is not None
    )
    return AccountView(user, staff.staff_role if staff else None, enabled)


def deactivate(db: Session, target: User, actor: User) -> User:
    # Self-deactivation would lock the admin out with no way back in-app.
    _reject_self(target, actor, detail="Não pode desativar a própria conta.")
    if target.role == UserRole.CLINIC_ADMIN and target.is_active:
        other_active_admins = (
            db.query(User)
            .filter(
                User.clinic_id == target.clinic_id,
                User.role == UserRole.CLINIC_ADMIN,
                User.is_active.is_(True),
                User.id != target.id,
            )
            .count()
        )
        if other_active_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Não é possível desativar o último administrador ativo da clínica.",
            )
    if target.is_active:
        target.is_active = False
        # Revoke every live session and any outstanding reset link.
        target.token_epoch += 1
        password_reset.revoke_outstanding(db, target.id)
        db.commit()
        db.refresh(target)
    return target


def reactivate(db: Session, target: User, actor: User) -> User:
    _reject_self(target, actor)
    if not target.is_active:
        target.is_active = True
        target.token_epoch += 1
        db.commit()
        db.refresh(target)
    return target


def issue_password_reset(db: Session, target: User, actor: User) -> tuple[str, datetime]:
    _reject_self(target, actor)
    _reject_admin_credentials(target)
    if not target.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reative a conta antes de redefinir a palavra-passe.")
    return password_reset.issue(db, target, issued_by=actor)


def require_password_change(db: Session, target: User, actor: User) -> User:
    _reject_self(target, actor)
    _reject_admin_credentials(target)
    if not target.must_change_password:
        target.must_change_password = True
        db.commit()
        db.refresh(target)
    return target


def reset_mfa(db: Session, target: User, actor: User) -> User:
    _reject_self(target, actor)
    _reject_admin_credentials(target)
    if db.query(UserMfa).filter(UserMfa.user_id == target.id).first() is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta conta não tem autenticação de dois fatores.")
    mfa_service.remove_enrolment(db, target)
    return target
