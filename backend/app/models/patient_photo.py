"""Patient profile photo, approved by the patient's doctor (MyChart-style).

A photo identifies the patient: it is health data under the GDPR. The image lives in the
same private storage as clinical documents (never a public URL) and is served only to
whoever may see the patient (app/modules/patient_photos).

Rows per patient, at most one of each status (partial unique indexes):
- `pending`: uploaded, waiting for an associated doctor;
- `approved`: the one shown (avatar, staff file header);
- `rejected`: NO image any more, only the doctor's reason, kept so the patient can read it
  until they upload another photo (then the row is deleted).

Retention (decision of 2026-10-12): an image no longer in use is deleted at once and for
good, file and row: the previous approved photo when a new one is approved, a rejected
photo's image, a pending photo replaced by a newer upload, and whatever the patient
removes. Backups keep copies until they expire (docs/patient-photos.md). File deletion is
made reliable by `StorageDeletion`: queued in the same transaction that deletes the row,
done after the commit, retried by the background job if it failed.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.scheduling import _enum


class PatientPhotoStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PatientPhoto(Base):
    __tablename__ = "patient_photos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"], ["patients.id", "patients.clinic_id"], name="fk_patient_photos_patient_clinic", ondelete="RESTRICT"
        ),
        Index("uq_patient_photos_pending", "patient_id", unique=True, postgresql_where=text("status = 'pending'")),
        Index("uq_patient_photos_approved", "patient_id", unique=True, postgresql_where=text("status = 'approved'")),
        Index("uq_patient_photos_rejected", "patient_id", unique=True, postgresql_where=text("status = 'rejected'")),
        # A rejected photo keeps no image; every other one has exactly one.
        CheckConstraint(
            "(status = 'rejected' AND storage_key IS NULL AND rejection_reason IS NOT NULL) "
            "OR (status <> 'rejected' AND storage_key IS NOT NULL AND rejection_reason IS NULL)",
            name="ck_patient_photos_image",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[PatientPhotoStatus] = mapped_column(_enum(PatientPhotoStatus, "patient_photo_status"), nullable=False)
    # Opaque key in the document storage; NULL once the image is gone (rejected).
    storage_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff.id", ondelete="RESTRICT"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Shown to the patient; never logged or audited.
    rejection_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)


class StorageDeletion(Base):
    """A stored file to delete for good (patient photos). Queued in the transaction that
    deletes its row; `deleted_at` is set once the file is gone. The key is random and
    says nothing about anyone."""

    __tablename__ = "storage_deletions"
    __table_args__ = (Index("ix_storage_deletions_pending", "requested_at", postgresql_where=text("deleted_at IS NULL")),)

    storage_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
