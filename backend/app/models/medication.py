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
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.clinical_history import HISTORY_ORIGIN_ENUM, HistoryOrigin


class MedicationStatus(str, enum.Enum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    COMPLETED = "completed"


class Medication(Base):
    __tablename__ = "medications"
    __table_args__ = (
        Index(
            "ix_medications_clinic_patient_status_created",
            "clinic_id",
            "patient_id",
            "status",
            "created_at",
        ),
        Index("ix_medications_clinic_patient_start", "clinic_id", "patient_id", "start_date"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_medications_date_order"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_medications_patient_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["confirmed_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_medications_confirmed_staff_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hidden_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_medications_hidden_staff_clinic",
            ondelete="RESTRICT",
        ),
        # A professional prescribes, with a dose, and is confirmed from the start (D6);
        # a patient's declaration names the patient's account and may lack the dose.
        CheckConstraint(
            "origin <> 'professional' OR (prescribed_by_staff_id IS NOT NULL AND dosage IS NOT NULL "
            "AND confirmed_at IS NOT NULL)",
            name="ck_medications_professional",
        ),
        CheckConstraint(
            "origin <> 'patient_declared' OR (declared_by_user_id IS NOT NULL AND prescribed_by_staff_id IS NULL)",
            name="ck_medications_patient_declared",
        ),
        CheckConstraint("(confirmed_at IS NULL) = (confirmed_by_staff_id IS NULL)", name="ck_medications_confirmation"),
        CheckConstraint(
            "(hidden_at IS NULL) = (hidden_by_staff_id IS NULL) AND (hidden_at IS NULL) = (hidden_reason IS NULL)",
            name="ck_medications_hidden",
        ),
        CheckConstraint(
            "(deleted_at IS NULL) = (deleted_by_user_id IS NULL) AND (deleted_at IS NOT NULL OR deletion_reason IS NULL)",
            name="ck_medications_deleted",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # NULL only for a patient's declaration (origin = patient_declared).
    prescribed_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Optional only in a patient's declaration (D6); the professional may complete it on confirmation.
    dosage: Mapped[str | None] = mapped_column(String(200), nullable=True)
    route: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(100), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MedicationStatus] = mapped_column(
        Enum(MedicationStatus, name="medication_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=MedicationStatus.ACTIVE,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Clinical history (commit 3): origin and confirmation, hiding from the patient (D4), soft delete.
    origin: Mapped[HistoryOrigin] = mapped_column(
        HISTORY_ORIGIN_ENUM, nullable=False, default=HistoryOrigin.PROFESSIONAL, server_default="professional"
    )
    declared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    confirmed_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    deletion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
