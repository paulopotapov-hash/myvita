"""
One-time password reset tokens.

Tokens are 384-bit random values handed to the user exactly once (by a
clinic admin, out of band); only their SHA-256 is stored. Completing a
reset revokes every session and every other outstanding reset token for
the account, and clears any forced-password-change flag. A reset does not
bypass MFA: the next login still requires the second factor.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import PasswordResetToken, User

_INVALID_TOKEN = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Ligação de redefinição inválida ou expirada.",
)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def revoke_outstanding(db: Session, user_id: object) -> None:
    """Mark every unused reset token for the user as spent (no commit)."""
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None)
    ).update({PasswordResetToken.used_at: datetime.now(UTC)}, synchronize_session=False)


def issue(db: Session, target: User, *, issued_by: User | None) -> tuple[str, datetime]:
    """`issued_by` is None only for the operator recovery tool (app/account_recovery.py)."""
    revoke_outstanding(db, target.id)
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
    db.add(
        PasswordResetToken(
            user_id=target.id,
            token_hash=_token_hash(token),
            created_by_user_id=issued_by.id if issued_by is not None else None,
            expires_at=expires_at,
        )
    )
    db.commit()
    return token, expires_at


def complete(db: Session, token: str, new_password: str) -> User:
    record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == _token_hash(token))
        .with_for_update()
        .first()
    )
    if record is None or record.used_at is not None or record.expires_at <= datetime.now(UTC):
        raise _INVALID_TOKEN
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise _INVALID_TOKEN
    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    user.token_epoch += 1
    revoke_outstanding(db, user.id)
    record.used_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user
