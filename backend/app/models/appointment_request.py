import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppointmentRequestStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    PROPOSED = "proposed"  # the clinic proposed a time; the patient accepts or declines
    DECLINED = "declined"  # the patient declined the proposal


OPEN_REQUEST_STATUSES = (AppointmentRequestStatus.PENDING, AppointmentRequestStatus.PROPOSED)


class RequestPeriod(str, enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"


class AppointmentRequest(Base):
    """
    A patient's request for an appointment, reviewed by clinic staff.

    The patient gives either a single preferred time (the original form) or a
    preference window (dates, weekdays, morning/afternoon), optionally for an
    appointment type and a preferred professional, and optionally to move one of
    their appointments (`reschedule_of_id`). Staff accept it (choosing the
    professional and slot, which creates a normal Appointment through the
    scheduling service) or propose a time the patient answers.

    PENDING -> ACCEPTED (appointment_id set), REJECTED (by staff), CANCELLED (by
    the patient) or PROPOSED. PROPOSED -> ACCEPTED (the patient accepts), DECLINED
    (the patient declines), CANCELLED, REJECTED (staff withdraw it), or back to
    PENDING when the proposed slot was taken before the answer.

    clinic_id/patient_id always come from the authenticated patient; the
    composite FK guarantees the request belongs to the patient's clinic.
    """

    __tablename__ = "appointment_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_appointment_requests_patient_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_types.id", "appointment_types.clinic_id"],
            name="fk_appointment_requests_type_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"], name="fk_appointment_requests_staff_clinic", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["reschedule_of_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_appointment_requests_reschedule_of_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["proposed_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_appointment_requests_proposed_staff_clinic",
            ondelete="RESTRICT",
        ),
        Index("ix_appointment_requests_clinic_status_created", "clinic_id", "status", "created_at"),
        Index("ix_appointment_requests_reschedule_of", "reschedule_of_id"),
        CheckConstraint("preferred_start IS NOT NULL OR preferred_from IS NOT NULL", name="ck_appointment_requests_preference"),
        CheckConstraint(
            "preferred_to IS NULL OR (preferred_from IS NOT NULL AND preferred_to >= preferred_from)",
            name="ck_appointment_requests_window",
        ),
        CheckConstraint(
            "preferred_weekdays IS NULL OR (cardinality(preferred_weekdays) BETWEEN 1 AND 7 "
            "AND preferred_weekdays <@ ARRAY[0, 1, 2, 3, 4, 5, 6]::smallint[])",
            name="ck_appointment_requests_weekdays",
        ),
        CheckConstraint(
            "(proposed_start IS NULL) = (proposed_staff_id IS NULL) "
            "AND (proposed_start IS NULL) = (proposed_duration_minutes IS NULL) "
            "AND (proposed_duration_minutes IS NULL OR proposed_duration_minutes BETWEEN 5 AND 480)",
            name="ck_appointment_requests_proposal",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Either this single time (the original form) or the preference window below.
    preferred_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preferred_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    preferred_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 0 = Monday ... 6 = Sunday; NULL = any day.
    preferred_weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger), nullable=True)
    preferred_period: Mapped[RequestPeriod | None] = mapped_column(
        Enum(RequestPeriod, name="request_period", values_callable=lambda e: [m.value for m in e]), nullable=True
    )
    appointment_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # NULL: any professional
    reschedule_of_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # The clinic's proposal (status PROPOSED).
    proposed_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    proposed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proposed_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", name="fk_appointment_requests_proposed_by"), nullable=True
    )
    # Clinical content: visible only to the patient and doctors/nurses (same rule as Appointment.reason).
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[AppointmentRequestStatus] = mapped_column(
        Enum(
            AppointmentRequestStatus,
            name="appointment_request_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=AppointmentRequestStatus.PENDING,
        nullable=False,
    )
    # One request produces at most one appointment.
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
