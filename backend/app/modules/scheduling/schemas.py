import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas import RequestModel
from app.models import AbsenceKind, AppointmentStatus, BookingMode

# --- specialties and appointment types ----------------------------------------------------------


class SpecialtyCreate(RequestModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)


class SpecialtyUpdate(RequestModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None


class SpecialtyOut(BaseModel):
    id: uuid.UUID
    name: str
    active: bool

    model_config = {"from_attributes": True}


class AppointmentTypeCreate(RequestModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(ge=5, le=480)
    specialty_id: uuid.UUID
    booking_mode: BookingMode


class AppointmentTypeUpdate(RequestModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    specialty_id: uuid.UUID | None = None
    booking_mode: BookingMode | None = None
    active: bool | None = None


class AppointmentTypeOut(BaseModel):
    id: uuid.UUID
    name: str
    duration_minutes: int
    specialty_id: uuid.UUID
    booking_mode: BookingMode
    active: bool

    model_config = {"from_attributes": True}


# --- clinic settings --------------------------------------------------------------------------


class BookingSettings(BaseModel):
    """Per-clinic rules: cancellation/rescheduling deadline in the app, how long a waitlist
    offer stays open, when the reminder is sent and how far ahead patients may book."""

    cancellation_deadline_hours: int = Field(ge=0, le=336)
    waitlist_offer_minutes: int = Field(ge=5, le=2880)
    reminder_hours_before: int = Field(ge=1, le=168)
    booking_horizon_days: int = Field(ge=1, le=365)


class BookingSettingsUpdate(BookingSettings, RequestModel):
    model_config = ConfigDict(extra="forbid")


class BookingSettingsOut(BookingSettings):
    clinic_phone: str | None


# --- professionals, weekly schedules and absences -----------------------------------------------


class ProfessionalOut(BaseModel):
    id: uuid.UUID
    full_name: str
    staff_role: str
    specialty_id: uuid.UUID | None
    accepts_new_patients: bool


class ProfessionalUpdate(RequestModel):
    model_config = ConfigDict(extra="forbid")
    specialty_id: uuid.UUID | None = None
    accepts_new_patients: bool | None = None

    @model_validator(mode="after")
    def at_least_one(self) -> "ProfessionalUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self


class ScheduleRuleIn(RequestModel):
    model_config = ConfigDict(extra="forbid")
    weekday: int = Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday")
    start_time: time
    end_time: time
    valid_from: date | None = None
    valid_until: date | None = None
    appointment_type_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def coherent(self) -> "ScheduleRuleIn":
        if self.end_time <= self.start_time:
            raise ValueError("A hora de fim tem de ser depois da hora de início.")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("A data de fim da validade não pode ser anterior à de início.")
        return self


class WeeklyScheduleIn(RequestModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[ScheduleRuleIn] = Field(max_length=100)


class ScheduleRuleOut(BaseModel):
    id: uuid.UUID
    weekday: int
    start_time: time
    end_time: time
    valid_from: date | None
    valid_until: date | None
    appointment_type_ids: list[uuid.UUID]


class AbsenceIn(RequestModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: datetime
    ends_at: datetime
    kind: AbsenceKind

    @field_validator("starts_at", "ends_at")
    @classmethod
    def with_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Indica o fuso horário.")
        return value

    @model_validator(mode="after")
    def ordered(self) -> "AbsenceIn":
        if self.ends_at <= self.starts_at:
            raise ValueError("O fim da ausência tem de ser depois do início.")
        return self


class AbsenceOut(BaseModel):
    id: uuid.UUID
    staff_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    kind: AbsenceKind
    # Active appointments inside the period: never cancelled automatically, the clinic decides.
    conflicting_appointments: int = 0


# --- availability and agenda ------------------------------------------------------------------


class SlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    staff_id: uuid.UUID
    staff_name: str


class AgendaAppointment(BaseModel):
    id: uuid.UUID
    scheduled_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    patient_name: str
    appointment_type: str


class AgendaOut(BaseModel):
    staff_id: uuid.UUID
    appointments: list[AgendaAppointment]
    absences: list[AbsenceOut]
    rules: list[ScheduleRuleOut]
