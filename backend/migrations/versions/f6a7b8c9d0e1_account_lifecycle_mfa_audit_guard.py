"""Account lifecycle, staff MFA, case-insensitive emails and append-only audit log.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0

Non-destructive: only adds columns, tables, an index and triggers. Existing
email values are NOT rewritten; if two accounts already differ only by
letter case the upgrade stops with an explanation instead of guessing which
account to keep.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | None = None
depends_on: str | None = None

NEW_AUDIT_ACTIONS = (
    "password_change_required",
    "password_reset_requested",
    "password_reset_issued",
    "password_reset_completed",
    "login_mfa_challenge",
    "mfa_enabled",
    "mfa_disabled",
    "mfa_reset",
    "mfa_failure",
    "mfa_recovery_code_used",
    "mfa_recovery_codes_regenerated",
    "user_enabled",
)

AUDIT_GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_logs_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'audit_logs is append-only: DELETE rejected'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    -- The only permitted UPDATE is the referential ON DELETE SET NULL of
    -- clinic_id / actor_user_id; every other column must stay identical.
    IF NEW.id = OLD.id
       AND NEW."timestamp" = OLD."timestamp"
       AND NEW.action = OLD.action
       AND NEW.result = OLD.result
       AND NEW.actor_email IS NOT DISTINCT FROM OLD.actor_email
       AND NEW.resource_type IS NOT DISTINCT FROM OLD.resource_type
       AND NEW.resource_id IS NOT DISTINCT FROM OLD.resource_id
       AND NEW.ip_address IS NOT DISTINCT FROM OLD.ip_address
       AND NEW.user_agent IS NOT DISTINCT FROM OLD.user_agent
       AND NEW.metadata IS NOT DISTINCT FROM OLD.metadata
       AND (NEW.clinic_id IS NOT DISTINCT FROM OLD.clinic_id OR NEW.clinic_id IS NULL)
       AND (NEW.actor_user_id IS NOT DISTINCT FROM OLD.actor_user_id OR NEW.actor_user_id IS NULL)
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit_logs is append-only: UPDATE rejected'
        USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""

AUDIT_TRUNCATE_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_logs_reject_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: TRUNCATE rejected'
        USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""


def upgrade() -> None:
    bind = op.get_bind()

    duplicates = bind.execute(
        sa.text("SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1 LIMIT 5")
    ).scalars().all()
    if duplicates:
        raise RuntimeError(
            "Cannot create case-insensitive unique email index: some accounts differ only by "
            f"letter case ({len(duplicates)} conflicting address(es) found). Resolve them manually "
            "(decide which account is legitimate) and run the migration again. No data was changed."
        )

    for value in NEW_AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "user_mfa",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_mfa_recovery_codes_user_hash"),
    )
    op.create_index("ix_mfa_recovery_codes_user_id", "mfa_recovery_codes", ["user_id"])

    op.execute(AUDIT_GUARD_FUNCTION)
    op.execute(AUDIT_TRUNCATE_FUNCTION)
    op.execute(
        "CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_guard()"
    )
    op.execute(
        "CREATE TRIGGER audit_logs_no_truncate BEFORE TRUNCATE ON audit_logs "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_reject_truncate()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_reject_truncate()")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_guard()")
    op.drop_index("ix_mfa_recovery_codes_user_id", table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_table("user_mfa")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_column("users", "must_change_password")
    # PostgreSQL enum labels on audit_action remain for historical compatibility.
