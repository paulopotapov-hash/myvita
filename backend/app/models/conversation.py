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
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ConversationStatus(str, enum.Enum):
    OPEN = "open"
    WAITING_FOR_PATIENT = "waiting_for_patient"
    WAITING_FOR_TEAM = "waiting_for_team"
    CLOSED = "closed"


class MessageSenderRole(str, enum.Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    NURSE = "nurse"


class ClinicalConversation(Base):
    __tablename__ = "clinical_conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_conversation_patient_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_conversation_creator_clinic",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "clinic_id", name="uq_conversation_id_clinic"),
        Index("ix_conversation_inbox", "clinic_id", "status", "updated_at"),
        Index("ix_conversation_patient", "clinic_id", "patient_id", "updated_at"),
        CheckConstraint("length(trim(subject)) > 0", name="ck_conversation_subject_nonempty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by_staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status", values_callable=lambda e: [item.value for item in e]),
        nullable=False,
        default=ConversationStatus.WAITING_FOR_PATIENT,
    )
    needs_doctor_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    patient_unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    team_unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    messages = relationship(
        "ClinicalMessage", back_populates="conversation", order_by="ClinicalMessage.created_at"
    )
    patient = relationship("Patient")


class ClinicalMessage(Base):
    __tablename__ = "clinical_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "clinic_id"],
            ["clinical_conversations.id", "clinical_conversations.clinic_id"],
            name="fk_message_conversation_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["sender_user_id"], ["users.id"], name="fk_message_sender_user", ondelete="RESTRICT"
        ),
        CheckConstraint("length(trim(body)) > 0", name="ck_message_body_nonempty"),
        CheckConstraint("sender_role IN ('patient', 'doctor', 'nurse')", name="ck_message_sender_role"),
        Index("ix_message_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sender_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_role: Mapped[MessageSenderRole] = mapped_column(
        Enum(MessageSenderRole, name="message_sender_role", values_callable=lambda e: [item.value for item in e]),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    conversation = relationship("ClinicalConversation", back_populates="messages")
