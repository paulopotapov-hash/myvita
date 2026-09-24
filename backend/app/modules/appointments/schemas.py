import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.appointment import AppointmentStatus


class AppointmentCreateRequest(BaseModel):
    """
    Created by staff/clinic_admin. clinic_id is deliberately NOT part of
    this payload — it's always taken from the authenticated staff member's
    own session (see core/security.get_current_clinic_id), never trusted
    from the client, so a request can't be aimed at another clinic.
    """

    model_config = ConfigDict(str_strip_whitespace=True)
    patient_id: uuid.UUID
    staff_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)

    @field_validator("scheduled_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("A data deve incluir timezone.")
        return value

    reason: str | None = Field(default=None, max_length=500)


class AppointmentUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    reason: str | None = Field(default=None, max_length=500)
    status: AppointmentStatus | None = None

    @field_validator("scheduled_at")
    @classmethod
    def require_timezone_when_present(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("A data deve incluir timezone.")
        return value


class AppointmentPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    staff_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int
    status: AppointmentStatus
    reason: str | None

    model_config = {"from_attributes": True}
