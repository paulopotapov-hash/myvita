import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MedicalRecordVisibility(str, enum.Enum):
    """Who may read a medical record besides the care team (P2.5).

    - INTERNAL: clinical team only. The default for every new record.
    - SHARED: a professional explicitly shared it with the patient; the record
      carries who made that decision and when.
    - LEGACY_SHARED: the record pre-dates the visibility model, when every
      record was readable by its patient. That access is preserved, but it is
      NOT a sharing decision: nobody is recorded as having shared it, and no
      notification was ever sent for it. A professional can confirm it
      (-> SHARED) or withdraw it (-> INTERNAL); it can never be re-entered.
    """

    INTERNAL = "internal"
    SHARED = "shared"
    LEGACY_SHARED = "legacy_shared"

    @property
    def patient_can_read(self) -> bool:
        return self in PATIENT_READABLE_VISIBILITIES


PATIENT_READABLE_VISIBILITIES = frozenset({MedicalRecordVisibility.SHARED, MedicalRecordVisibility.LEGACY_SHARED})

_VISIBILITY_ENUM = Enum(
    MedicalRecordVisibility,
    name="medical_record_visibility",
    values_callable=lambda e: [m.value for m in e],
)


class MedicalRecord(Base):
    __tablename__ = "medical_records"
    __table_args__ = (
        Index("ix_medical_records_clinic_patient", "clinic_id", "patient_id"),
        # Target of the composite notification foreign key (same-clinic guarantee).
        UniqueConstraint("id", "clinic_id", name="uq_medical_records_id_clinic"),
        ForeignKeyConstraint(
            ["visibility_changed_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_medical_records_visibility_staff_clinic",
            ondelete="RESTRICT",
        ),
        # An explicit share always names who decided and when; a legacy grant never does.
        CheckConstraint(
            "(patient_visibility = 'shared' AND visibility_changed_by_staff_id IS NOT NULL "
            "AND visibility_changed_at IS NOT NULL) OR "
            "(patient_visibility = 'legacy_shared' AND visibility_changed_by_staff_id IS NULL "
            "AND visibility_changed_at IS NULL) OR "
            "(patient_visibility = 'internal' AND "
            "(visibility_changed_by_staff_id IS NULL) = (visibility_changed_at IS NULL))",
            name="ck_medical_records_visibility_decision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    author_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    patient_visibility: Mapped[MedicalRecordVisibility] = mapped_column(
        _VISIBILITY_ENUM,
        nullable=False,
        default=MedicalRecordVisibility.INTERNAL,
        server_default=MedicalRecordVisibility.INTERNAL.value,
    )
    # Last explicit visibility decision (share or unshare). NULL for records never decided on.
    visibility_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visibility_changed_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    revisions = relationship(
        "MedicalRecordRevision", back_populates="record", order_by="MedicalRecordRevision.version"
    )


class MedicalRecordRevision(Base):
    """Append-only snapshot of a record at each version, including its visibility.

    Content edits and visibility decisions each create a revision; the editor is
    the professional who made the change. The runtime database role can insert
    revisions but never update or delete them (app/db_provisioning.py).
    """

    __tablename__ = "medical_record_revisions"
    __table_args__ = (UniqueConstraint("record_id", "version", name="uq_medical_record_revision"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medical_records.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    editor_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Visibility in force for this version (legacy_shared for history that pre-dates P2.5).
    patient_visibility: Mapped[MedicalRecordVisibility] = mapped_column(
        _VISIBILITY_ENUM,
        nullable=False,
        default=MedicalRecordVisibility.INTERNAL,
        server_default=MedicalRecordVisibility.INTERNAL.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    record = relationship("MedicalRecord", back_populates="revisions")
