import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.schemas import RequestModel
from app.core.validators import validate_password_strength
from app.models.staff import StaffRole
from app.models.user import UserRole


class LoginRequest(RequestModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=1, max_length=128)


class PasswordChangeRequest(RequestModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_not_trivial(cls, value: str) -> str:
        return validate_password_strength(value)


class UserPublic(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    clinic_id: uuid.UUID | None
    staff_role: StaffRole | None = None
    patient_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}
