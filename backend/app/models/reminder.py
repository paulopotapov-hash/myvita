"""Appointment reminders (step 7): one row per appointment and channel, written by the
background job (python -m app.jobs) when the reminder goes out.

Only the in-app channel is active. Email and SMS are prepared (the channel values exist
and the job asks each configured channel) but switched off: there is no sender for them,
and transactional e-mail never carries clinical information (app/core/email.py), so
turning them on needs its own decision and review.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.scheduling import _enum


class ReminderChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"  # prepared, not active
    SMS = "sms"  # prepared, not active


class ReminderStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"


class ReminderDelivery(Base):
    __tablename__ = "reminder_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_reminder_deliveries_appointment_clinic",
            ondelete="CASCADE",
        ),
        # Once per appointment and channel, however often the job runs.
        UniqueConstraint("appointment_id", "channel", name="uq_reminder_deliveries_appointment_channel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[ReminderChannel] = mapped_column(_enum(ReminderChannel, "reminder_channel"), nullable=False)
    status: Mapped[ReminderStatus] = mapped_column(_enum(ReminderStatus, "reminder_status"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
