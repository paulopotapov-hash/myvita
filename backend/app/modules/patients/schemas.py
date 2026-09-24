import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.validators import validate_password_strength


class PatientRegisterRequest(BaseModel):
    """Public self-registration payload: a patient joins an existing clinic."""

    clinic_id: uuid.UUID
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("password")
    @classmethod
    def password_not_trivial(cls, v: str) -> str:
        return validate_password_strength(v)


class PatientPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    full_name: str
    birth_date: date | None
    phone: str | None
    national_health_number: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class PatientUpdateRequest(BaseModel):
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=30)
    national_health_number: str | None = Field(default=None, max_length=30)

    @field_validator("phone", "national_health_number")
    @classmethod
    def strip_optional_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PatientUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self
