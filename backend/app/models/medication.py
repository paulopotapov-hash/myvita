"""Tenant-scoped medication history."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
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


class Medication(Base):
    __tablename__ = "medications"
    __table_args__ = (
        Index("ix_medications_clinic_patient_active_created", "clinic_id", "patient_id", "is_active", "created_at"),
        Index("ix_medications_clinic_patient_start", "clinic_id", "patient_id", "start_date"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_medications_date_order"),
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_medications_patient_clinic",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[str] = mapped_column("dose", String(100), nullable=False)
    route: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frequency: Mapped[str] = mapped_column(String(100), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
