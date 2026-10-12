"""Medication start date: optional and partial in a patient's declaration.

Revision ID: 5f3a9c1e7b2d
Revises: a0b1c2d3e4f5

- medications.start_precision (year / month / day), the same model as the
  clinical history dates: the date is the first day of its period.
- start_date becomes optional, but only for a patient's declaration: a
  professional's medication keeps a complete start date (CHECK).
- Every existing row keeps its start date unchanged, with precision "day".

Downgrade refuses while any medication has no start date or a partial one
(it would have to invent a date); otherwise it only drops the new column and
checks.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5f3a9c1e7b2d"
down_revision: str | Sequence[str] | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROFESSIONAL_BEFORE = (
    "origin <> 'professional' OR (prescribed_by_staff_id IS NOT NULL AND dosage IS NOT NULL "
    "AND confirmed_at IS NOT NULL)"
)
PROFESSIONAL_AFTER = (
    "origin <> 'professional' OR (prescribed_by_staff_id IS NOT NULL AND dosage IS NOT NULL "
    "AND confirmed_at IS NOT NULL AND start_date IS NOT NULL AND start_precision = 'day')"
)


def upgrade() -> None:
    op.add_column(
        "medications",
        sa.Column(
            "start_precision",
            postgresql.ENUM("year", "month", "day", name="date_precision", create_type=False),
            nullable=True,
        ),
    )
    op.execute("UPDATE medications SET start_precision = 'day' WHERE start_date IS NOT NULL")
    op.alter_column("medications", "start_date", existing_type=sa.Date(), nullable=True)
    op.drop_constraint("ck_medications_professional", "medications", type_="check")
    op.create_check_constraint("ck_medications_professional", "medications", PROFESSIONAL_AFTER)
    op.create_check_constraint(
        "ck_medications_start_precision", "medications", "(start_date IS NULL) = (start_precision IS NULL)"
    )
    op.create_check_constraint(
        "ck_medications_start_year_start",
        "medications",
        "start_precision IS DISTINCT FROM 'year' OR "
        "(EXTRACT(MONTH FROM start_date) = 1 AND EXTRACT(DAY FROM start_date) = 1)",
    )
    op.create_check_constraint(
        "ck_medications_start_month_start",
        "medications",
        "start_precision IS DISTINCT FROM 'month' OR EXTRACT(DAY FROM start_date) = 1",
    )


def downgrade() -> None:
    bind = op.get_bind()
    partial = bind.execute(
        sa.text("SELECT count(*) FROM medications WHERE start_date IS NULL OR start_precision <> 'day'")
    ).scalar_one()
    if partial:
        raise RuntimeError(
            f"Refusing to downgrade: {partial} medications have no start date or a partial one, "
            "which the previous schema cannot hold without inventing a date."
        )
    for name in ("ck_medications_start_month_start", "ck_medications_start_year_start", "ck_medications_start_precision"):
        op.drop_constraint(name, "medications", type_="check")
    op.drop_constraint("ck_medications_professional", "medications", type_="check")
    op.create_check_constraint("ck_medications_professional", "medications", PROFESSIONAL_BEFORE)
    op.alter_column("medications", "start_date", existing_type=sa.Date(), nullable=False)
    op.drop_column("medications", "start_precision")
