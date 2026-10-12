import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.schemas import RequestModel
from app.models.appointment_request import AppointmentRequestStatus, RequestPeriod


def _require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("must include a timezone")
    return value


class AppointmentRequestCreate(RequestModel):
    """Submitted by a patient. Patient and clinic are never part of the payload (identity
    and clinic come from the session; unknown fields are rejected).

    Either `preferred_start` (one time, the original form) or a preference window from
    `preferred_from`, optionally until `preferred_to`, on some weekdays (0 = Monday) and in
    the morning or afternoon. `appointment_type_id` and `staff_id` (a preferred
    professional; omit for any) are re-checked by the server. `reschedule_of_id` asks to
    move one of the patient's own appointments: the type is then that appointment's."""

    preferred_start: datetime | None = None
    preferred_from: date | None = None
    preferred_to: date | None = None
    preferred_weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    preferred_period: RequestPeriod | None = None
    appointment_type_id: uuid.UUID | None = None
    staff_id: uuid.UUID | None = None
    reschedule_of_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("preferred_start")
    @classmethod
    def preferred_start_has_timezone(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value) if value is not None else None

    @field_validator("preferred_weekdays")
    @classmethod
    def valid_weekdays(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Dias da semana inválidos.")
        return sorted(set(value))

    @field_validator("reason")
    @classmethod
    def blank_reason_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def one_kind_of_preference(self) -> "AppointmentRequestCreate":
        window = (self.preferred_from, self.preferred_to, self.preferred_weekdays, self.preferred_period)
        if self.preferred_start is not None and any(item is not None for item in window):
            raise ValueError("Indica uma data e hora ou um período, não ambos.")
        if self.preferred_start is None and self.preferred_from is None:
            raise ValueError("Indica a partir de quando preferes a consulta.")
        if self.preferred_to is not None and self.preferred_from is not None and self.preferred_to < self.preferred_from:
            raise ValueError("A data final tem de ser igual ou posterior à inicial.")
        if self.reschedule_of_id is not None and self.appointment_type_id is not None:
            raise ValueError("Numa remarcação, o tipo de consulta é o da consulta a remarcar.")
        return self


class AppointmentRequestAccept(RequestModel):
    """Staff choose the professional and the actual slot (duration: the request's
    appointment type, or 30 minutes, unless given)."""

    staff_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int | None = Field(default=None, ge=5, le=480)

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_has_timezone(cls, value: datetime) -> datetime:
        return _require_timezone(value)


class AppointmentRequestPropose(AppointmentRequestAccept):
    """Staff propose a time; the patient accepts or declines it."""


class AppointmentRequestPublic(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    preferred_start: datetime | None
    preferred_from: date | None
    preferred_to: date | None
    preferred_weekdays: list[int] | None
    preferred_period: RequestPeriod | None
    appointment_type: str | None  # name; None for requests without a type
    specialty: str | None
    # Names for everyone; the professionals' ids only for staff (None for the patient).
    staff_id: uuid.UUID | None
    staff_name: str | None  # the preferred professional (None: any)
    reschedule_of_id: uuid.UUID | None
    reschedule_of_start: datetime | None  # when the appointment to move is
    proposed_staff_id: uuid.UUID | None
    proposed_staff_name: str | None
    proposed_start: datetime | None
    proposed_duration_minutes: int | None
    # None for callers who may not read clinical content (admins, non-clinical staff).
    reason: str | None
    status: AppointmentRequestStatus
    appointment_id: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
