"""
TOTP multi-factor authentication primitives (RFC 6238 / RFC 4226).

Design (see docs/security/account-lifecycle.md):
- TOTP with HMAC-SHA1, 6 digits, 30-second steps — the parameters every
  mainstream authenticator app supports. A code is accepted for the
  current step and one step either side (clock drift), and a step can be
  used at most once (`last_used_step`), so an observed code cannot be
  replayed.
- The seed is encrypted at rest with AES-256-GCM. The key lives outside
  the database (MFA_ENCRYPTION_KEY) and the user id is bound as associated
  data, so a ciphertext copied onto another user's row does not decrypt.
- Recovery codes are random, single-use, and stored as HMAC-SHA256 under a
  key derived from the same secret (a database dump alone cannot be
  brute-forced offline).
- Between password and code, the browser holds only a short-lived MFA
  challenge token signed with a key and `purpose` distinct from session
  tokens, so it can never be presented as a session.

Nothing in this module logs codes, seeds or tokens.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode

import jwt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
TOTP_ALLOWED_DRIFT_STEPS = 1
SECRET_BYTES = 20
RECOVERY_CODE_COUNT = 10
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
CHALLENGE_TTL_SECONDS = 300
CHALLENGE_PURPOSE = "mfa_challenge"
_CIPHERTEXT_VERSION = "v1"
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o/1/l/i ambiguity


class MfaSecretError(Exception):
    """The stored seed could not be decrypted (wrong key, tampering or row swap)."""


def _master_key() -> bytes:
    if settings.MFA_ENCRYPTION_KEY:
        return base64.urlsafe_b64decode(settings.MFA_ENCRYPTION_KEY.encode())
    # Development/test only: production refuses to start without an explicit
    # key (app/core/config.py).
    return hmac.new(settings.JWT_SECRET_KEY.encode(), b"myvita-mfa-dev-key-v1", hashlib.sha256).digest()


def _subkey(label: bytes) -> bytes:
    return hmac.new(_master_key(), label, hashlib.sha256).digest()


# --- TOTP ------------------------------------------------------------------


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode().rstrip("=")


def _decode_secret(secret: str) -> bytes:
    padding = "=" * (-len(secret) % 8)
    return base64.b32decode(secret.upper() + padding)


def hotp(secret: str, counter: int, *, digits: int = TOTP_DIGITS, digest: str = "sha1") -> str:
    message = struct.pack(">Q", counter)
    mac = hmac.new(_decode_secret(secret), message, digest).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // TOTP_PERIOD_SECONDS)


def totp(secret: str, *, step: int | None = None) -> str:
    return hotp(secret, current_step() if step is None else step)


def verify_totp(secret: str, code: str, *, last_used_step: int | None, now: float | None = None) -> int | None:
    """Return the matched time step, or None. Never accepts an already-used step."""
    candidate = code.strip().replace(" ", "")
    if len(candidate) != TOTP_DIGITS or not candidate.isdigit():
        return None
    step_now = current_step(now)
    matched: int | None = None
    for step in range(step_now - TOTP_ALLOWED_DRIFT_STEPS, step_now + TOTP_ALLOWED_DRIFT_STEPS + 1):
        # Compare every candidate (no early exit) in constant time.
        if hmac.compare_digest(hotp(secret, step), candidate) and matched is None:
            matched = step
    if matched is None or (last_used_step is not None and matched <= last_used_step):
        return None
    return matched


def provisioning_uri(secret: str, account_name: str) -> str:
    issuer = settings.MFA_ISSUER
    label = quote(f"{issuer}:{account_name}")
    query = urlencode(
        {"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": TOTP_DIGITS, "period": TOTP_PERIOD_SECONDS}
    )
    return f"otpauth://totp/{label}?{query}"


# --- Seed encryption -------------------------------------------------------


def encrypt_secret(secret: str, user_id: uuid.UUID) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_subkey(b"totp-seed-v1")).encrypt(nonce, secret.encode(), user_id.bytes)
    return f"{_CIPHERTEXT_VERSION}:{base64.urlsafe_b64encode(nonce + ciphertext).decode()}"


def decrypt_secret(stored: str, user_id: uuid.UUID) -> str:
    try:
        version, payload = stored.split(":", 1)
        if version != _CIPHERTEXT_VERSION:
            raise MfaSecretError("unknown ciphertext version")
        raw = base64.urlsafe_b64decode(payload.encode())
        plaintext = AESGCM(_subkey(b"totp-seed-v1")).decrypt(raw[:12], raw[12:], user_id.bytes)
    except (ValueError, InvalidTag) as exc:
        raise MfaSecretError("cannot decrypt MFA secret") from exc
    return plaintext.decode()


# --- Recovery codes --------------------------------------------------------


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    def one() -> str:
        chars = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        return f"{chars[:5]}-{chars[5:]}"

    return [one() for _ in range(count)]


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum())


def hash_recovery_code(code: str) -> str:
    return hmac.new(_subkey(b"recovery-code-v1"), normalize_recovery_code(code).encode(), hashlib.sha256).hexdigest()


def looks_like_recovery_code(code: str) -> bool:
    return len(normalize_recovery_code(code)) == 10 and not code.strip().isdigit()


# --- Login challenge -------------------------------------------------------


def create_challenge_token(user_id: uuid.UUID, token_epoch: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "epoch": token_epoch,
        "purpose": CHALLENGE_PURPOSE,
        "iat": now,
        "exp": now + timedelta(seconds=CHALLENGE_TTL_SECONDS),
    }
    return jwt.encode(payload, _subkey(b"mfa-challenge-v1"), algorithm="HS256")


def decode_challenge_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            _subkey(b"mfa-challenge-v1"),
            algorithms=["HS256"],
            options={"require": ["sub", "epoch", "purpose", "iat", "exp"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != CHALLENGE_PURPOSE:
        return None
    return payload
