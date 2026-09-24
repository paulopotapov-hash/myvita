import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Patient(Base):
    """
    Clinical profile for a patient user, scoped to exactly one clinic.
    The patient's name lives on User.full_name (single source of truth) —
    access it via patient.user.full_name, don't duplicate it here.
    NOTE: MVP assumes a patient belongs to a single clinic. Supporting a
    patient registered at multiple clinics is a deliberate future change,
    not an oversight — revisit before allowing multi-clinic patients.
    """
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_patients_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    national_health_number: Mapped[str | None] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="patient_profile")
    clinic = relationship("Clinic", back_populates="patients")
    appointments = relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    # Consent history is intentionally not delete-orphan: DB RESTRICT keeps it durable.
    consents = relationship("Consent", back_populates="patient")
