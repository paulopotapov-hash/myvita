"""Add patient appointment requests.

Revision ID: e8f9a0b1c2d3
Revises: f7a8b9c0d1e2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8f9a0b1c2d3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for value in (
        "appointment_request_created",
        "appointment_request_accepted",
        "appointment_request_rejected",
        "appointment_request_cancelled",
    ):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")
    postgresql.ENUM(
        "pending", "accepted", "rejected", "cancelled", name="appointment_request_status"
    ).create(op.get_bind(), checkfirst=True)
    request_status = postgresql.ENUM(
        "pending", "accepted", "rejected", "cancelled", name="appointment_request_status", create_type=False
    )
    op.create_table(
        "appointment_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("preferred_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("status", request_status, nullable=False),
        sa.Column("appointment_id", sa.UUID(), nullable=True),
        sa.Column("decided_by_user_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_appointment_requests_patient_clinic",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id"),
    )
    op.create_index("ix_appointment_requests_clinic_id", "appointment_requests", ["clinic_id"])
    op.create_index("ix_appointment_requests_patient_id", "appointment_requests", ["patient_id"])
    op.create_index(
        "ix_appointment_requests_clinic_status_created",
        "appointment_requests",
        ["clinic_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("appointment_requests")
    postgresql.ENUM(name="appointment_request_status").drop(op.get_bind(), checkfirst=True)
    # PostgreSQL enum labels on audit_action remain for historical compatibility.
