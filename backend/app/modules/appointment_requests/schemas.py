import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.schemas import RequestModel
from app.models.appointment_request import AppointmentRequestStatus


def _require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("must include a timezone")
    return value


class AppointmentRequestCreate(RequestModel):
    """Submitted by a patient. Patient, clinic and professional are never part of
    the payload: identity and clinic come from the session, the professional is
    chosen by staff on acceptance (unknown fields are rejected)."""

    preferred_start: datetime
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("preferred_start")
    @classmethod
    def preferred_start_has_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @field_validator("reason")
    @classmethod
    def blank_reason_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AppointmentRequestAccept(RequestModel):
    """Staff choose the professional and the actual slot."""

    staff_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_has_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)


class AppointmentRequestPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    preferred_start: datetime
    # None for callers who may not read clinical content (admins, non-clinical staff).
    reason: str | None
    status: AppointmentRequestStatus
    appointment_id: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
