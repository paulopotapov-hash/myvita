"""Scheduling (MyChart-style booking): specialties, appointment types, weekly schedules,
absences and per-clinic booking settings.

All times are stored in UTC (timestamptz). Weekly schedules are wall-clock times in the
clinic's time zone, Europe/Lisbon, and free slots are computed from them
(app/modules/scheduling/availability.py), so daylight-saving changes are handled when
slots are generated, never by shifting stored rules.

Overlapping bookings are prevented in the database, not only in the application:
migration 7d2e4b9a1c3f adds two GiST exclusion constraints on appointments (btree_gist),
one per professional and one per patient, over the half-open interval
[scheduled_at, ends_at) of active appointments. Adjacent appointments (one ends at
11:00, the next starts at 11:00) are allowed. Those constraints live only in the
migration: SQLAlchemy cannot reflect them, so declaring them here would make the
model/migration comparison report a phantom difference.
"""

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

CLINIC_TIME_ZONE = "Europe/Lisbon"


def _enum(enum_class: type[enum.Enum], name: str) -> Enum:
    return Enum(enum_class, name=name, values_callable=lambda e: [m.value for m in e])


class BookingMode(str, enum.Enum):
    DIRECT = "direct"  # "Marcação direta": the patient picks a free slot, confirmed at once
    REQUEST = "request"  # "Só por pedido": the patient asks; the clinic approves or proposes


class AbsenceKind(str, enum.Enum):
    VACATION = "vacation"
    OTHER = "other"  # no free text: the reason may be personal


class BookingSource(str, enum.Enum):
    STAFF = "staff"
    PATIENT = "patient"
    REQUEST = "request"
    WAITLIST = "waitlist"


class Specialty(Base):
    __tablename__ = "specialties"
    __table_args__ = (
        UniqueConstraint("clinic_id", "name", name="uq_specialties_clinic_name"),
        UniqueConstraint("id", "clinic_id", name="uq_specialties_id_clinic"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AppointmentType(Base):
    __tablename__ = "appointment_types"
    __table_args__ = (
        ForeignKeyConstraint(
            ["specialty_id", "clinic_id"],
            ["specialties.id", "specialties.clinic_id"],
            name="fk_appointment_types_specialty_clinic",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("clinic_id", "name", name="uq_appointment_types_clinic_name"),
        UniqueConstraint("id", "clinic_id", name="uq_appointment_types_id_clinic"),
        CheckConstraint("duration_minutes BETWEEN 5 AND 480", name="ck_appointment_types_duration"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    specialty_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    booking_mode: Mapped[BookingMode] = mapped_column(_enum(BookingMode, "booking_mode"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ClinicBookingSettings(Base):
    """Per-clinic booking rules. A clinic without a row uses the defaults below."""

    __tablename__ = "clinic_booking_settings"
    __table_args__ = (
        CheckConstraint("cancellation_deadline_hours BETWEEN 0 AND 336", name="ck_booking_settings_deadline"),
        CheckConstraint("waitlist_offer_minutes BETWEEN 5 AND 2880", name="ck_booking_settings_offer"),
        CheckConstraint("reminder_hours_before BETWEEN 1 AND 168", name="ck_booking_settings_reminder"),
        CheckConstraint("booking_horizon_days BETWEEN 1 AND 365", name="ck_booking_settings_horizon"),
    )

    DEFAULT_CANCELLATION_DEADLINE_HOURS = 24
    DEFAULT_WAITLIST_OFFER_MINUTES = 60
    DEFAULT_REMINDER_HOURS_BEFORE = 24
    DEFAULT_BOOKING_HORIZON_DAYS = 90

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), primary_key=True
    )
    cancellation_deadline_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")
    waitlist_offer_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    reminder_hours_before: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")
    booking_horizon_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ScheduleRule(Base):
    """One weekly block of a professional's agenda: weekday + wall-clock hours (Europe/Lisbon)."""

    __tablename__ = "schedule_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_schedule_rules_staff_clinic",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "clinic_id", name="uq_schedule_rules_id_clinic"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_schedule_rules_weekday"),
        CheckConstraint("end_time > start_time", name="ck_schedule_rules_hours"),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from", name="ck_schedule_rules_validity"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0 = Monday ... 6 = Sunday
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScheduleRuleType(Base):
    """Appointment types allowed in a schedule block (same clinic guaranteed by composite keys)."""

    __tablename__ = "schedule_rule_types"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rule_id", "clinic_id"],
            ["schedule_rules.id", "schedule_rules.clinic_id"],
            name="fk_schedule_rule_types_rule_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_types.id", "appointment_types.clinic_id"],
            name="fk_schedule_rule_types_type_clinic",
            ondelete="RESTRICT",
        ),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    appointment_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )


class ScheduleAbsence(Base):
    """A professional's blocked period (holidays, unforeseen). No free-text reason."""

    __tablename__ = "schedule_absences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_schedule_absences_staff_clinic",
            ondelete="RESTRICT",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_schedule_absences_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[AbsenceKind] = mapped_column(_enum(AbsenceKind, "absence_kind"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


BOOKING_SOURCE_ENUM = _enum(BookingSource, "booking_source")
