import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.staff import StaffRole
from app.models.user import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    clinic_id: uuid.UUID | None
    staff_role: StaffRole | None = None
    patient_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}
