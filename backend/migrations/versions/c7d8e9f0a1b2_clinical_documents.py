"""Add versioned patient-facing documents and notification targets.

Revision ID: c7d8e9f0a1b2
Revises: ab12cd34ef56
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "ab12cd34ef56"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for value in (
        "document_created",
        "document_updated",
        "document_viewed",
        "document_downloaded",
    ):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")
    postgresql.ENUM("note", "file", name="document_kind").create(op.get_bind(), checkfirst=True)
    document_kind = postgresql.ENUM("note", "file", name="document_kind", create_type=False)
    op.create_table(
        "clinical_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_staff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", document_kind, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"], ["patients.id", "patients.clinic_id"],
            name="fk_documents_patient_clinic", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["author_staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"],
            name="fk_documents_author_clinic", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_document_id_clinic"),
        sa.UniqueConstraint("id", "clinic_id", "patient_id", name="uq_document_scope"),
        sa.CheckConstraint("current_version > 0", name="ck_document_current_version_positive"),
    )
    op.create_index(
        "ix_documents_clinic_patient_updated", "clinical_documents", ["clinic_id", "patient_id", "updated_at"]
    )
    op.create_table(
        "clinical_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_staff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("media_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("storage_key", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_document_version_positive"),
        sa.CheckConstraint(
            "(content IS NOT NULL AND storage_key IS NULL AND original_filename IS NULL "
            "AND media_type IS NULL AND file_size IS NULL AND checksum_sha256 IS NULL) OR "
            "(content IS NULL AND storage_key IS NOT NULL AND original_filename IS NOT NULL "
            "AND media_type = 'application/pdf' AND file_size > 0 AND checksum_sha256 IS NOT NULL)",
            name="ck_document_version_payload",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "clinic_id", "patient_id"],
            ["clinical_documents.id", "clinical_documents.clinic_id", "clinical_documents.patient_id"],
            name="fk_document_version_parent_scope", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["author_staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"],
            name="fk_document_version_author_clinic", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version", name="uq_document_version"),
    )
    op.create_index("ix_clinical_document_versions_document_id", "clinical_document_versions", ["document_id"])
    op.add_column("notifications", sa.Column("target_type", sa.String(length=50), nullable=True))
    op.add_column("notifications", sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_check_constraint(
        "ck_notification_target_type",
        "notifications",
        "(target_type IS NULL AND target_id IS NULL) OR (target_type = 'document' AND target_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_notification_document_target", "notifications", "clinical_documents",
        ["target_id", "clinic_id"], ["id", "clinic_id"], ondelete="RESTRICT"
    )


def downgrade() -> None:
    op.drop_constraint("fk_notification_document_target", "notifications", type_="foreignkey")
    op.drop_constraint("ck_notification_target_type", "notifications", type_="check")
    op.drop_column("notifications", "target_id")
    op.drop_column("notifications", "target_type")
    op.drop_index("ix_clinical_document_versions_document_id", table_name="clinical_document_versions")
    op.drop_table("clinical_document_versions")
    op.drop_index("ix_documents_clinic_patient_updated", table_name="clinical_documents")
    op.drop_table("clinical_documents")
    postgresql.ENUM(name="document_kind").drop(op.get_bind(), checkfirst=True)
