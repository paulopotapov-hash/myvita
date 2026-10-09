"""Add the invitation_revoked audit action.

Revision ID: f7a8b9c0d1e2
Revises: 9c3f1e2d4b5a
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "9c3f1e2d4b5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'invitation_revoked'")


def downgrade() -> None:
    # PostgreSQL enum labels on audit_action remain for historical compatibility.
    pass
