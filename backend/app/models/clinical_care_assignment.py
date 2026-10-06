import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClinicalCareAssignment(Base):
    """Explicit, revocable link between a clinic professional and a patient."""

    __tablename__ = "clinical_care_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_care_assignment_patient_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_care_assignment_staff_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["assigned_by_user_id"], ["users.id"], name="fk_care_assignment_assigned_by", ondelete="RESTRICT"
        ),
        Index("ix_care_assignments_clinic_patient_active", "clinic_id", "patient_id", "active"),
        Index(
            "uq_care_assignment_active_staff_patient",
            "staff_id",
            "patient_id",
            unique=True,
            postgresql_where=text("active IS TRUE"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
