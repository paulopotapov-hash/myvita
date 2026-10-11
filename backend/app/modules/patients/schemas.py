import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.core.pt_identifiers import is_valid_nif, is_valid_niss, is_valid_postal_code, is_valid_sns_number
from app.core.schemas import RequestModel
from app.core.validators import NormalizedEmail, validate_password_strength


class PatientRegisterRequest(RequestModel):
    """Public self-registration payload: a patient joins an existing clinic."""

    clinic_id: uuid.UUID
    full_name: str = Field(min_length=2, max_length=255)
    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=128)
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("password")
    @classmethod
    def password_not_trivial(cls, v: str) -> str:
        return validate_password_strength(v)


class PatientIdentifiersMasked(BaseModel):
    """Only the last three digits; the full values need the audited reveal endpoint."""

    nif: str | None
    niss: str | None
    national_health_number: str | None


class PatientIdentifiersRevealed(BaseModel):
    """Full identifiers. Served only by the audited reveal endpoint, with no-store."""

    nif: str | None
    niss: str | None
    national_health_number: str | None


class PatientAddress(BaseModel):
    street: str | None
    postal_code: str | None
    locality: str | None


class PatientPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    full_name: str
    birth_date: date | None
    phone: str | None
    address: PatientAddress
    identifiers: PatientIdentifiersMasked
    is_active: bool


class PatientIdentification(BaseModel):
    """Administrative identification card: name and masked identifiers, nothing clinical.

    Served to everyone allowed to see a patient's identifiers, including administrative
    staff and the clinic administrator, who have no access to the clinical file.
    """

    id: uuid.UUID
    full_name: str
    identifiers: PatientIdentifiersMasked
    can_edit: bool


class PatientSummary(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    full_name: str
    is_active: bool


def _strip(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _digits_only(value: str | None) -> str | None:
    """Accept the usual spaced formats ("123 456 789"); store digits only."""
    value = _strip(value)
    return value.replace(" ", "") if value is not None else None


class PatientUpdateRequest(RequestModel):
    """Contact data. The patient may change phone and address; the care team also the birth date.

    Identifiers (NIF, NISS, Nº de utente) have their own endpoint and permission.
    """

    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=30)
    address_street: str | None = Field(default=None, max_length=200)
    address_postal_code: str | None = Field(default=None, max_length=8)
    address_locality: str | None = Field(default=None, max_length=100)

    @field_validator("phone", "address_street", "address_postal_code", "address_locality")
    @classmethod
    def strip_optional_values(cls, value: str | None) -> str | None:
        return _strip(value)

    @field_validator("address_postal_code")
    @classmethod
    def postal_code_format(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_postal_code(value):
            raise PydanticCustomError("postal_code", "O código postal deve ter o formato 0000-000.")
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PatientUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self


class PatientIdentifiersUpdateRequest(RequestModel):
    """NIF, NISS and Nº de utente. An omitted field is unchanged; null clears it.

    Error messages never repeat the submitted value.
    """

    nif: str | None = Field(default=None, max_length=15)
    niss: str | None = Field(default=None, max_length=15)
    national_health_number: str | None = Field(default=None, max_length=15)

    @field_validator("nif", "niss", "national_health_number")
    @classmethod
    def normalise(cls, value: str | None) -> str | None:
        return _digits_only(value)

    @field_validator("nif")
    @classmethod
    def nif_check_digit(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_nif(value):
            raise PydanticCustomError("nif", "NIF inválido: confirma os 9 dígitos.")
        return value

    @field_validator("niss")
    @classmethod
    def niss_check_digit(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_niss(value):
            raise PydanticCustomError("niss", "NISS inválido: confirma os 11 dígitos.")
        return value

    @field_validator("national_health_number")
    @classmethod
    def sns_format(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_sns_number(value):
            raise PydanticCustomError("national_health_number", "O número de utente deve ter 9 dígitos.")
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PatientIdentifiersUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self


class CareAssignmentCreateRequest(RequestModel):
    staff_id: uuid.UUID


class CareAssignmentPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    staff_id: uuid.UUID
    assigned_by_user_id: uuid.UUID
    active: bool
    created_at: datetime
    ended_at: datetime | None

    model_config = {"from_attributes": True}
