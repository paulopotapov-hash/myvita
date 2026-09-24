import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ConsentType(str, enum.Enum):
    TREATMENT = "treatment"
    DATA_PROCESSING = "data_processing"
    COMMUNICATIONS = "communications"
    RESEARCH = "research"


class ConsentStatus(str, enum.Enum):
    GRANTED = "granted"
    REVOKED = "revoked"


class Consent(Base):
    """A patient's immutable grant plus its optional revocation."""

    __tablename__ = "consents"
    __table_args__ = (
        CheckConstraint(
            "(status = 'granted' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL AND revoked_at >= granted_at)",
            name="ck_consents_lifecycle",
        ),
        Index("ix_consents_clinic_patient_created", "clinic_id", "patient_id", "created_at"),
        Index(
            "uq_consents_active_patient_type_purpose",
            "patient_id",
            "consent_type",
            "purpose",
            unique=True,
            postgresql_where=text("status = 'granted'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        Enum(ConsentType, name="consent_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ConsentStatus] = mapped_column(
        Enum(ConsentStatus, name="consent_status", values_callable=lambda e: [m.value for m in e]),
        default=ConsentStatus.GRANTED,
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    clinic = relationship("Clinic", back_populates="consents")
    patient = relationship("Patient", back_populates="consents")
    recorded_by = relationship("User")
