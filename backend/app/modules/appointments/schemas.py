import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.schemas import RequestModel
from app.models.appointment import AppointmentStatus
from app.models.scheduling import BookingMode


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
    """Staff and clinic-admin view: the identifiers scheduling workflows use."""

    view: Literal["staff"] = "staff"
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    staff_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int
    status: AppointmentStatus
    reason: str | None
    patient_confirmed_at: datetime | None = None  # the patient confirmed they will come (step 7)

    model_config = {"from_attributes": True}


class AppointmentPatientView(BaseModel):
    """Patient view: when, with whom (display name only) and why. No internal
    clinic, patient or staff identifiers; patients cannot resolve them anyway."""

    view: Literal["patient"] = "patient"
    id: uuid.UUID
    staff_name: str
    scheduled_at: datetime
    ends_at: datetime
    duration_minutes: int
    status: AppointmentStatus
    reason: str | None
    appointment_type: str  # "Consulta" for appointments created before appointment types
    specialty: str | None
    location: str | None  # the clinic's address
    # Step 5: whether the patient may still cancel or reschedule in the app, until when
    # (the clinic's deadline), and how it is rescheduled: "direct" (free slots) or
    # "request" (ask the clinic); None for appointments without a type.
    can_change: bool
    change_until: datetime | None
    booking_mode: BookingMode | None
    # Step 7: the patient's confirmation that they will come (from the reminder, or any time
    # before the start while it is active).
    patient_confirmed_at: datetime | None
    can_confirm: bool


AppointmentOut = Annotated[AppointmentPublic | AppointmentPatientView, Field(discriminator="view")]


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
        for name in ("patient_id", "staff_id", "scheduled_at", "duration_minutes", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} must not be null")
        if self.status == AppointmentStatus.CANCELLED:
            raise ValueError("Use the cancellation endpoint.")
        return self
