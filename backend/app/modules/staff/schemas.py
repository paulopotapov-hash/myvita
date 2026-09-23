import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.validators import validate_password_strength
from app.models.staff import StaffRole


class StaffCreateRequest(BaseModel):
    """Created by a clinic_admin for their own clinic — clinic_id is never
    taken from this payload, only from the admin's own session."""

    model_config = ConfigDict(str_strip_whitespace=True)
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    staff_role: StaffRole
    specialty: str | None = Field(default=None, max_length=255)
    license_number: str | None = Field(default=None, max_length=50)

    @field_validator("password")
    @classmethod
    def password_not_trivial(cls, v: str) -> str:
        return validate_password_strength(v)


class StaffPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    full_name: str
    staff_role: StaffRole
    specialty: str | None
    license_number: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class StaffUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    staff_role: StaffRole | None = None
    specialty: str | None = Field(default=None, max_length=255)
    license_number: str | None = Field(default=None, max_length=50)
