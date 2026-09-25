import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.schemas import RequestModel
from app.models.appointment import AppointmentStatus


class AppointmentCreateRequest(RequestModel):
    """
    Created by staff/clinic_admin. clinic_id is deliberately NOT part of
    this payload — it's always taken from the authenticated staff member's
    own session (see core/security.get_current_clinic_id), never trusted
    from the client, so a request can't be aimed at another clinic.
    """

    patient_id: uuid.UUID
    staff_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_at must include a timezone")
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


class AppointmentUpdateRequest(RequestModel):
    patient_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    reason: str | None = Field(default=None, max_length=500)
    status: AppointmentStatus | None = None

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("scheduled_at must include a timezone")
        return value

    @model_validator(mode="after")
    def at_least_one_field_and_no_direct_cancel(self) -> "AppointmentUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        if self.status == AppointmentStatus.CANCELLED:
            raise ValueError("Use the cancellation endpoint.")
        return self
