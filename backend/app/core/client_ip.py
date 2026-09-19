"""
Single source of truth for "what is the client's IP address", used by both
rate limiting (app/core/rate_limit.py) and audit logging (app/core/audit.py).

Why this needs to exist at all: `X-Forwarded-For` is just an HTTP header —
any client can set it to anything, including a different value on every
request. If we trusted it unconditionally:
  - rate limiting becomes trivially bypassable (send a new fake XFF value
    per request and each one looks like a "new" IP)
  - the audit trail can be poisoned with fabricated IPs, or, running behind
    the reverse proxy `docker-compose.prod.yml` assumes, EVERY request looks
    like it came from the proxy's own IP if we ignore XFF entirely (which
    would silently collapse rate limiting to one shared bucket for every
    real user).

The fix used here is the standard one: only read X-Forwarded-For when the
immediate TCP peer (`request.client.host`) is itself a proxy we've been
told to trust. Otherwise, the raw socket peer is the answer — full stop.
"""
import ipaddress

from fastapi import Request

from app.core.config import settings


def _is_trusted_proxy(host: str) -> bool:
    if not host or not settings.TRUSTED_PROXIES:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    for entry in settings.TRUSTED_PROXIES:
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            # A malformed entry in TRUSTED_PROXIES shouldn't crash request
            # handling — it just never matches, which is the safe failure
            # mode (falls back to not trusting XFF).
            continue
    return False


def get_client_ip(request: Request) -> str:
    """
    Returns the socket peer's address, UNLESS that peer is in
    settings.TRUSTED_PROXIES (empty by default — nothing is trusted until
    explicitly configured), in which case the first address in
    X-Forwarded-For is used instead (the standard "closest-to-client" hop
    in a single-proxy chain — see README.md#production for multi-hop notes).
    """
    peer = request.client.host if request.client else None

    if peer and _is_trusted_proxy(peer):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            if candidate:
                return candidate

    return peer or "127.0.0.1"
