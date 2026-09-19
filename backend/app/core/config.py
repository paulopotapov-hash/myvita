"""
Application configuration.

All settings are loaded from environment variables (see .env.example).
Nothing sensitive is hardcoded here.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# jwt.encode/decode also accepts "none" and asymmetric algorithms (RS*, ES*,
# EdDSA) we have no key material for. Restricting to the HMAC family we
# actually use closes off both a misconfiguration (typo'd env var silently
# picking "none") and the classic "alg confusion" class of JWT bugs.
_ALLOWED_JWT_ALGORITHMS = {"HS256", "HS384", "HS512"}


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
        default="postgresql+psycopg://myvita:myvita@db:5432/myvita",
        description="SQLAlchemy connection string (sync driver: psycopg).",
    )

    # Auth / security
    JWT_SECRET_KEY: str = Field(
        ..., min_length=32, description="Must be set via environment, no default, >=32 bytes (RFC 7518 §3.2)."
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    COOKIE_NAME: str = "myvita_session"
    COOKIE_SECURE: bool = True  # False only for local http dev
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

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

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def _jwt_algorithm_must_be_hmac(cls, v: str) -> str:
        if v not in _ALLOWED_JWT_ALGORITHMS:
            raise ValueError(
                f"JWT_ALGORITHM must be one of {sorted(_ALLOWED_JWT_ALGORITHMS)}, got {v!r}."
            )
        return v

    @model_validator(mode="after")
    def _refuse_insecure_production_config(self) -> "Settings":
        if not self.is_production:
            return self
        if not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true when ENVIRONMENT=production.")
        if "*" in self.CORS_ORIGINS:
            raise ValueError(
                "CORS_ORIGINS may not contain '*' when ENVIRONMENT=production "
                "(the app sends allow_credentials=True, and browsers reject — "
                "and CORS's own spec forbids — a wildcard origin combined "
                "with credentials; set explicit origins instead)."
            )
        if not self.CORS_ORIGINS:
            raise ValueError("CORS_ORIGINS must be set explicitly when ENVIRONMENT=production.")
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
