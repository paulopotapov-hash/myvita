"""
Helpers for referring to attacker-supplied identifiers in logs and audit
metadata without recording them in full.

An email typed into the login or reset form may belong to someone who has
no account here (or be a typo of a real person's address); storing it
verbatim would make our logs a list of third-party personal data. Instead
we keep a masked form for humans and a keyed hash so repeated attempts
against the same address can still be correlated.

The hash is keyed with PRIVACY_FINGERPRINT_KEY, a secret used for nothing
else: rotating the session (JWT) or MFA keys must not change fingerprints,
and a key must never serve two purposes.
"""

import hashlib
import hmac

from app.core.config import settings

_DEVELOPMENT_KEY = b"myvita-development-only-fingerprint-key-v1"


def _fingerprint_key() -> bytes:
    if settings.PRIVACY_FINGERPRINT_KEY:
        return settings.PRIVACY_FINGERPRINT_KEY.encode()
    # Development/test only: production refuses to start without an explicit
    # key (app/core/config.py).
    return _DEVELOPMENT_KEY


def email_fingerprint(email: str) -> str:
    return hmac.new(_fingerprint_key(), email.strip().lower().encode(), hashlib.sha256).hexdigest()[:16]


def mask_email(email: str) -> str:
    local, _, domain = email.strip().lower().partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"
