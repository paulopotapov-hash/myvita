import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.staff import StaffRole


class StaffCreateRequest(BaseModel):
    """Created by a clinic_admin for their own clinic — clinic_id is never
    taken from this payload, only from the admin's own session."""
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    staff_role: StaffRole
    specialty: str | None = Field(default=None, max_length=255)
    license_number: str | None = Field(default=None, max_length=50)


class StaffPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    full_name: str
    staff_role: StaffRole
    specialty: str | None

    model_config = {"from_attributes": True}
