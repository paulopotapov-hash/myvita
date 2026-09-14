import uuid

from pydantic import BaseModel, EmailStr, Field

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

    model_config = {"from_attributes": True}
