import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


class ClinicOnboardingRequest(BaseModel):
    """
    Public endpoint payload: a new clinic self-registers along with its
    first admin user in a single step. This is intentionally unauthenticated
    (there's no user yet), which is why NIF/email uniqueness must be
    re-checked server-side — never trust that the frontend checked first.
    """
    clinic_name: str = Field(min_length=2, max_length=255)
    nif: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=30)

    admin_full_name: str = Field(min_length=2, max_length=255)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)

    @field_validator("admin_password")
    @classmethod
    def password_not_trivial(cls, v: str) -> str:
        if v.lower() in {"password", "12345678", "password123"}:
            raise ValueError("Password demasiado fraca.")
        return v


class ClinicPublic(BaseModel):
    id: uuid.UUID
    name: str
    nif: str | None
    address: str | None
    phone: str | None

    model_config = {"from_attributes": True}


class ClinicSummary(BaseModel):
    """Minimal, non-sensitive shape for public clinic pickers (e.g. patient sign-up)."""
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}
