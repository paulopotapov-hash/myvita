"""add medical records, medications and notifications

Revision ID: b6f1c2d3e4a5
Revises: b5c0a9e71d42
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b6f1c2d3e4a5"
down_revision: str | None = "b5c0a9e71d42"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    medication_status = postgresql.ENUM(
        "active", "discontinued", "completed", name="medication_status", create_type=False
    )
    postgresql.ENUM("active", "discontinued", "completed", name="medication_status").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "medical_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("author_staff_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_staff_id"], ["staff.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medical_records_clinic_id", "medical_records", ["clinic_id"])
    op.create_index("ix_medical_records_patient_id", "medical_records", ["patient_id"])
    op.create_index("ix_medical_records_clinic_patient", "medical_records", ["clinic_id", "patient_id"])

    op.create_table(
        "medical_record_revisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("editor_staff_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["editor_staff_id"], ["staff.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["record_id"], ["medical_records.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("record_id", "version", name="uq_medical_record_revision"),
    )
    op.create_index("ix_medical_record_revisions_record_id", "medical_record_revisions", ["record_id"])

    op.create_table(
        "medications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("prescribed_by_staff_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("dosage", sa.String(length=200), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("status", medication_status, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["prescribed_by_staff_id"], ["staff.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medications_clinic_id", "medications", ["clinic_id"])
    op.create_index("ix_medications_patient_id", "medications", ["patient_id"])
    op.create_index("ix_medications_clinic_patient", "medications", ["clinic_id", "patient_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_clinic_id", "notifications", ["clinic_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])

    for value in (
        "medical_record_created", "medical_record_updated", "medication_created",
        "medication_updated", "notification_read", "medical_record_viewed", "medication_viewed",
    ):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("medications")
    op.drop_table("medical_record_revisions")
    op.drop_table("medical_records")
    sa.Enum(name="medication_status").drop(op.get_bind(), checkfirst=True)
    # Audit enum labels remain to preserve compatibility with existing audit rows.
