"""
Application configuration.

All settings are loaded from environment variables (see .env.example).
Nothing sensitive is hardcoded here.
"""

import base64
import binascii
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# jwt.encode/decode also accepts "none" and asymmetric algorithms (RS*, ES*,
# EdDSA) we have no key material for. Restricting to the HMAC family we
# actually use closes off both a misconfiguration (typo'd env var silently
# picking "none") and the classic "alg confusion" class of JWT bugs.
_ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def siem_endpoint_problem(endpoint: str | None) -> str | None:
    """Why a SIEM endpoint is unacceptable, or None when it is fine.

    Only absolute HTTPS URLs, plus plain HTTP to a loopback host (local tests and
    a sidecar collector). This rules out file:, ftp: and other urllib schemes and
    cleartext audit export over a network. Shared by the settings validator and
    the HTTP sink so both enforce exactly the same rule.
    """
    parts = urlsplit(endpoint or "")
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "SIEM_ENDPOINT must be an absolute http(s) URL."
    if parts.scheme == "http" and parts.hostname not in _LOOPBACK_HOSTS:
        return "SIEM_ENDPOINT must use HTTPS (plain HTTP is only allowed to a loopback host)."
    return None
_DEVELOPMENT_DATABASE_URL = "postgresql+psycopg://myvita:myvita@db:5432/myvita"


def _is_32_byte_urlsafe_key(value: str) -> bool:
    try:
        return len(base64.urlsafe_b64decode(value.encode())) == 32
    except (ValueError, binascii.Error):
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "myVita API"
    # A free string here means a typo ("productoin") silently skips every
    # is_production-gated check below instead of failing loudly — Literal
    # makes pydantic reject it at startup instead.
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = Field(
        default=_DEVELOPMENT_DATABASE_URL,
        description="SQLAlchemy connection string (sync driver: psycopg).",
    )
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=120)

    # Auth / security
    JWT_SECRET_KEY: str = Field(
        ..., min_length=32, description="Must be set via environment, no default, >=32 bytes (RFC 7518 §3.2)."
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    COOKIE_NAME: str = "myvita_session"
    COOKIE_SECURE: bool = True  # False only for local http dev
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    MAX_REQUEST_BODY_BYTES: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    DOCUMENT_STORAGE_DIR: str = "./var/documents"
    # Upload limit for the private patient documents API (app/main.py exempts that
    # route from MAX_REQUEST_BODY_BYTES up to this size). The default aligns with
    # the production reverse-proxy allowance.
    DOCUMENT_MAX_UPLOAD_BYTES: int = Field(default=10_485_760, ge=1_024, le=104_857_600)

    # Public account creation is useful during local development, but must
    # be an explicit operational decision for a controlled clinic rollout.
    # Production Compose defaults both switches to false; operators may
    # temporarily enable clinic onboarding during a supervised bootstrap.
    ALLOW_PUBLIC_CLINIC_ONBOARDING: bool = False
    ALLOW_PUBLIC_PATIENT_REGISTRATION: bool = False
    ALLOW_DIRECT_STAFF_CREATION: bool = False
    INVITATION_EXPIRE_HOURS: int = Field(default=24, ge=1, le=168)
    # Clinics that opted in to appear in the anonymous clinic directory (GET
    # /api/v1/clinics[/{id}]). Empty by default = no clinic is public (fail
    # closed). Only consulted while ALLOW_PUBLIC_PATIENT_REGISTRATION is true;
    # a signed-in user always sees their own clinic regardless. JSON list of
    # UUIDs, e.g. PUBLIC_CLINIC_IDS=["3f2a..."]; a malformed value fails startup.
    PUBLIC_CLINIC_IDS: list[UUID] = Field(default_factory=list)

    # Account lifecycle. Reset links are issued by a clinic admin and handed
    # over out of band; self-service delivery (e-mail/SMS) is deliberately
    # not implemented until a provider and identity-verification policy are
    # approved (docs/security/account-lifecycle.md).
    PASSWORD_RESET_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)

    # Staff MFA (TOTP). When true, staff and clinic admins can do nothing
    # except enrol MFA until they have done so. Must stay true in production.
    MFA_REQUIRED_FOR_STAFF: bool = True
    MFA_ISSUER: str = Field(default="myVita", min_length=1, max_length=64)
    # urlsafe-base64 encoding of 32 random bytes. Encrypts TOTP seeds at rest
    # and keys recovery-code hashes. Required (and distinct from
    # JWT_SECRET_KEY) in production; derived from JWT_SECRET_KEY elsewhere so
    # local development needs no extra secret.
    MFA_ENCRYPTION_KEY: str | None = None

    # Keys the fingerprints that let repeated attempts against one typed
    # e-mail address be correlated in logs/audit without storing it
    # (app/core/privacy.py). Dedicated so that rotating the session or MFA
    # keys never breaks correlation and no key serves two purposes. Required
    # in production; derived from a fixed development label elsewhere.
    PRIVACY_FINGERPRINT_KEY: str | None = Field(default=None, min_length=32)

    # CSRF (double-submit cookie, HMAC-bound to the session)
    CSRF_COOKIE_NAME: str = "myvita_csrf"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    # CORS — methods/headers are deliberately explicit, not "*": the app
    # only ever needs these. See app/main.py for where they're applied.
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    CORS_ALLOW_METHODS: list[str] = Field(default_factory=lambda: ["GET", "POST", "PATCH", "DELETE"])
    CORS_ALLOW_HEADERS: list[str] = Field(
        default_factory=lambda: ["Content-Type", "X-CSRF-Token", "X-Request-ID"]
    )
    ALLOWED_HOSTS: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1", "testserver"])

    # IPs/CIDRs of reverse proxies allowed to set X-Forwarded-For — empty by
    # default, meaning NOTHING is trusted until explicitly configured (fail
    # closed). See app/core/client_ip.py. Example for a proxy on the same
    # Docker network: TRUSTED_PROXIES=["172.16.0.0/12"].
    TRUSTED_PROXIES: list[str] = Field(default_factory=list)

    # GET /metrics is disabled entirely (404) unless this is set — see
    # app/main.py. Not a general-purpose auth scheme, just enough to keep
    # metrics off the public internet by default without requiring a
    # network-level ACL to be configured before the app is usable at all.
    METRICS_TOKEN: str | None = None

    # Optional SIEM export (see docs/audit-logging.md § SIEM export). Disabled by
    # default: with SIEM_ENABLED=false nothing in the app opens a connection to
    # SIEM_ENDPOINT. Export runs out-of-band (scripts/export_audit_siem.py),
    # never inside a clinical request.
    SIEM_ENABLED: bool = False
    SIEM_ENDPOINT: str | None = None
    SIEM_API_KEY: SecretStr | None = None
    SIEM_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=60)
    SIEM_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    SIEM_CURSOR_FILE: str = "/var/lib/myvita/siem-cursor.json"

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def _jwt_algorithm_must_be_hmac(cls, v: str) -> str:
        if v not in _ALLOWED_JWT_ALGORITHMS:
            raise ValueError(f"JWT_ALGORITHM must be one of {sorted(_ALLOWED_JWT_ALGORITHMS)}, got {v!r}.")
        return v

    @model_validator(mode="after")
    def _siem_config_is_coherent(self) -> "Settings":
        if not self.SIEM_ENABLED:
            return self
        if not self.SIEM_ENDPOINT or not self.SIEM_ENDPOINT.startswith(("http://", "https://")):
            raise ValueError("SIEM_ENDPOINT must be an http(s) URL when SIEM_ENABLED=true.")
        if self.is_production and not self.SIEM_ENDPOINT.startswith("https://"):
            raise ValueError("SIEM_ENDPOINT must use HTTPS in production.")
        problem = siem_endpoint_problem(self.SIEM_ENDPOINT)
        if problem:
            raise ValueError(problem)
        return self

    @model_validator(mode="after")
    def _refuse_insecure_production_config(self) -> "Settings":
        if not self.is_production:
            return self
        if not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true when ENVIRONMENT=production.")
        if self.DATABASE_URL == _DEVELOPMENT_DATABASE_URL or "myvita:myvita@" in self.DATABASE_URL:
            raise ValueError("DATABASE_URL must use dedicated production credentials.")
        if not self.DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use PostgreSQL in production.")
        normalized_secret = self.JWT_SECRET_KEY.lower()
        if len(set(self.JWT_SECRET_KEY)) < 12 or any(
            marker in normalized_secret
            for marker in ("change-me", "not-a-real", "do-not-reuse", "example", "temporary")
        ):
            raise ValueError("JWT_SECRET_KEY is obviously unsuitable for production.")
        if "*" in self.CORS_ORIGINS:
            raise ValueError(
                "CORS_ORIGINS may not contain '*' when ENVIRONMENT=production "
                "(the app sends allow_credentials=True, and browsers reject — "
                "and CORS's own spec forbids — a wildcard origin combined "
                "with credentials; set explicit origins instead)."
            )
        if not self.CORS_ORIGINS:
            raise ValueError("CORS_ORIGINS must be set explicitly when ENVIRONMENT=production.")
        if any(not origin.startswith("https://") for origin in self.CORS_ORIGINS):
            raise ValueError("CORS_ORIGINS must use HTTPS in production.")
        if not self.ALLOWED_HOSTS or "*" in self.ALLOWED_HOSTS:
            raise ValueError("ALLOWED_HOSTS must contain explicit hostnames in production.")
        if any(host in {"localhost", "127.0.0.1", "testserver"} for host in self.ALLOWED_HOSTS):
            raise ValueError("ALLOWED_HOSTS must not contain local/test hosts in production.")
        if self.METRICS_TOKEN is not None and (
            len(self.METRICS_TOKEN) < 24 or len(set(self.METRICS_TOKEN)) < 10
        ):
            raise ValueError("METRICS_TOKEN is obviously unsuitable for production.")
        if self.ALLOW_DIRECT_STAFF_CREATION:
            raise ValueError("Direct staff creation is forbidden in production; use invitations.")
        if not self.MFA_REQUIRED_FOR_STAFF:
            raise ValueError("MFA_REQUIRED_FOR_STAFF must be true when ENVIRONMENT=production.")
        if not self.MFA_ENCRYPTION_KEY:
            raise ValueError("MFA_ENCRYPTION_KEY must be set explicitly when ENVIRONMENT=production.")
        if not _is_32_byte_urlsafe_key(self.MFA_ENCRYPTION_KEY):
            raise ValueError("MFA_ENCRYPTION_KEY must be the urlsafe-base64 encoding of exactly 32 bytes.")
        if self.MFA_ENCRYPTION_KEY == self.JWT_SECRET_KEY:
            raise ValueError("MFA_ENCRYPTION_KEY must differ from JWT_SECRET_KEY.")
        if not self.PRIVACY_FINGERPRINT_KEY:
            raise ValueError("PRIVACY_FINGERPRINT_KEY must be set explicitly when ENVIRONMENT=production.")
        if self.PRIVACY_FINGERPRINT_KEY in {self.JWT_SECRET_KEY, self.MFA_ENCRYPTION_KEY}:
            raise ValueError(
                "PRIVACY_FINGERPRINT_KEY must differ from JWT_SECRET_KEY and MFA_ENCRYPTION_KEY."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
