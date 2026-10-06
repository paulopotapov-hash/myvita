import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.schemas import RequestModel
from app.core.validators import NormalizedEmail, validate_password_strength
from app.models import InvitationStatus, StaffRole, UserRole


class StaffInvitationCreateRequest(RequestModel):
    email: NormalizedEmail
    full_name: str = Field(min_length=2, max_length=255)
    staff_role: StaffRole
    specialty: str | None = Field(default=None, max_length=255)


class PatientInvitationCreateRequest(RequestModel):
    email: NormalizedEmail
    full_name: str = Field(min_length=2, max_length=255)


class InvitationAcceptRequest(RequestModel):
    token: str = Field(min_length=40, max_length=200)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_not_trivial(cls, value: str) -> str:
        return validate_password_strength(value)


class InvitationPreviewRequest(RequestModel):
    token: str = Field(min_length=40, max_length=200)


class InvitationPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    staff_role: StaffRole | None
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime
    model_config = {"from_attributes": True}


class InvitationCreated(InvitationPublic):
    token: str


class InvitationPreview(BaseModel):
    clinic_name: str
    email: EmailStr
    full_name: str
    role: UserRole
    staff_role: StaffRole | None
    expires_at: datetime
