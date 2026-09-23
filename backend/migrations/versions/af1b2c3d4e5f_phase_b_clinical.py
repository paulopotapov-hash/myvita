"""Phase B clinical tables and audit actions.

Revision ID: af1b2c3d4e5f
Revises: 76dad50950ee
"""
from alembic import op
import sqlalchemy as sa

revision = "af1b2c3d4e5f"
down_revision = "76dad50950ee"
branch_labels = None
depends_on = None

ACTIONS = [
    "medical_record_created", "medical_record_updated", "medical_record_viewed",
    "medication_created", "medication_updated", "medication_viewed",
    "consent_recorded", "consent_viewed",
]


def upgrade() -> None:
    for action in ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")
    for table, columns in (
        ("medical_records", [
            sa.Column("author_user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("title", sa.String(255), nullable=False), sa.Column("content", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]),
        ("medications", [
            sa.Column("name", sa.String(255), nullable=False), sa.Column("dose", sa.String(100), nullable=False),
            sa.Column("frequency", sa.String(100), nullable=False), sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date()), sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("notes", sa.Text()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]),
        ("consents", [
            sa.Column("recorded_by_user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("consent_type", sa.String(100), nullable=False), sa.Column("status", sa.String(20), nullable=False),
            sa.Column("version", sa.String(50), nullable=False),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        ]),
        ("notifications", [
            sa.Column("recipient_user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("title", sa.String(255), nullable=False), sa.Column("message", sa.Text(), nullable=False),
            sa.Column("kind", sa.String(50), nullable=False), sa.Column("is_read", sa.Boolean(), nullable=False),
        ]),
    ):
        base = [
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("clinic_id", sa.UUID(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False),
        ]
        if table != "notifications":
            base.append(sa.Column("patient_id", sa.UUID(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False))
        op.create_table(table, *base, *columns, sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_medical_records_clinic_patient_created", "medical_records", ["clinic_id", "patient_id", "created_at"])
    op.create_index("ix_medications_clinic_patient", "medications", ["clinic_id", "patient_id"])
    op.create_index("ix_consents_clinic_patient_created", "consents", ["clinic_id", "patient_id", "created_at"])
    op.create_index("ix_notifications_recipient_created", "notifications", ["recipient_user_id", "created_at"])


def downgrade() -> None:
    for table in ("notifications", "consents", "medications", "medical_records"):
        op.drop_table(table)
    # Postgres enum values cannot safely be removed while historical audit rows may use them.
