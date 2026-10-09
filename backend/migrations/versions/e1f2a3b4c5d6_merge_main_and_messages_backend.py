"""Merge main (account lifecycle, MFA, care assignments, clinical documents/messaging)
with feature/messages-backend (consent snapshot, invitations, appointment requests,
messages, documents, centralized audit).

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6, c2d3e4f5a6b7

No schema operations: both branches touch disjoint tables/enum types, and the
shared `audit_action` enum is extended with `ADD VALUE IF NOT EXISTS` on both
sides, so applying either chain after the other is safe.
"""

from collections.abc import Sequence

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = ("d1e2f3a4b5c6", "c2d3e4f5a6b7")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
