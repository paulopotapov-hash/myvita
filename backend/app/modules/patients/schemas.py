import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator

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

    model_config = {"from_attributes": True}


class PatientUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=30)
