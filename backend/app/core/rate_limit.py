"""
Rate limiting (docs/rate-limiting.md).

Who is counted:
- Authenticated requests count per USER, never per IP: a clinic's staff share one
  public IP, so an IP bucket would let one busy colleague lock out the others, and would
  let one abusive account hide among them. The user comes from the signed session
  cookie (a forged one cannot be made without the server key); without a valid session
  the client IP is used (see `user_or_ip`).
- Public, unauthenticated endpoints (login, registration, clinic onboarding, password
  reset, public invitation links) count per client IP: there is no account yet.
- Login also counts FAILED attempts per account: 5 in 15 minutes per e-mail address
  (keyed by its privacy fingerprint, never the address itself), on top of the per-IP
  limit, so a slow distributed guess at one account is still stopped.

What is limited:
- Every clinical module router gets a per-user limit when it is included in the app
  (`module_limit`): generous for reads, tighter for writes, tighter still for document
  uploads, and very generous for notifications (the badges poll them).
- Specific endpoints keep their own decorators (`limiter.limit`), e.g. revealing the
  full NIF / NISS / Nº de utente: about 10 per hour per user.

Storage: in memory (`RATE_LIMIT_STORAGE_URI=memory://`), correct for the single backend
process deployed today. With more than one process or replica every process would keep
its own counters, so they must share Redis first (docs/rate-limiting.md).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status
from limits import RateLimitItem, parse_many
from slowapi import Limiter

from app.core.client_ip import get_client_ip
from app.core.config import settings

logger = logging.getLogger("myvita.rate_limit")


def user_or_ip(request: Request) -> str:
    """The session's user id if the request carries a validly signed session, else the
    client IP. Only the signature and expiry are checked here; the endpoint still does
    full authentication (a revoked session is refused there, and still counted here)."""
    token = request.cookies.get(settings.COOKIE_NAME)
    if token:
        from app.core.security import decode_access_token

        try:
            return f"user:{decode_access_token(token)['sub']}"
        except HTTPException:
            pass
    return f"ip:{get_client_ip(request)}"


# NOT slowapi's default get_remote_address: that reads request.client.host directly,
# which behind the reverse proxy would be the proxy's own IP on every request.
# get_client_ip only trusts X-Forwarded-For from configured TRUSTED_PROXIES.
limiter = Limiter(key_func=user_or_ip, storage_uri=settings.RATE_LIMIT_STORAGE_URI)


def per_ip(limit: str) -> Callable:
    """Decorator for public endpoints: counted per client IP."""
    return limiter.limit(limit, key_func=get_client_ip)


# Public endpoints (per IP). Generous enough for a person who mistypes a password a
# couple of times, tight enough to make credential stuffing and registration spam impractical.
LOGIN_RATE_LIMIT = "10/minute"
REGISTRATION_RATE_LIMIT = "5/minute"
INVITATION_PUBLIC_RATE_LIMIT = "10/minute"
# Unauthenticated password-reset endpoints: enough for a person retrying a link, too few
# to brute-force tokens or spray reset requests.
PASSWORD_RESET_RATE_LIMIT = "5/minute"
# Failed logins per account (e-mail fingerprint), whatever the IP.
FAILED_LOGINS_PER_ACCOUNT = "5/15minutes"

# Authenticated actions (per user): caps the blast radius of a compromised or misused
# session, not brute force.
AUTHENTICATED_WRITE_RATE_LIMIT = "20/minute"
# Full patient identifiers: a person looks up a few, a script scraping them stops quickly.
IDENTIFIER_REVEAL_RATE_LIMIT = "10/hour"

TOO_MANY = "Demasiados pedidos em pouco tempo. Espera um momento e tenta novamente."
ACCOUNT_LOCKED = "Demasiadas tentativas falhadas para esta conta. Tenta novamente dentro de 15 minutos."
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class ModuleLimits:
    """Per-user limits for one module's router. `special` maps (method, request path suffix)
    to a stricter limit for that endpoint (counted in its own bucket, as well as the
    module's write bucket)."""

    name: str
    read: str = "300/minute"
    write: str = "60/minute"
    special: dict[tuple[str, str], str] = field(default_factory=dict)


MODULE_LIMITS: dict[str, ModuleLimits] = {
    module.name: module
    for module in (
        ModuleLimits("appointments"),
        ModuleLimits("appointment_requests"),
        ModuleLimits("clinical_history"),
        ModuleLimits("clinical_results"),
        ModuleLimits("consents"),
        # Uploads are the heaviest writes (files on disk): a few per minute per user.
        ModuleLimits("documents", special={("POST", "/documents"): "10/minute;100/hour"}),
        ModuleLimits("medical_records"),
        ModuleLimits("medications"),
        ModuleLimits("messages"),
        # The header badges poll notifications: never in the way of a normal session.
        ModuleLimits("notifications", read="600/minute", write="120/minute"),
        ModuleLimits("patients"),
        # Profile photo uploads (per user): a few retries, never a stream of images.
        ModuleLimits("patient_photos", special={("POST", "/patient-photos"): "5/hour;20/day"}),
        ModuleLimits("scheduling"),
        ModuleLimits("staff"),
        ModuleLimits("users"),
        ModuleLimits("waitlist"),
    )
}


def _reject(request: Request, detail: str, reason: str) -> HTTPException:
    from app.core.audit import client_ip, record_audit_event
    from app.core.metrics import rate_limit_events_total
    from app.core.request_context import get_request_id
    from app.models import AuditAction, AuditResult

    rate_limit_events_total.inc()
    record_audit_event(
        action=AuditAction.RATE_LIMITED,
        result=AuditResult.DENIED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"path": request.url.path, "request_id": get_request_id(), "reason": reason},
    )
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail, headers={"Retry-After": "60"})


def _hit(items: list[RateLimitItem], *identifiers: str) -> bool:
    return all(limiter.limiter.hit(item, *identifiers) for item in items)


def module_limit(name: str) -> Callable[[Request], None]:
    """A router dependency: the per-user limits of module `name` (see MODULE_LIMITS)."""
    module = MODULE_LIMITS[name]
    read, write = parse_many(module.read), parse_many(module.write)
    special = {key: parse_many(value) for key, value in module.special.items()}

    def dependency(request: Request) -> None:
        if not limiter.enabled:
            return
        key = user_or_ip(request)
        # The request's own path: inside a router dependency the matched route only knows
        # its path relative to the router's prefix.
        path = request.url.path
        method = request.method
        buckets: list[tuple[str, list[RateLimitItem]]] = [("read", read) if method in _SAFE_METHODS else ("write", write)]
        for (special_method, suffix), items in special.items():
            if method == special_method and path.endswith(suffix):
                buckets.append((f"{special_method}:{suffix}", items))
        for bucket, items in buckets:
            if not _hit(items, "module", module.name, bucket, key):
                raise _reject(request, TOO_MANY, f"module:{module.name}:{bucket}")

    return dependency


def check_account_not_locked(request: Request, fingerprint: str) -> None:
    """Login: refuse (429) while this account has 5 failed attempts in 15 minutes."""
    if not limiter.enabled:
        return
    items = parse_many(FAILED_LOGINS_PER_ACCOUNT)
    if not all(limiter.limiter.test(item, "login-failures", fingerprint) for item in items):
        raise _reject(request, ACCOUNT_LOCKED, "account_login_failures")


def record_failed_login(fingerprint: str) -> None:
    if limiter.enabled:
        for item in parse_many(FAILED_LOGINS_PER_ACCOUNT):
            limiter.limiter.hit(item, "login-failures", fingerprint)


def clear_failed_logins(fingerprint: str) -> None:
    """A successful password step starts the account's count again."""
    if limiter.enabled:
        for item in parse_many(FAILED_LOGINS_PER_ACCOUNT):
            limiter.limiter.clear(item, "login-failures", fingerprint)
