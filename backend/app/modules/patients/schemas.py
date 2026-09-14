import uuid
from datetime import date

from pydantic import BaseModel, EmailStr, Field


class PatientRegisterRequest(BaseModel):
    """Public self-registration payload: a patient joins an existing clinic."""
    clinic_id: uuid.UUID
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=30)


class PatientPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    full_name: str
    birth_date: date | None
    phone: str | None

    model_config = {"from_attributes": True}
