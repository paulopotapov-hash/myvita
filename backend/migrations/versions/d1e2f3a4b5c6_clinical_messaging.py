"""Add clinic-scoped conversations and immutable messages.

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a1b2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for value in (
        "conversation_created",
        "conversation_viewed",
        "message_sent",
        "conversation_status_changed",
        "conversation_escalated",
        "conversation_escalation_cleared",
    ):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    conversation_status_values = ("open", "waiting_for_patient", "waiting_for_team", "closed")
    sender_role_values = ("patient", "doctor", "nurse")
    conversation_status = postgresql.ENUM(
        *conversation_status_values, name="conversation_status"
    )
    sender_role = postgresql.ENUM(*sender_role_values, name="message_sender_role")
    conversation_status.create(op.get_bind(), checkfirst=True)
    sender_role.create(op.get_bind(), checkfirst=True)
    conversation_status_column = postgresql.ENUM(
        *conversation_status_values, name="conversation_status", create_type=False
    )
    sender_role_column = postgresql.ENUM(*sender_role_values, name="message_sender_role", create_type=False)

    op.create_table(
        "clinical_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_staff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("status", conversation_status_column, nullable=False, server_default="waiting_for_patient"),
        sa.Column("needs_doctor_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("patient_unread", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("team_unread", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"], ["patients.id", "patients.clinic_id"],
            name="fk_conversation_patient_clinic", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"],
            name="fk_conversation_creator_clinic", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_conversation_id_clinic"),
        sa.CheckConstraint("length(trim(subject)) > 0", name="ck_conversation_subject_nonempty"),
    )
    op.create_index(
        "ix_conversation_inbox", "clinical_conversations", ["clinic_id", "status", "updated_at"]
    )
    op.create_index(
        "ix_conversation_patient", "clinical_conversations", ["clinic_id", "patient_id", "updated_at"]
    )

    op.create_table(
        "clinical_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_name", sa.String(length=255), nullable=False),
        sa.Column("sender_role", sender_role_column, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id", "clinic_id"], ["clinical_conversations.id", "clinical_conversations.clinic_id"],
            name="fk_message_conversation_clinic", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], name="fk_message_sender_user", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(trim(body)) > 0", name="ck_message_body_nonempty"),
        sa.CheckConstraint(
            "sender_role IN ('patient', 'doctor', 'nurse')", name="ck_message_sender_role"
        ),
    )
    op.create_index("ix_message_conversation_created", "clinical_messages", ["conversation_id", "created_at"])

    # A conversation reference is separate from the Phase 2 document target.
    # The existing document FK and target shape remain intact.
    op.add_column(
        "notifications", sa.Column("conversation_target_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.drop_constraint("ck_notification_target_type", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notification_target_type",
        "notifications",
        "(target_type IS NULL AND target_id IS NULL AND conversation_target_id IS NULL) OR "
        "(target_type = 'document' AND target_id IS NOT NULL AND conversation_target_id IS NULL) OR "
        "(target_type = 'conversation' AND target_id IS NULL AND conversation_target_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_notification_conversation_target",
        "notifications",
        "clinical_conversations",
        ["conversation_target_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )

    # Message content is append-only at the database layer too.
    op.execute(
        """
        CREATE FUNCTION reject_clinical_message_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'clinical messages are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER clinical_messages_no_update_delete "
        "BEFORE UPDATE OR DELETE ON clinical_messages "
        "FOR EACH ROW EXECUTE FUNCTION reject_clinical_message_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS clinical_messages_no_truncate ON clinical_messages")
    op.execute("DROP TRIGGER clinical_messages_no_update_delete ON clinical_messages")
    op.execute("DROP FUNCTION reject_clinical_message_mutation()")
    op.drop_constraint("fk_notification_conversation_target", "notifications", type_="foreignkey")
    op.execute("DELETE FROM notifications WHERE conversation_target_id IS NOT NULL")
    op.drop_constraint("ck_notification_target_type", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notification_target_type",
        "notifications",
        "(target_type IS NULL AND target_id IS NULL) OR "
        "(target_type = 'document' AND target_id IS NOT NULL)",
    )
    op.drop_column("notifications", "conversation_target_id")
    op.drop_index("ix_message_conversation_created", table_name="clinical_messages")
    op.drop_table("clinical_messages")
    op.drop_index("ix_conversation_patient", table_name="clinical_conversations")
    op.drop_index("ix_conversation_inbox", table_name="clinical_conversations")
    op.drop_table("clinical_conversations")
    postgresql.ENUM(name="message_sender_role").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="conversation_status").drop(op.get_bind(), checkfirst=True)
