import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.scheduling import BOOKING_SOURCE_ENUM, BookingSource


class AppointmentStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Appointment(Base):
    """
    A scheduled visit between a patient and a staff member, within one clinic.

    IMPORTANT invariant (enforced in the service layer, not the DB, because
    cross-row FK checks aren't expressible as a plain constraint):
    appointment.clinic_id MUST equal patient.clinic_id AND staff.clinic_id.
    Never trust clinic_id passed by the client — derive it from the
    authenticated user's session (see core/security.get_current_clinic_id).
    """

    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_clinic_scheduled_at", "clinic_id", "scheduled_at"),
        Index("ix_appointments_staff_scheduled_at", "staff_id", "scheduled_at"),
        # Target of same-clinic composite foreign keys (the care assignment a booking created).
        UniqueConstraint("id", "clinic_id", name="uq_appointments_id_clinic"),
        ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_types.id", "appointment_types.clinic_id"],
            name="fk_appointments_type_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rescheduled_from_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_appointments_rescheduled_from_clinic",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("rescheduled_from_id", name="uq_appointments_rescheduled_from"),
        # GiST exclusion constraints (no double booking of a professional or a patient)
        # live in migration 7d2e4b9a1c3f; see app/models/scheduling.py for why.
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(default=30, nullable=False)
    # Always scheduled_at + duration (set on every insert/update below); the exclusion
    # constraints compare [scheduled_at, ends_at) intervals.
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL for appointments created before appointment types existed (shown as "Consulta").
    appointment_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    booked_via: Mapped[BookingSource] = mapped_column(
        BOOKING_SOURCE_ENUM, nullable=False, default=BookingSource.STAFF, server_default="staff"
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status", values_callable=lambda e: [m.value for m in e]),
        default=AppointmentStatus.SCHEDULED,
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Who cancelled and when (NULL for cancellations before step 5).
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT", name="fk_appointments_cancelled_by"), nullable=True
    )
    # The appointment this one replaces (a reschedule); at most one successor each.
    rescheduled_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # The patient confirmed they will come (step 7, usually from the reminder).
    patient_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    clinic = relationship("Clinic", back_populates="appointments")
    patient = relationship("Patient", back_populates="appointments")
    staff = relationship("Staff", back_populates="appointments")


@event.listens_for(Appointment, "before_insert")
@event.listens_for(Appointment, "before_update")
def _keep_ends_at(_mapper: object, _connection: object, appointment: Appointment) -> None:
    """ends_at is derived, never set by hand: the exclusion constraints rely on it."""
    if appointment.duration_minutes is None:  # the column default is applied after this event
        appointment.duration_minutes = 30
    appointment.ends_at = appointment.scheduled_at + timedelta(minutes=appointment.duration_minutes)
