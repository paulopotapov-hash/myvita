"""Enforce valid appointment duration.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_appointments_duration_minutes",
        "appointments",
        "duration_minutes >= 5 AND duration_minutes <= 480",
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointments_duration_minutes", "appointments", type_="check")
