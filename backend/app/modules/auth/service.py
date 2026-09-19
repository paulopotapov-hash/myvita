import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import record_audit_event
from app.core.metrics import auth_failures_total
from app.core.security import hash_password, verify_password
from app.models import AuditAction, AuditResult, User

logger = logging.getLogger("myvita.auth")

# Precomputed once at import time so the "unknown email" branch below still
# pays the same Argon2 cost as a real login attempt. Without this, a request
# for a non-existent email returns in ~0ms while a wrong-password request for
# a real email takes as long as an Argon2 hash — an attacker can use that
# timing gap alone to enumerate which emails have accounts, even though the
# error message is identical either way.
_DUMMY_HASH = hash_password("not-a-real-password-used-only-for-timing")


def authenticate(
    db: Session,
    email: str,
    password: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    user = db.query(User).filter(User.email == email).first()

    # Deliberately identical error for "no such user" and "wrong password":
    # a different message would let an attacker enumerate registered emails.
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email ou palavra-passe incorretos.",
    )

    if user is None or not user.is_active:
        # Still run a full password verification against a dummy hash so
        # this branch takes roughly the same time as the "wrong password"
        # branch below — see _DUMMY_HASH comment.
        verify_password(password, _DUMMY_HASH)
        # Safe to log the reason server-side (unlike the HTTP response,
        # which must stay generic): this is for security monitoring, not
        # sent back to whoever made the request.
        logger.warning("Tentativa de login falhada (email desconhecido ou inativo): %s", email)
        auth_failures_total.inc()
        record_audit_event(
            action=AuditAction.LOGIN_FAILURE,
            result=AuditResult.FAILURE,
            actor_email=email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise invalid_credentials

    if not verify_password(password, user.hashed_password):
        logger.warning("Tentativa de login falhada (password incorreta): user_id=%s", user.id)
        auth_failures_total.inc()
        record_audit_event(
            action=AuditAction.LOGIN_FAILURE,
            result=AuditResult.FAILURE,
            clinic_id=user.clinic_id,
            actor_user_id=user.id,
            actor_email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise invalid_credentials

    logger.info("Login bem-sucedido: user_id=%s", user.id)
    record_audit_event(
        action=AuditAction.LOGIN_SUCCESS,
        result=AuditResult.SUCCESS,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return user
