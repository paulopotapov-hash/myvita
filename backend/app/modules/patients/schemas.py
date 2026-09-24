import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.validators import validate_password_strength


class PatientRegisterRequest(BaseModel):
    """Public self-registration payload: a patient joins an existing clinic."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

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

    @field_validator("birth_date")
    @classmethod
    def birth_date_not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("A data de nascimento não pode estar no futuro.")
        return value

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)


class PatientPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    full_name: str
    birth_date: date | None
    phone: str | None
    national_health_number: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=30)
    national_health_number: str | None = Field(default=None, max_length=30)

    @field_validator("birth_date")
    @classmethod
    def birth_date_not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("A data de nascimento não pode estar no futuro.")
        return value

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)


def _validate_phone(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    allowed_punctuation = frozenset("+ -().")
    if any(not (character.isdigit() or character in allowed_punctuation) for character in value):
        raise ValueError("Número de telefone inválido.")
    digit_count = sum(character.isdigit() for character in value)
    if not 7 <= digit_count <= 15:
        raise ValueError("O telefone deve conter entre 7 e 15 dígitos.")
    return value
