import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import Clinic, Invitation, InvitationStatus, Patient, Staff, StaffRole, User, UserRole


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_invitation(
    db: Session,
    *,
    clinic_id: uuid.UUID,
    inviter_id: uuid.UUID,
    email: str,
    full_name: str,
    role: UserRole,
    staff_role: StaffRole | None = None,
    specialty: str | None = None,
) -> tuple[Invitation, str]:
    normalized_email = email.strip().lower()
    if db.query(User).filter(User.email == normalized_email).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe uma conta com este email."
        )
    if role == UserRole.STAFF and staff_role is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Função profissional em falta."
        )
    if role not in {UserRole.STAFF, UserRole.PATIENT}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tipo de convite inválido."
        )

    now = datetime.now(UTC)
    db.query(Invitation).filter(
        Invitation.clinic_id == clinic_id,
        Invitation.email == normalized_email,
        Invitation.status == InvitationStatus.PENDING,
    ).update({Invitation.status: InvitationStatus.REVOKED}, synchronize_session=False)

    token = secrets.token_urlsafe(48)
    invitation = Invitation(
        clinic_id=clinic_id,
        invited_by_user_id=inviter_id,
        email=normalized_email,
        full_name=full_name.strip(),
        role=role,
        staff_role=staff_role,
        specialty=specialty.strip() if specialty else None,
        token_hash=_token_hash(token),
        expires_at=now + timedelta(hours=settings.INVITATION_EXPIRE_HOURS),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation, token


def get_pending_invitation(db: Session, token: str, *, lock: bool = False) -> Invitation:
    query = db.query(Invitation).filter(Invitation.token_hash == _token_hash(token))
    if lock:
        query = query.with_for_update()
    invitation = query.first()
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite inválido.")
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Convite já utilizado ou revogado.")
    if invitation.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Convite expirado.")
    return invitation


def accept_invitation(db: Session, token: str, password: str) -> tuple[Invitation, User]:
    invitation = get_pending_invitation(db, token, lock=True)
    if db.query(User).filter(User.email == invitation.email).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe uma conta com este email."
        )

    user = User(
        email=invitation.email,
        full_name=invitation.full_name,
        hashed_password=hash_password(password),
        role=invitation.role,
        clinic_id=invitation.clinic_id,
    )
    db.add(user)
    db.flush()
    if invitation.role == UserRole.STAFF:
        db.add(
            Staff(
                user_id=user.id,
                clinic_id=invitation.clinic_id,
                staff_role=invitation.staff_role,
                specialty=invitation.specialty,
            )
        )
    else:
        db.add(Patient(user_id=user.id, clinic_id=invitation.clinic_id))
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError:
        # Same email registered concurrently through another invitation: the
        # unique constraint on users.email wins and nothing is half-created.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe uma conta com este email."
        ) from None
    db.refresh(invitation)
    db.refresh(user)
    return invitation, user


def invitation_preview(db: Session, token: str) -> tuple[Invitation, Clinic]:
    invitation = get_pending_invitation(db, token)
    clinic = db.get(Clinic, invitation.clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite inválido.")
    return invitation, clinic


def list_invitations(
    db: Session,
    clinic_id: uuid.UUID,
    roles: set[UserRole],
    *,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Invitation], int]:
    """Pending invitations of one clinic (expired ones included, flagged by expires_at)."""
    query = db.query(Invitation).filter(
        Invitation.clinic_id == clinic_id,
        Invitation.role.in_(roles),
        Invitation.status == InvitationStatus.PENDING,
    )
    total = query.count()
    rows = (
        query.order_by(Invitation.created_at.desc(), Invitation.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def revoke_invitation(
    db: Session, invitation_id: uuid.UUID, clinic_id: uuid.UUID, roles: set[UserRole]
) -> Invitation:
    """Revokes a pending invitation of the caller's clinic. Another clinic's id is a 404."""
    invitation = (
        db.query(Invitation)
        .filter(
            Invitation.id == invitation_id,
            Invitation.clinic_id == clinic_id,
            Invitation.role.in_(roles),
        )
        .with_for_update()
        .first()
    )
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Convite não encontrado.")
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="O convite já não está pendente.")
    invitation.status = InvitationStatus.REVOKED
    db.commit()
    db.refresh(invitation)
    return invitation
