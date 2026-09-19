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
    ENVIRONMENT: str = Field(default="development")  # development | staging | production
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://myvita:myvita@db:5432/myvita",
        description="SQLAlchemy connection string (sync driver: psycopg).",
    )

    # Auth / security
    JWT_SECRET_KEY: str = Field(..., description="Must be set via environment, no default.")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    COOKIE_NAME: str = "myvita_session"
    COOKIE_SECURE: bool = True  # False only for local http dev
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    # CSRF (double-submit cookie, HMAC-bound to the session)
    CSRF_COOKIE_NAME: str = "myvita_csrf"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    # CORS
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

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
        if self.is_production and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true when ENVIRONMENT=production.")
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
