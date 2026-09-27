"""Add secure clinic-scoped onboarding invitations.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'invitation_created'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'invitation_accepted'")
    postgresql.ENUM("pending", "accepted", "revoked", name="invitation_status").create(
        op.get_bind(), checkfirst=True
    )
    invitation_status = postgresql.ENUM(
        "pending", "accepted", "revoked", name="invitation_status", create_type=False
    )
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", postgresql.ENUM(name="user_role", create_type=False), nullable=False),
        sa.Column("staff_role", postgresql.ENUM(name="staff_role", create_type=False), nullable=True),
        sa.Column("specialty", sa.String(length=255), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", invitation_status, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_invitations_clinic_id", "invitations", ["clinic_id"])
    op.create_index("ix_invitations_clinic_email", "invitations", ["clinic_id", "email"])
    op.create_index("ix_invitations_expires_at", "invitations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_invitations_expires_at", table_name="invitations")
    op.drop_index("ix_invitations_clinic_email", table_name="invitations")
    op.drop_index("ix_invitations_clinic_id", table_name="invitations")
    op.drop_table("invitations")
    postgresql.ENUM(name="invitation_status").drop(op.get_bind(), checkfirst=True)
    # PostgreSQL enum labels on audit_action remain for historical compatibility.
