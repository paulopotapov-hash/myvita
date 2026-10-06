"""
Single entry point for writing to the audit trail. Everything that needs to
log a security or clinical-access event calls `record_audit_event` — nothing
else should construct an AuditLog row directly.
"""
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException, Request

from app.core.client_ip import get_client_ip as client_ip  # re-exported: see app/core/client_ip.py
from app.core.database import SessionLocal
from app.models.audit_log import AuditAction, AuditLog, AuditResult
from app.models.staff import Staff
from app.models.user import User

__all__ = ["record_audit_event", "record_denied_access", "audit_denials", "client_ip"]

logger = logging.getLogger("myvita.audit")


def _bounded(value: str | None, max_length: int) -> str | None:
    """Keep attacker-controlled audit fields within their database columns."""
    return value[:max_length] if value is not None else None


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
        audit_metadata = dict(metadata or {})
        if actor_user_id is not None:
            actor_staff = (
                session.query(Staff.staff_role)
                .filter(Staff.user_id == actor_user_id, Staff.clinic_id == clinic_id)
                .scalar()
            )
            if actor_staff is not None:
                audit_metadata["actor_staff_role"] = actor_staff.value
        session.add(
            AuditLog(
                clinic_id=clinic_id,
                actor_user_id=actor_user_id,
                actor_email=_bounded(actor_email, 255),
                action=action,
                resource_type=_bounded(resource_type, 50),
                resource_id=resource_id,
                result=result,
                ip_address=_bounded(ip_address, 45),
                user_agent=_bounded(user_agent, 255),
                event_metadata=audit_metadata or None,
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


def record_denied_access(
    request: Request, user: User, resource_type: str, resource_id: uuid.UUID | str
) -> None:
    """Audit a 403/404 on a clinical resource under the ACTOR's clinic, never the target's."""
    record_audit_event(
        action=AuditAction.PERMISSION_DENIED,
        result=AuditResult.DENIED,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"path": request.url.path},
    )


@contextmanager
def audit_denials(
    request: Request, user: User, resource_type: str, resource_id: uuid.UUID | str
) -> Iterator[None]:
    """Audit any 403/404 raised inside the block, then let it propagate unchanged."""
    try:
        yield
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            record_denied_access(request, user, resource_type, resource_id)
        raise
