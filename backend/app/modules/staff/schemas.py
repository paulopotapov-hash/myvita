import uuid

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel
from app.core.validators import NormalizedEmail, validate_password_strength
from app.models.staff import StaffRole


class StaffCreateRequest(RequestModel):
    """Created by a clinic_admin for their own clinic — clinic_id is never
    taken from this payload, only from the admin's own session."""
    full_name: str = Field(min_length=2, max_length=255)
    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=128)
    staff_role: StaffRole
    specialty: str | None = Field(default=None, max_length=255)
    license_number: str | None = Field(default=None, max_length=50)
    # The admin chose this password, so by default the person must replace
    # it at first login. Direct creation is a development path only;
    # production uses invitations, where the person sets their own password.
    require_password_change: bool = True

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
    is_active: bool

    model_config = {"from_attributes": True}
