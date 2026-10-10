import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConversationStatus(str, enum.Enum):
    """Where a clinical conversation stands for the care team (docs/clinical-messaging.md).

    Messages move it between the two waiting states automatically; nurses triage
    the non-closed states; only a doctor closes or reopens. CLOSED is read-only.
    """

    OPEN = "open"
    WAITING_FOR_PATIENT = "waiting_for_patient"
    WAITING_FOR_TEAM = "waiting_for_team"
    CLOSED = "closed"


class Conversation(Base):
    """
    A clinical thread between one patient and their care team, opened by one
    clinical staff member (doctor/nurse) of the same clinic. Participants are
    derived from patient.user_id and the patient's ACTIVE care assignments —
    there is no free-form participant list, so a conversation can never include
    an arbitrary user. `staff_id` is the professional who opened the thread.

    Invariant (DB-enforced via the composite FKs): conversation.clinic_id ==
    patient.clinic_id == staff.clinic_id. One conversation per (patient, staff) pair.
    """

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("patient_id", "staff_id", name="uq_conversations_patient_staff"),
        # Target of the composite notification foreign key (same-clinic guarantee).
        UniqueConstraint("id", "clinic_id", name="uq_conversations_id_clinic"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_conversations_patient_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["escalated_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_conversations_escalated_by_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["closed_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_conversations_closed_by_clinic",
            ondelete="RESTRICT",
        ),
        # A closed conversation always says who closed it and when; an open one never does.
        CheckConstraint(
            "(status = 'closed' AND closed_at IS NOT NULL AND closed_by_staff_id IS NOT NULL) OR "
            "(status <> 'closed' AND closed_at IS NULL AND closed_by_staff_id IS NULL)",
            name="ck_conversations_closed_state",
        ),
        # A pending doctor review always says who requested it and when.
        CheckConstraint(
            "NOT needs_doctor_review OR (escalated_at IS NOT NULL AND escalated_by_staff_id IS NOT NULL)",
            name="ck_conversations_escalation_state",
        ),
        Index("ix_conversations_clinic_updated", "clinic_id", "updated_at"),
        Index("ix_conversations_clinic_patient_status", "clinic_id", "patient_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Bumped on every new message so the inbox can sort by latest activity.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(
            ConversationStatus,
            name="conversation_lifecycle_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ConversationStatus.OPEN,
        server_default=ConversationStatus.OPEN.value,
    )
    # Nurse escalation: a doctor of the care team should review. Cleared by a doctor's reply or on close.
    needs_doctor_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class Message(Base):
    """
    Plain-text message in a conversation. "Read" is a single timestamp set by
    the other side: the patient for team messages, and the first care-team
    member who opens the thread for patient messages (a shared team flag).
    """

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sender_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
