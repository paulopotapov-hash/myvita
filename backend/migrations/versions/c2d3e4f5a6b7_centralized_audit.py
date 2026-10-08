"""Centralized audit infrastructure: request correlation and admin read access.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'audit_log_viewed'")
    op.add_column("audit_logs", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.create_index("ix_audit_logs_clinic_timestamp", "audit_logs", ["clinic_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_clinic_timestamp", table_name="audit_logs")
    op.drop_column("audit_logs", "request_id")
    # PostgreSQL enum labels remain for historical compatibility.
