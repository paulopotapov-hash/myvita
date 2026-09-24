"""B4 medication management.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'medication_deactivated'")
    op.add_column("medications", sa.Column("route", sa.String(100), nullable=True))
    op.add_column("medications", sa.Column("instructions", sa.Text(), nullable=True))
    op.add_column(
        "medications",
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.execute("UPDATE medications SET instructions = notes WHERE notes IS NOT NULL")
    op.drop_column("medications", "notes")
    op.create_check_constraint(
        "ck_medications_date_order",
        "medications",
        "end_date IS NULL OR end_date >= start_date",
    )
    op.drop_index("ix_medications_clinic_patient", table_name="medications")
    op.create_index(
        "ix_medications_clinic_patient_active_created",
        "medications",
        ["clinic_id", "patient_id", "is_active", "created_at"],
    )
    op.create_index(
        "ix_medications_clinic_patient_start",
        "medications",
        ["clinic_id", "patient_id", "start_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_medications_clinic_patient_start", table_name="medications")
    op.drop_index("ix_medications_clinic_patient_active_created", table_name="medications")
    op.create_index("ix_medications_clinic_patient", "medications", ["clinic_id", "patient_id"])
    op.drop_constraint("ck_medications_date_order", "medications", type_="check")
    op.add_column("medications", sa.Column("notes", sa.Text(), nullable=True))
    op.execute("UPDATE medications SET notes = instructions WHERE instructions IS NOT NULL")
    op.drop_column("medications", "created_by_user_id")
    op.drop_column("medications", "instructions")
    op.drop_column("medications", "route")
    # PostgreSQL enum values are retained because historical audit rows may use them.
