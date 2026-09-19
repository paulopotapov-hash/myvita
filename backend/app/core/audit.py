"""
Single entry point for writing to the audit trail. Everything that needs to
log a security or clinical-access event calls `record_audit_event` — nothing
else should construct an AuditLog row directly.
"""
import logging
import uuid
from typing import Any

from app.core.database import SessionLocal
from app.models.audit_log import AuditAction, AuditLog, AuditResult

logger = logging.getLogger("myvita.audit")


def record_audit_event(
    *,
    action: AuditAction,
    result: AuditResult,
    clinic_id: uuid.UUID | str | None = None,
    actor_user_id: uuid.UUID | str | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Writes one row in its OWN short-lived session/transaction, deliberately
    independent of whatever session the calling request is using.

    This is what makes the log reliable rather than decorative: a failed
    login, a denied permission, or a request whose main transaction later
    rolls back must still leave a record. If this reused the caller's
    session, a rollback there would silently erase the audit trail for
    exactly the events — failures, denials — that matter most to have a
    record of.

    Never pass passwords, JWTs, cookies, CSRF tokens, or clinical payloads
    in `metadata` — see app/models/audit_log.py.
    """
    session = SessionLocal()
    try:
        session.add(
            AuditLog(
                clinic_id=clinic_id,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result=result,
                ip_address=ip_address,
                user_agent=user_agent,
                event_metadata=metadata,
            )
        )
        session.commit()
    except Exception:
        # Audit logging must never take down the actual request. A failure
        # here is surfaced in the application log (so it isn't invisible)
        # but never re-raised.
        logger.exception("Failed to persist audit log entry: action=%s", action)
        session.rollback()
    finally:
        session.close()


def client_ip(request: Any) -> str | None:
    """Best-effort client IP: honors X-Forwarded-For (set by a trusted
    reverse proxy in production) before falling back to the raw socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
