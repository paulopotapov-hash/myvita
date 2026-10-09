"""
Single entry point for writing to the audit trail. Everything that needs to
log a security or clinical-access event calls `record_audit_event` (service
layer) or `audit_request` (routers, with a Request) — nothing else should
construct an AuditLog row directly.

Transaction semantics (deliberate — see docs/audit-logging.md):
  * Every row is written in its own short transaction on a DEDICATED pool
    (`AuditSessionLocal`). Sharing the request pool deadlocked under load:
    every pooled connection was held by a request waiting for its own audit
    connection (regression test in tests/test_audit_logging.py).
  * FAILURE/DENIED rows (bad login, CSRF, permission denied) are written even
    though the request itself fails — exactly the events an investigation
    needs, which a shared-transaction design would roll away.
  * If the audit write itself fails it is logged (never raised) so audit
    storage problems cannot take the clinical application down.
  * Metadata is sanitised here: allowlisted keys, scalar values, bounded
    sizes. Never pass passwords, JWTs, cookies, CSRF tokens or clinical
    payloads — see app/models/audit_log.py.
"""

import logging
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException, Request

from app.core.client_ip import get_client_ip as client_ip  # re-exported: see app/core/client_ip.py
from app.core.database import AuditSessionLocal
from app.core.request_context import get_request_id
from app.models.audit_log import AuditAction, AuditLog, AuditResult
from app.models.staff import Staff
from app.models.user import User

__all__ = [
    "ALLOWED_METADATA_KEYS",
    "audit_denials",
    "audit_request",
    "client_ip",
    "record_access",
    "record_audit_event",
    "record_denied_access",
    "sanitize_metadata",
]

logger = logging.getLogger("myvita.audit")

# Allowlist: only these metadata keys are ever persisted. Identifiers and
# small operational facts — never content. Extend deliberately, in review;
# tests/test_audit_metadata_policy.py fails if app code uses a key not listed.
ALLOWED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        # counts / operations
        "count",
        "updated_count",
        "operation",
        "filters",
        # request context
        "path",
        "method",
        "reason",
        "required_roles",
        "request_id",
        # identifiers (UUIDs / enum values, never names or content)
        "patient_id",
        "staff_id",
        "conversation_id",
        "appointment_id",
        "actor_staff_role",
        "staff_role",
        "target_role",
        "active",
        "status",
        "from",
        "to",
        # account lifecycle / MFA (booleans, stage codes, counters)
        "mfa",
        "stage",
        "forced",
        "recovery_codes_remaining",
        "expires_at",
        "via",
        "ticket",  # operator's reference to the verified request, never the reset link
        "delivery",  # reset-link delivery mode code (e.g. "disabled"), never the link
        "account_found",  # boolean: password-reset request matched an account
        # privacy-preserving identity of an unknown login email
        "email_masked",
        "email_fingerprint",
        # flags
        "initial_message",  # boolean: conversation opened with a first message
    }
)
# Defence in depth on top of the allowlist: a key that merely *mentions* one of
# these is dropped even if someone adds it to the allowlist by mistake. The
# allowed keys above do not match it (`initial_message` is a boolean flag and is
# matched only as a whole word `message`).
_SENSITIVE_KEY_PATTERN = re.compile(
    r"password|passwd|secret|token|authorization|cookie|csrf|session|api[_-]?key"
    r"|body|content|record|hash|text|note|(?<![a-z_])message(?![a-z_])",
    re.IGNORECASE,
)
_MAX_STRING = 200
_MAX_LIST = 25


def _bounded(value: str | None, max_length: int) -> str | None:
    """Keep attacker-controlled audit fields within their database columns."""
    return value[:max_length] if value is not None else None


def _scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        return value[:_MAX_STRING]
    # Enums: store their value, never repr() of a model instance.
    inner = getattr(value, "value", None)
    if isinstance(inner, str | int):
        return _scalar(inner)
    raise TypeError(type(value).__name__)


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Allowlisted keys, scalar (or flat list / one-level dict of scalars) values, bounded sizes.

    Anything else is dropped with a warning rather than persisted. Returns None
    when nothing survives so the column stays NULL instead of `{}`.
    """
    if not metadata:
        return None
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or key not in ALLOWED_METADATA_KEYS or _SENSITIVE_KEY_PATTERN.search(key):
            logger.warning("Dropping disallowed audit metadata key: %s", str(key)[:50])
            continue
        try:
            if isinstance(value, list | tuple | set | frozenset):
                clean[key] = [_scalar(item) for item in list(value)[:_MAX_LIST]]
            elif isinstance(value, dict):
                clean[key] = {
                    k[:50]: _scalar(v)
                    for k, v in list(value.items())[:_MAX_LIST]
                    if isinstance(k, str) and not _SENSITIVE_KEY_PATTERN.search(k)
                }
            else:
                clean[key] = _scalar(value)
        except TypeError:
            logger.warning("Dropping audit metadata key with unsupported value type: %s", key)
    return clean or None


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
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist one audit row in its own transaction on the audit pool.

    Deliberately independent of whatever session the calling request is
    using: a failed login, a denied permission, or a request whose main
    transaction later rolls back must still leave a record.

    `request_id` defaults to the current request's ID from the ContextVar, so
    service-layer callers get correlation for free. The actor's staff role is
    attached when known so investigations do not need a second lookup.
    """
    if request_id is None:
        current = get_request_id()
        request_id = current if current != "-" else None
    session = AuditSessionLocal()
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
                request_id=_bounded(request_id, 64),
                event_metadata=sanitize_metadata(audit_metadata),
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


def audit_request(
    request: Request,
    *,
    action: AuditAction,
    actor: User | None,
    result: AuditResult = AuditResult.SUCCESS,
    resource_type: str | None = None,
    resource_id: uuid.UUID | str | None = None,
    clinic_id: uuid.UUID | str | None = None,
    actor_email: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Request-aware entry point for routers and security dependencies.

    Actor identity and clinic default to the authenticated user. Pass
    `clinic_id` when the resource's clinic is the right scope (e.g. clinic
    onboarding) and `actor_email` for anonymous failures (unknown login).
    """
    record_audit_event(
        action=action,
        result=result,
        clinic_id=clinic_id if clinic_id is not None else (actor.clinic_id if actor is not None else None),
        actor_user_id=actor.id if actor is not None else None,
        actor_email=actor_email if actor_email is not None else (actor.email if actor is not None else None),
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
        metadata=metadata,
    )


def record_access(
    request: Request,
    user: User,
    action: AuditAction,
    resource_type: str,
    resource_id: uuid.UUID | str | None,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Audit a successful action by the authenticated user, under the actor's own clinic."""
    audit_request(
        request,
        action=action,
        actor=user,
        result=AuditResult.SUCCESS,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
    )


def record_denied_access(
    request: Request, user: User, resource_type: str, resource_id: uuid.UUID | str
) -> None:
    """Audit a 403/404 on a clinical resource under the ACTOR's clinic, never the target's."""
    audit_request(
        request,
        action=AuditAction.PERMISSION_DENIED,
        actor=user,
        result=AuditResult.DENIED,
        resource_type=resource_type,
        resource_id=resource_id,
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
