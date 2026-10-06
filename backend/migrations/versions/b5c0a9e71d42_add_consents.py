"""add consent management

Revision ID: b5c0a9e71d42
Revises: 76dad50950ee
Create Date: 2026-09-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b5c0a9e71d42"
down_revision: str | None = "76dad50950ee"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    consent_type = postgresql.ENUM(
        "treatment",
        "data_processing",
        "communications",
        "research",
        name="consent_type",
        create_type=False,
    )
    consent_status = postgresql.ENUM(
        "granted", "revoked", name="consent_status", create_type=False
    )
    postgresql.ENUM(
        "treatment", "data_processing", "communications", "research", name="consent_type"
    ).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM("granted", "revoked", name="consent_status").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "consents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("consent_type", consent_type, nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False),
        sa.Column("status", consent_status, nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "(status = 'granted' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL AND revoked_at >= granted_at)",
            name="ck_consents_lifecycle",
        ),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consents_clinic_id", "consents", ["clinic_id"])
    op.create_index("ix_consents_patient_id", "consents", ["patient_id"])
    op.create_index("ix_consents_recorded_by_user_id", "consents", ["recorded_by_user_id"])
    op.create_index(
        "ix_consents_clinic_patient_created",
        "consents",
        ["clinic_id", "patient_id", "created_at"],
    )
    op.create_index(
        "uq_consents_active_patient_type_purpose",
        "consents",
        ["patient_id", "consent_type", "purpose"],
        unique=True,
        postgresql_where=sa.text("status = 'granted'"),
    )

    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'consent_granted'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'consent_revoked'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'consent_viewed'")


def downgrade() -> None:
    op.drop_index("uq_consents_active_patient_type_purpose", table_name="consents")
    op.drop_index("ix_consents_clinic_patient_created", table_name="consents")
    op.drop_index("ix_consents_recorded_by_user_id", table_name="consents")
    op.drop_index("ix_consents_patient_id", table_name="consents")
    op.drop_index("ix_consents_clinic_id", table_name="consents")
    op.drop_table("consents")
    sa.Enum(name="consent_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="consent_type").drop(op.get_bind(), checkfirst=True)
    # PostgreSQL cannot remove enum labels safely in-place. The extra audit
    # labels are harmless after downgrade and preserve existing audit rows.
