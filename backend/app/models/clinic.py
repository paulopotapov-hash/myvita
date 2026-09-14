import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Clinic(Base):
    """The tenant root. Every other clinical entity hangs off a clinic_id."""
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nif: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # NOTE: deliberately NO delete cascade here. clinic_id uses ON DELETE
    # RESTRICT at the DB level (see patients/staff/appointments FKs) so a
    # clinic with any data CANNOT be deleted, accidentally or otherwise.
    # An ORM-level cascade would delete the children before the DB gets a
    # chance to enforce that — do not add cascade="all, delete-orphan" here.
    users = relationship("User", back_populates="clinic")
    patients = relationship("Patient", back_populates="clinic")
    staff = relationship("Staff", back_populates="clinic")
    appointments = relationship("Appointment", back_populates="clinic")
