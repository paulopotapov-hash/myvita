"""
Application configuration.

All settings are loaded from environment variables (see .env.example).
Nothing sensitive is hardcoded here.
"""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    COOKIE_SAMESITE: str = "lax"

    # CORS
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
