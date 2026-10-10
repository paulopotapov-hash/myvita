"""Clinical conversation lifecycle: team inbox status, nurse escalation, doctor close.

Revision ID: 7c8d9e0f1a2b
Revises: 6b7c8d9e0f1a

Adds to `conversations`:
- `status` (open / waiting_for_patient / waiting_for_team / closed),
- `needs_doctor_review` with who/when requested it (nurse escalation),
- `closed_at` / `closed_by_staff_id` (only a doctor closes).
Both staff references are same-clinic composite foreign keys.

Backfill (deterministic, one UPDATE, no notifications): a conversation whose
latest message was written by the patient is `waiting_for_team`; by the care
team, `waiting_for_patient`; with no message, `open`. Nothing is closed or
escalated by the migration.

Downgrade drops the lifecycle columns. Messages and conversations are kept;
closed conversations become writable again under the previous one-to-one
model, so review closed conversations before downgrading in a live system.
The audit_action labels used here already exist (migration d1e2f3a4b5c6).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7c8d9e0f1a2b"
down_revision: str | Sequence[str] | None = "6b7c8d9e0f1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = ("open", "waiting_for_patient", "waiting_for_team", "closed")


def upgrade() -> None:
    status = postgresql.ENUM(*_STATUS_VALUES, name="conversation_lifecycle_status", create_type=False)
    status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "conversations", sa.Column("status", status, server_default=sa.text("'open'"), nullable=False)
    )
    op.add_column(
        "conversations",
        sa.Column("needs_doctor_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("conversations", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("escalated_by_staff_id", sa.UUID(), nullable=True))
    op.add_column("conversations", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("closed_by_staff_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_escalated_by_clinic",
        "conversations",
        "staff",
        ["escalated_by_staff_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_conversations_closed_by_clinic",
        "conversations",
        "staff",
        ["closed_by_staff_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_conversations_closed_state",
        "conversations",
        "(status = 'closed' AND closed_at IS NOT NULL AND closed_by_staff_id IS NOT NULL) OR "
        "(status <> 'closed' AND closed_at IS NULL AND closed_by_staff_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_conversations_escalation_state",
        "conversations",
        "NOT needs_doctor_review OR (escalated_at IS NOT NULL AND escalated_by_staff_id IS NOT NULL)",
    )
    op.create_index(
        "ix_conversations_clinic_patient_status", "conversations", ["clinic_id", "patient_id", "status"]
    )

    # Who spoke last decides whose turn it is.
    op.execute(
        """
        UPDATE conversations AS c
           SET status = CASE
                   WHEN (
                       SELECT m.sender_user_id
                         FROM messages AS m
                        WHERE m.conversation_id = c.id
                        ORDER BY m.created_at DESC, m.id DESC
                        LIMIT 1
                   ) = (SELECT p.user_id FROM patients AS p WHERE p.id = c.patient_id)
                   THEN 'waiting_for_team'::conversation_lifecycle_status
                   ELSE 'waiting_for_patient'::conversation_lifecycle_status
               END
         WHERE EXISTS (SELECT 1 FROM messages AS m WHERE m.conversation_id = c.id)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_clinic_patient_status", table_name="conversations")
    op.drop_constraint("ck_conversations_escalation_state", "conversations", type_="check")
    op.drop_constraint("ck_conversations_closed_state", "conversations", type_="check")
    op.drop_constraint("fk_conversations_closed_by_clinic", "conversations", type_="foreignkey")
    op.drop_constraint("fk_conversations_escalated_by_clinic", "conversations", type_="foreignkey")
    for column in (
        "closed_by_staff_id",
        "closed_at",
        "escalated_by_staff_id",
        "escalated_at",
        "needs_doctor_review",
        "status",
    ):
        op.drop_column("conversations", column)
    sa.Enum(name="conversation_lifecycle_status").drop(op.get_bind(), checkfirst=True)
