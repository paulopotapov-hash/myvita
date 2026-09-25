"""B4 medication management hardening.

Revision ID: d4e5f6a7b8c9
Revises: b6f1c2d3e4a5
"""

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "b6f1c2d3e4a5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'medication_deactivated'")
    op.add_column("medications", sa.Column("route", sa.String(length=100), nullable=True))
    op.add_column("medications", sa.Column("frequency", sa.String(length=100), nullable=True))
    op.create_unique_constraint("uq_patients_id_clinic", "patients", ["id", "clinic_id"])
    op.drop_constraint("medications_patient_id_fkey", "medications", type_="foreignkey")
    op.create_foreign_key(
        "fk_medications_patient_clinic",
        "medications",
        "patients",
        ["patient_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_medications_date_order",
        "medications",
        "end_date IS NULL OR end_date >= start_date",
    )
    op.drop_index("ix_medications_clinic_patient", table_name="medications")
    op.create_index(
        "ix_medications_clinic_patient_status_created",
        "medications",
        ["clinic_id", "patient_id", "status", "created_at"],
    )
    op.create_index(
        "ix_medications_clinic_patient_start",
        "medications",
        ["clinic_id", "patient_id", "start_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_medications_clinic_patient_start", table_name="medications")
    op.drop_index("ix_medications_clinic_patient_status_created", table_name="medications")
    op.create_index("ix_medications_clinic_patient", "medications", ["clinic_id", "patient_id"])
    op.drop_constraint("ck_medications_date_order", "medications", type_="check")
    op.drop_constraint("fk_medications_patient_clinic", "medications", type_="foreignkey")
    op.create_foreign_key(
        "medications_patient_id_fkey",
        "medications",
        "patients",
        ["patient_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_patients_id_clinic", "patients", type_="unique")
    op.drop_column("medications", "frequency")
    op.drop_column("medications", "route")
    # PostgreSQL enum labels remain because historical audit rows may use them.
