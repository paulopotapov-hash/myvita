"""Add explicit professional-to-patient care assignments.

Revision ID: ab12cd34ef56
Revises: f6a7b8c9d0e1
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "ab12cd34ef56"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Enum labels are retained on downgrade because existing rows may use them.
    op.execute("ALTER TYPE staff_role ADD VALUE IF NOT EXISTS 'physiotherapist'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'care_assignment_created'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'care_assignment_ended'")

    op.create_unique_constraint("uq_staff_id_clinic", "staff", ["id", "clinic_id"])
    op.create_table(
        "clinical_care_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("staff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_care_assignment_patient_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_care_assignment_staff_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"], ["users.id"], name="fk_care_assignment_assigned_by", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_care_assignments_clinic_patient_active",
        "clinical_care_assignments",
        ["clinic_id", "patient_id", "active"],
    )
    op.create_index(
        "uq_care_assignment_active_staff_patient",
        "clinical_care_assignments",
        ["staff_id", "patient_id"],
        unique=True,
        postgresql_where=sa.text("active IS TRUE"),
    )


def downgrade() -> None:
    op.drop_table("clinical_care_assignments")
    op.drop_constraint("uq_staff_id_clinic", "staff", type_="unique")
    # PostgreSQL enum labels remain for compatibility with historical data.
