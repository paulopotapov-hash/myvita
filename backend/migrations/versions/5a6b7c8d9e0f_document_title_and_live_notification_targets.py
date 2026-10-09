"""Document titles and notification targets on the live documents/conversations tables.

Revision ID: 5a6b7c8d9e0f
Revises: e1f2a3b4c5d6

Integration Phase 4 (decisions D4, D5, M6):
- `documents.title` (custom title restored from Parent A). Existing rows are
  backfilled from `original_filename`, then the column becomes NOT NULL.
- Notification deep-link targets (`target_id` for documents,
  `conversation_target_id` for conversations) pointed at Parent A's
  `clinical_documents` / `clinical_conversations`. Those tables are deprecated
  (kept, not dropped, until no environment holds data in them), so the foreign
  keys are repointed at the live `documents` / `conversations` tables.
  Notifications whose target only exists in the deprecated tables keep their row
  and text; their old target is first COPIED into
  `deprecated_notification_targets` (no data loss) and then cleared on the
  notification (the check constraint allows an all-NULL target). The archive is
  dropped together with the deprecated tables later; downgrade restores from it.
- `(id, clinic_id)` unique keys on `documents` and `conversations` so the
  repointed foreign keys keep Parent A's same-clinic guarantee.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5a6b7c8d9e0f"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ARCHIVE = "deprecated_notification_targets"


def _target_missing_from(documents_table: str, conversations_table: str) -> str:
    """SQL predicate on `notifications`: its target does not exist in the given tables."""
    return f"""
        (notifications.target_id IS NOT NULL
         AND NOT EXISTS (SELECT 1 FROM {documents_table} d WHERE d.id = notifications.target_id))
        OR (notifications.conversation_target_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM {conversations_table} c
                             WHERE c.id = notifications.conversation_target_id))
    """


def _clear_targets_missing_from(documents_table: str, conversations_table: str) -> None:
    op.execute(
        "UPDATE notifications SET target_type = NULL, target_id = NULL, conversation_target_id = NULL "
        f"WHERE {_target_missing_from(documents_table, conversations_table)}"
    )


def upgrade() -> None:
    op.add_column("documents", sa.Column("title", sa.String(length=200), nullable=True))
    op.execute("UPDATE documents SET title = LEFT(original_filename, 200) WHERE title IS NULL")
    op.alter_column("documents", "title", existing_type=sa.String(length=200), nullable=False)

    op.create_unique_constraint("uq_documents_id_clinic", "documents", ["id", "clinic_id"])
    op.create_unique_constraint("uq_conversations_id_clinic", "conversations", ["id", "clinic_id"])

    op.drop_constraint("fk_notification_document_target", "notifications", type_="foreignkey")
    op.drop_constraint("fk_notification_conversation_target", "notifications", type_="foreignkey")
    # No silent data loss: keep every target that is about to be cleared. Migration-only
    # table (no model, no app grants); dropped with the deprecated clinical_* tables.
    op.create_table(
        _ARCHIVE,
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        comment="DEPRECATED: notification targets in clinical_documents/clinical_conversations (Parent A), "
        "archived by migration 5a6b7c8d9e0f. Drop together with those tables.",
    )
    op.execute(
        f"INSERT INTO {_ARCHIVE} (notification_id, target_type, target_id, conversation_target_id) "
        "SELECT id, target_type, target_id, conversation_target_id FROM notifications "
        f"WHERE {_target_missing_from('documents', 'conversations')}"
    )
    _clear_targets_missing_from("documents", "conversations")
    op.create_foreign_key(
        "fk_notification_document_target",
        "notifications",
        "documents",
        ["target_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_notification_conversation_target",
        "notifications",
        "conversations",
        ["conversation_target_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_notification_conversation_target", "notifications", type_="foreignkey")
    op.drop_constraint("fk_notification_document_target", "notifications", type_="foreignkey")
    # Targets on the live tables cannot be expressed against Parent A's tables: they are
    # cleared (notifications kept). Archived Parent A targets are restored when they still exist.
    _clear_targets_missing_from("clinical_documents", "clinical_conversations")
    op.execute(
        f"""
        UPDATE notifications
           SET target_type = a.target_type, target_id = a.target_id,
               conversation_target_id = a.conversation_target_id
          FROM {_ARCHIVE} a
         WHERE notifications.id = a.notification_id
           AND (a.target_id IS NULL OR EXISTS (SELECT 1 FROM clinical_documents d WHERE d.id = a.target_id))
           AND (a.conversation_target_id IS NULL
                OR EXISTS (SELECT 1 FROM clinical_conversations c WHERE c.id = a.conversation_target_id))
        """
    )
    op.drop_table(_ARCHIVE)
    op.create_foreign_key(
        "fk_notification_document_target",
        "notifications",
        "clinical_documents",
        ["target_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_notification_conversation_target",
        "notifications",
        "clinical_conversations",
        ["conversation_target_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("uq_conversations_id_clinic", "conversations", type_="unique")
    op.drop_constraint("uq_documents_id_clinic", "documents", type_="unique")
    op.drop_column("documents", "title")
