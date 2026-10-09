import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, ForeignKeyConstraint, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppointmentRequestStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class AppointmentRequest(Base):
    """
    A patient's request for an appointment, reviewed by clinic staff.

    The patient proposes only a preferred time and an optional reason; the
    professional and the actual slot are chosen by staff on acceptance, which
    creates a normal Appointment through the existing scheduling service.
    PENDING is the only state that can change: -> ACCEPTED (appointment_id
    set), -> REJECTED (by staff) or -> CANCELLED (by the patient).

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
        Index("ix_appointment_requests_clinic_status_created", "clinic_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    preferred_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
