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


class DocumentKind(str, enum.Enum):
    NOTE = "note"
    FILE = "file"


class ClinicalDocument(Base):
    __tablename__ = "clinical_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_documents_patient_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["author_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_documents_author_clinic",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "clinic_id", name="uq_document_id_clinic"),
        UniqueConstraint("id", "clinic_id", "patient_id", name="uq_document_scope"),
        CheckConstraint("current_version > 0", name="ck_document_current_version_positive"),
        Index("ix_documents_clinic_patient_updated", "clinic_id", "patient_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    author_staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[DocumentKind] = mapped_column(
        Enum(DocumentKind, name="document_kind", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    versions = relationship(
        "ClinicalDocumentVersion", back_populates="document", order_by="ClinicalDocumentVersion.version"
    )


class ClinicalDocumentVersion(Base):
    __tablename__ = "clinical_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_version"),
        CheckConstraint("version > 0", name="ck_document_version_positive"),
        CheckConstraint(
            "(content IS NOT NULL AND storage_key IS NULL AND original_filename IS NULL "
            "AND media_type IS NULL AND file_size IS NULL AND checksum_sha256 IS NULL) OR "
            "(content IS NULL AND storage_key IS NOT NULL AND original_filename IS NOT NULL "
            "AND media_type = 'application/pdf' AND file_size > 0 AND checksum_sha256 IS NOT NULL)",
            name="ck_document_version_payload",
        ),
        ForeignKeyConstraint(
            ["document_id", "clinic_id", "patient_id"],
            ["clinical_documents.id", "clinical_documents.clinic_id", "clinical_documents.patient_id"],
            name="fk_document_version_parent_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["author_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_document_version_author_clinic",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    author_staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    document = relationship("ClinicalDocument", back_populates="versions")
    author_staff = relationship("Staff", foreign_keys=[author_staff_id])
