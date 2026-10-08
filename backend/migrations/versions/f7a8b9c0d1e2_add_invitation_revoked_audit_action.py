"""Add the invitation_revoked audit action.

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'invitation_revoked'")


def downgrade() -> None:
    # PostgreSQL enum labels on audit_action remain for historical compatibility.
    pass
