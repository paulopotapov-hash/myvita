import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StaffRole(str, enum.Enum):
    DOCTOR = "doctor"
    NURSE = "nurse"
    PHYSIOTHERAPIST = "physiotherapist"
    ADMIN = "admin"


class Staff(Base):
    """Clinical/admin staff profile, scoped to exactly one clinic.
    Name lives on User.full_name — access via staff.user.full_name."""
    __tablename__ = "staff"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_staff_user_id"),
        UniqueConstraint("id", "clinic_id", name="uq_staff_id_clinic"),
        ForeignKeyConstraint(
            ["specialty_id", "clinic_id"],
            ["specialties.id", "specialties.clinic_id"],
            name="fk_staff_specialty_clinic",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    staff_role: Mapped[StaffRole] = mapped_column(
        Enum(StaffRole, name="staff_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    specialty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    license_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Scheduling: the bookable specialty (the free-text `specialty` above stays as the label)
    # and whether patients who never had an appointment with this professional may book.
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    accepts_new_patients: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="staff_profile")
    clinic = relationship("Clinic", back_populates="staff")
    # NO delete cascade: appointments.staff_id is ON DELETE RESTRICT — a
    # staff member who has appointment history cannot be hard-deleted
    # (that history is a clinical record). Deactivate via is_active-style
    # flag instead once that's added; don't delete the Staff row.
    appointments = relationship("Appointment", back_populates="staff")
