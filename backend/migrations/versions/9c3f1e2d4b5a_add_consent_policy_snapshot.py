"""add immutable consent policy snapshot

Revision ID: 9c3f1e2d4b5a
Revises: e5f6a7b8c9d0

Originally minted as f6a7b8c9d0e1 on feature/messages-backend; re-identified at
merge time because main used the same id for account_lifecycle_mfa_audit_guard.
A database that already ran this migration under the old id still reports
`f6a7b8c9d0e1`'s descendants in alembic_version, so no data change is needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c3f1e2d4b5a"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("consents", sa.Column("policy_version", sa.String(length=100), nullable=True))
    op.add_column("consents", sa.Column("policy_text", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_consents_policy_snapshot_complete",
        "consents",
        "(policy_version IS NULL AND policy_text IS NULL) OR "
        "(policy_version IS NOT NULL AND policy_text IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_consents_policy_snapshot_complete", "consents", type_="check")
    op.drop_column("consents", "policy_text")
    op.drop_column("consents", "policy_version")
