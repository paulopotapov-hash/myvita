import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ColumnElement, DateTime, Enum, ForeignKey, Index, Integer, String, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.validators import normalize_email


class UserRole(str, enum.Enum):
    PATIENT = "patient"
    STAFF = "staff"
    CLINIC_ADMIN = "clinic_admin"


class User(Base):
    """
    Auth identity. One row per login-capable person.
    A User has at most one Patient profile OR one Staff profile
    (never both), enforced at the service layer.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )

    # Nullable because a brand-new clinic_admin creating a clinic doesn't
    # have a clinic yet at the instant the user row is created.
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Bumped on password change / forced logout to invalidate all
    # previously issued JWTs immediately (see core/security.py).
    token_epoch: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Set by a clinic admin (or on admin-assigned initial passwords). While
    # true, the session only allows changing the password — see
    # app/core/security.get_current_user.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    clinic = relationship("Clinic", back_populates="users")
    patient_profile = relationship("Patient", back_populates="user", uselist=False, cascade="all, delete-orphan")
    staff_profile = relationship("Staff", back_populates="user", uselist=False, cascade="all, delete-orphan")

    @staticmethod
    def email_matches(email: str) -> ColumnElement[bool]:
        """Case-insensitive lookup that also matches rows stored before normalisation."""
        return func.lower(User.email) == normalize_email(email)


# Emails are compared case-insensitively everywhere (see
# app/core/validators.normalize_email); this keeps "Ana@x.pt" and "ana@x.pt"
# from ever becoming two accounts, even for rows written before
# normalisation existed.
Index("uq_users_email_lower", func.lower(User.email), unique=True)
