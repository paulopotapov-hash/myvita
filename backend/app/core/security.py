"""
Security primitives: password hashing, JWT issuing/verification, CSRF
protection, and FastAPI dependencies that enforce authentication + tenant
(clinic) scoping.

Design decisions (do not change without discussion):
- Passwords hashed with Argon2id (via passlib's argon2 backend).
- Sessions are httpOnly cookies carrying a JWT, NOT localStorage.
- Each JWT embeds a `token_epoch` matching the user's current epoch in DB.
  Bumping the user's epoch (e.g. on password change / forced logout)
  instantly invalidates all previously issued tokens without needing
  a token blocklist.
- CSRF: double-submit cookie, HMAC-signed and bound to (user_id, token_epoch).
  See the "CSRF protection" section below for the full rationale.
"""

import enum
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.staff import StaffRole
from app.models.user import User, UserRole


class ClinicalPermission(str, enum.Enum):
    """Central policy for Phase B resources; routers must not infer privileges."""

    PATIENT_DIRECTORY_READ = "patient_directory.read"
    PATIENT_UPDATE = "patient.update"
    APPOINTMENT_READ = "appointment.read"
    APPOINTMENT_MANAGE = "appointment.manage"
    MEDICAL_RECORD_READ = "medical_record.read"
    MEDICAL_RECORD_WRITE = "medical_record.write"
    MEDICATION_READ = "medication.read"
    MEDICATION_WRITE = "medication.write"
    CONSENT_READ = "consent.read"
    CONSENT_RECORD = "consent.record"
    STAFF_DIRECTORY_READ = "staff_directory.read"
    STAFF_MANAGE = "staff.manage"
    NOTIFICATION_READ = "notification.read"


_PATIENT_PERMISSIONS = frozenset(
    {
        ClinicalPermission.PATIENT_UPDATE,
        ClinicalPermission.APPOINTMENT_READ,
        ClinicalPermission.MEDICAL_RECORD_READ,
        ClinicalPermission.MEDICATION_READ,
        ClinicalPermission.CONSENT_READ,
        ClinicalPermission.CONSENT_RECORD,
        ClinicalPermission.STAFF_DIRECTORY_READ,
        ClinicalPermission.NOTIFICATION_READ,
    }
)
_CLINIC_ADMIN_PERMISSIONS = frozenset(
    {
        ClinicalPermission.PATIENT_DIRECTORY_READ,
        ClinicalPermission.PATIENT_UPDATE,
        ClinicalPermission.APPOINTMENT_READ,
        ClinicalPermission.APPOINTMENT_MANAGE,
        ClinicalPermission.STAFF_DIRECTORY_READ,
        ClinicalPermission.STAFF_MANAGE,
        ClinicalPermission.NOTIFICATION_READ,
    }
)
_STAFF_PERMISSIONS = {
    StaffRole.DOCTOR: frozenset(
        {
            ClinicalPermission.PATIENT_DIRECTORY_READ,
            ClinicalPermission.PATIENT_UPDATE,
            ClinicalPermission.APPOINTMENT_READ,
            ClinicalPermission.APPOINTMENT_MANAGE,
            ClinicalPermission.MEDICAL_RECORD_READ,
            ClinicalPermission.MEDICAL_RECORD_WRITE,
            ClinicalPermission.MEDICATION_READ,
            ClinicalPermission.MEDICATION_WRITE,
            ClinicalPermission.CONSENT_READ,
            ClinicalPermission.CONSENT_RECORD,
            ClinicalPermission.STAFF_DIRECTORY_READ,
            ClinicalPermission.NOTIFICATION_READ,
        }
    ),
    StaffRole.NURSE: frozenset(
        {
            ClinicalPermission.PATIENT_DIRECTORY_READ,
            ClinicalPermission.PATIENT_UPDATE,
            ClinicalPermission.APPOINTMENT_READ,
            ClinicalPermission.APPOINTMENT_MANAGE,
            ClinicalPermission.MEDICAL_RECORD_READ,
            ClinicalPermission.MEDICAL_RECORD_WRITE,
            ClinicalPermission.MEDICATION_READ,
            ClinicalPermission.CONSENT_READ,
            ClinicalPermission.CONSENT_RECORD,
            ClinicalPermission.STAFF_DIRECTORY_READ,
            ClinicalPermission.NOTIFICATION_READ,
        }
    ),
    StaffRole.ADMIN: frozenset(
        {
            ClinicalPermission.PATIENT_DIRECTORY_READ,
            ClinicalPermission.PATIENT_UPDATE,
            ClinicalPermission.APPOINTMENT_READ,
            ClinicalPermission.APPOINTMENT_MANAGE,
            ClinicalPermission.STAFF_DIRECTORY_READ,
            ClinicalPermission.NOTIFICATION_READ,
        }
    ),
}

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Methods that never require a CSRF token, per RFC 7231 they must not have
# side effects. OPTIONS is included so CORS preflight always succeeds.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "clinic_id": str(user.clinic_id) if user.clinic_id else None,
        "role": user.role.value,
        "epoch": user.token_epoch,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada.",
        ) from exc


# ---------------------------------------------------------------------------
# CSRF protection
#
# Strategy: double-submit cookie, HMAC-signed and bound to the session.
#
# On login/registration, alongside the httpOnly session cookie, we also set
# a SECOND cookie (myvita_csrf) that is deliberately NOT httpOnly, so
# frontend JavaScript can read it via document.cookie. The frontend must
# echo that value back in the `X-CSRF-Token` header on every state-changing
# request. A cross-site attacker can trick a victim's browser into sending
# cookies automatically, but — thanks to the same-origin policy — cannot
# read the CSRF cookie's value to also set the matching header, so a forged
# cross-site request will fail the check below.
#
# We go one step further than a plain double-submit cookie: the token is
# `<nonce>.<hmac>` where the HMAC is computed over (user_id, token_epoch,
# nonce) using the server's secret key. This means:
#   1. The token is unforgeable without the server secret (not just "any
#      string the client echoes back", which is a common weak
#      implementation of double-submit).
#   2. The token is automatically invalidated when the session is (logout,
#      forced logout, password change all bump token_epoch) — no separate
#      CSRF token store/expiry logic needed.
#   3. It is NOT the JWT itself — a leaked CSRF cookie alone cannot be used
#      to authenticate as the user (it's not accepted as a session token).
# ---------------------------------------------------------------------------


def _csrf_signing_key() -> bytes:
    """
    Derives a subkey for CSRF signing from JWT_SECRET_KEY instead of using
    the same secret bytes to key two different HMAC/JWT constructions.
    This is a defense-in-depth choice, not a strictly required one for the
    double-submit scheme to work — but it keeps a compromise of one
    signing context from having any bearing on the other, at zero extra
    configuration cost (no second secret to generate/rotate/leak).
    """
    return hmac.new(settings.JWT_SECRET_KEY.encode(), b"myvita-csrf-key-v1", hashlib.sha256).digest()


def _csrf_signature(user_id: str, token_epoch: int, nonce: str) -> str:
    message = f"{user_id}:{token_epoch}:{nonce}".encode()
    return hmac.new(_csrf_signing_key(), message, hashlib.sha256).hexdigest()


def generate_csrf_token(user: User) -> str:
    nonce = secrets.token_urlsafe(32)
    signature = _csrf_signature(str(user.id), user.token_epoch, nonce)
    return f"{nonce}.{signature}"


def _csrf_token_is_valid_for_user(token: str, user: User) -> bool:
    try:
        nonce, signature = token.split(".", 1)
    except ValueError:
        return False
    expected = _csrf_signature(str(user.id), user.token_epoch, nonce)
    # constant-time comparison — this is a security-sensitive equality check
    return hmac.compare_digest(expected, signature)


def _enforce_csrf(request: Request, user: User) -> None:
    """
    Raises 403 unless a valid, session-bound CSRF token is present as BOTH
    the myvita_csrf cookie and the X-CSRF-Token header, and they match.
    Only called for unsafe HTTP methods on already-authenticated requests.
    """
    cookie_token = request.cookies.get(settings.CSRF_COOKIE_NAME)
    header_token = request.headers.get(settings.CSRF_HEADER_NAME)

    if not cookie_token or not header_token:
        _audit_csrf_failure(request, user, "Token CSRF em falta.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF em falta.",
        )

    # Double-submit check: header must match cookie exactly (constant-time).
    if not hmac.compare_digest(cookie_token, header_token):
        _audit_csrf_failure(request, user, "Token CSRF inválido (cookie != header).")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF inválido.",
        )

    # Signature check: the cookie itself must be a genuine token this
    # server issued for THIS user's current session (not forged, not
    # replayed from a previous/different session after logout).
    if not _csrf_token_is_valid_for_user(cookie_token, user):
        _audit_csrf_failure(request, user, "Token CSRF inválido (assinatura/epoch).")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF inválido.",
        )


def _audit_csrf_failure(request: Request, user: User, reason: str) -> None:
    # Local import: app.core.audit imports app.models, which would otherwise
    # be a circular import at module load time (app.models.audit_log does
    # not import security, but keeping this import local avoids ever having
    # to think about import order between this module and app.models).
    from app.core.audit import client_ip, record_audit_event
    from app.models import AuditAction, AuditResult

    record_audit_event(
        action=AuditAction.CSRF_FAILURE,
        result=AuditResult.DENIED,
        clinic_id=user.clinic_id,
        actor_user_id=user.id,
        actor_email=user.email,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"reason": reason, "path": request.url.path},
    )


def _origin_is_allowed(request: Request) -> bool:
    """
    Defense-in-depth on top of the CSRF token check: if the browser sent an
    Origin header (it does on virtually all cross-site fetch/XHR/form
    submissions), it must match one of our configured CORS origins.
    We do NOT reject requests with no Origin header at all — some
    legitimate same-origin and non-browser clients omit it — the CSRF
    token check above is the primary defense either way.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return True
    return origin in settings.CORS_ORIGINS


def set_session_cookie(response: Response, user: User) -> None:
    token = create_access_token(user)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    csrf_token = generate_csrf_token(user)
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # frontend JS must be able to read this one
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.COOKIE_NAME, path="/")
    response.delete_cookie(key=settings.CSRF_COOKIE_NAME, path="/")


def get_current_user(
    request: Request,
    session_token: str | None = Cookie(default=None, alias=settings.COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolves the authenticated user from the httpOnly session cookie.
    Rejects the request if the token is missing, invalid, expired,
    stale (epoch mismatch -> forced logout happened), or the user is inactive.

    For any unsafe HTTP method (everything except GET/HEAD/OPTIONS), this
    ALSO enforces CSRF protection. Every endpoint that authenticates via
    this dependency (directly, or via require_roles/get_current_clinic_id)
    is automatically covered — no per-endpoint CSRF code needed.
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado.",
        )

    payload = decode_access_token(session_token)
    user = db.get(User, payload.get("sub"))

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilizador inválido.",
        )

    if user.token_epoch != payload.get("epoch"):
        # Password changed / admin forced logout / token was revoked.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada. Inicie sessão novamente.",
        )

    if request.method not in SAFE_METHODS:
        if not _origin_is_allowed(request):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Origem do pedido não permitida.",
            )
        _enforce_csrf(request, user)

    return user


def require_roles(*allowed_roles: UserRole) -> Callable[..., User]:
    """
    Dependency factory for endpoint-level authorization.
    Usage: Depends(require_roles(UserRole.STAFF, UserRole.CLINIC_ADMIN))
    """

    def _checker(request: Request, user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            from app.core.audit import client_ip, record_audit_event
            from app.models import AuditAction, AuditResult

            record_audit_event(
                action=AuditAction.PERMISSION_DENIED,
                result=AuditResult.DENIED,
                clinic_id=user.clinic_id,
                actor_user_id=user.id,
                actor_email=user.email,
                ip_address=client_ip(request),
                user_agent=request.headers.get("user-agent"),
                metadata={"path": request.url.path, "required_roles": [r.value for r in allowed_roles]},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sem permissões para aceder a este recurso.",
            )
        return user

    return _checker


def has_permission(user: User, permission: ClinicalPermission) -> bool:
    if user.role == UserRole.PATIENT:
        return permission in _PATIENT_PERMISSIONS
    if user.role == UserRole.CLINIC_ADMIN:
        return permission in _CLINIC_ADMIN_PERMISSIONS
    if user.role == UserRole.STAFF and user.staff_profile is not None:
        return permission in _STAFF_PERMISSIONS[user.staff_profile.staff_role]
    return False


def require_permission(permission: ClinicalPermission) -> Callable[..., User]:
    """Authorize one named capability and audit every denial."""

    def _checker(request: Request, user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            from app.core.audit import client_ip, record_audit_event
            from app.models import AuditAction, AuditResult

            record_audit_event(
                action=AuditAction.PERMISSION_DENIED,
                result=AuditResult.DENIED,
                clinic_id=user.clinic_id,
                actor_user_id=user.id,
                actor_email=user.email,
                ip_address=client_ip(request),
                user_agent=request.headers.get("user-agent"),
                metadata={"path": request.url.path, "required_permission": permission.value},
            )
            raise HTTPException(status_code=403, detail="Sem permissões para aceder a este recurso.")
        return user

    return _checker


def get_current_clinic_id(user: User = Depends(get_current_user)) -> str:
    """
    Every tenant-scoped query/endpoint MUST depend on this (directly or
    indirectly) and filter by it. Never trust a clinic_id coming from the
    request path/body/query params for authorization decisions.
    """
    if user.clinic_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Utilizador não está associado a nenhuma clínica.",
        )
    return str(user.clinic_id)
