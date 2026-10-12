import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Kept in sync with migration 6b7c8d9e0f1a (constraint text is not autogenerate-compared).
_TARGET_COLUMNS = {
    "document": "target_id",
    "conversation": "conversation_target_id",
    "result": "result_target_id",
    "medical_record": "record_target_id",
    "appointment": "appointment_target_id",
    "patient": "patient_target_id",
}


def _target_type_check(columns: dict[str, str]) -> str:
    """Exactly one target column per target type, or none at all."""
    none = " AND ".join(f"{column} IS NULL" for column in columns.values())
    branches = [f"(target_type IS NULL AND {none})"]
    for kind, own in columns.items():
        others = " AND ".join(f"{column} IS NULL" for column in columns.values() if column != own)
        branches.append(f"(target_type = '{kind}' AND {own} IS NOT NULL AND {others})")
    return " OR ".join(branches)


# Kept in sync with migration d5e7f9a1b3c4 (constraint text is not autogenerate-compared).
TARGET_TYPE_CHECK = _target_type_check(_TARGET_COLUMNS)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        # Deep-link targets point at the live documents/conversations tables
        # (migration 5a6b7c8d9e0f); Parent A's clinical_* tables are deprecated.
        ForeignKeyConstraint(
            ["target_id", "clinic_id"],
            ["documents.id", "documents.clinic_id"],
            name="fk_notification_document_target",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["conversation_target_id", "clinic_id"],
            ["conversations.id", "conversations.clinic_id"],
            name="fk_notification_conversation_target",
            ondelete="CASCADE",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["result_target_id", "clinic_id"],
            ["clinical_results.id", "clinical_results.clinic_id"],
            name="fk_notification_result_target",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["record_target_id", "clinic_id"],
            ["medical_records.id", "medical_records.clinic_id"],
            name="fk_notification_record_target",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["appointment_target_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_notification_appointment_target",
            ondelete="CASCADE",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["patient_target_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_notification_patient_target",
            ondelete="CASCADE",
            use_alter=True,
        ),
        # Exactly one target column per target type (each has its own same-clinic foreign key).
        CheckConstraint(TARGET_TYPE_CHECK, name="ck_notification_target_type"),
        # Idempotency of domain events (app/modules/notifications/events.py): one
        # notification per recipient and event key, however often the event fires.
        Index(
            "uq_notifications_user_event_key",
            "user_id",
            "event_key",
            unique=True,
            postgresql_where=text("event_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    conversation_target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    result_target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    record_target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    appointment_target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    patient_target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Internal idempotency key, never exposed by the API.
    event_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
