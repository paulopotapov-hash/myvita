import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MedicationStatus(str, enum.Enum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    COMPLETED = "completed"


class Medication(Base):
    __tablename__ = "medications"
    __table_args__ = (Index("ix_medications_clinic_patient", "clinic_id", "patient_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    prescribed_by_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    dosage: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MedicationStatus] = mapped_column(
        Enum(MedicationStatus, name="medication_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=MedicationStatus.ACTIVE,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
