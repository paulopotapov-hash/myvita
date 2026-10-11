"""Clinical history: conditions, procedures, allergies, immunizations, notes; medication origin.

Revision ID: a0b1c2d3e4f5
Revises: 9e0f1a2b3c4d

Commit 3 (decisions D1-D9):
- clinical_history_entries: one table for the five categories with a CHECK per
  category (D1), partial dates with their precision (D5), origin and
  confirmation, hiding from the patient with a reason (D4) and soft delete.
- clinical_history_revisions: append-only snapshots, one per version.
- medications: origin (professional / patient_declared), confirmation, hiding,
  soft delete; dosage and prescriber become optional only for a patient's
  declaration (D6). No content revisions for medication (D2).
- Audit actions for the new operations.

Existing medications are kept and marked as confirmed by their prescriber at
their creation time; no row is changed otherwise.

Downgrade refuses to run while any clinical history entry or patient-declared
medication exists, instead of deleting clinical data. The audit enum labels
stay (PostgreSQL cannot drop them; historical rows may hold them).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a0b1c2d3e4f5"
down_revision: str | Sequence[str] | None = "9e0f1a2b3c4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS = {
    "history_category": ("condition", "procedure", "allergy", "immunization", "note"),
    "history_origin": ("professional", "patient_declared"),
    "condition_status": ("active", "resolved"),
    "allergy_severity": ("mild", "moderate", "severe", "unknown"),
    "date_precision": ("year", "month", "day"),
    "history_change_kind": ("created", "updated", "confirmed", "hidden", "shown", "deleted"),
}
AUDIT_ACTIONS = (
    "clinical_history_viewed",
    "clinical_history_created",
    "clinical_history_declared",
    "clinical_history_updated",
    "clinical_history_confirmed",
    "clinical_history_hidden",
    "clinical_history_shown",
    "clinical_history_deleted",
    "medication_declared",
    "medication_confirmed",
    "medication_hidden",
    "medication_shown",
    "medication_deleted",
)
CATEGORY_COLUMNS = (
    "name",
    "condition_status",
    "onset_date",
    "resolved_date",
    "occurred_on",
    "location",
    "reaction",
    "severity",
    "note_text",
)
REQUIRED = {
    "condition": ("name", "condition_status"),
    "procedure": ("name",),
    "allergy": ("name", "severity"),
    "immunization": ("name",),
    "note": ("note_text",),
}
ALLOWED = {
    "condition": {"name", "condition_status", "onset_date", "resolved_date"},
    "procedure": {"name", "occurred_on", "location"},
    "allergy": {"name", "reaction", "severity"},
    "immunization": {"name", "occurred_on"},
    "note": {"note_text"},
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _precision_checks(column: str) -> list[sa.CheckConstraint]:
    precision = f"{column.removesuffix('_date').removesuffix('_on')}_precision"
    return [
        sa.CheckConstraint(
            f"({column} IS NULL) = ({precision} IS NULL)", name=f"ck_clinical_history_{column}_precision"
        ),
        sa.CheckConstraint(
            f"{precision} IS DISTINCT FROM 'year' OR "
            f"(EXTRACT(MONTH FROM {column}) = 1 AND EXTRACT(DAY FROM {column}) = 1)",
            name=f"ck_clinical_history_{column}_year_start",
        ),
        sa.CheckConstraint(
            f"{precision} IS DISTINCT FROM 'month' OR EXTRACT(DAY FROM {column}) = 1",
            name=f"ck_clinical_history_{column}_month_start",
        ),
    ]


def _category_checks() -> list[sa.CheckConstraint]:
    checks = []
    for category, required_columns in REQUIRED.items():
        required = " AND ".join(f"{column} IS NOT NULL" for column in required_columns)
        unused = " AND ".join(f"{column} IS NULL" for column in CATEGORY_COLUMNS if column not in ALLOWED[category])
        checks.append(
            sa.CheckConstraint(
                f"category <> '{category}' OR ({required} AND {unused})",
                name=f"ck_clinical_history_{category}_fields",
            )
        )
    return checks


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "clinical_history_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("category", _enum("history_category"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("condition_status", _enum("condition_status"), nullable=True),
        sa.Column("onset_date", sa.Date(), nullable=True),
        sa.Column("onset_precision", _enum("date_precision"), nullable=True),
        sa.Column("resolved_date", sa.Date(), nullable=True),
        sa.Column("resolved_precision", _enum("date_precision"), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("occurred_precision", _enum("date_precision"), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("reaction", sa.String(length=500), nullable=True),
        sa.Column("severity", _enum("allergy_severity"), nullable=True),
        sa.Column("note_text", sa.Text(), nullable=True),
        sa.Column("origin", _enum("history_origin"), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("confirmed_by_staff_id", sa.UUID(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hidden_by_staff_id", sa.UUID(), nullable=True),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hidden_reason", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", sa.UUID(), nullable=True),
        sa.Column("deletion_reason", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deleted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_clinical_history_patient_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_clinical_history_confirmed_staff_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hidden_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_clinical_history_hidden_staff_clinic",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "clinic_id", name="uq_clinical_history_id_clinic"),
        *_category_checks(),
        sa.CheckConstraint(
            "condition_status IS DISTINCT FROM 'active' OR resolved_date IS NULL",
            name="ck_clinical_history_active_not_resolved",
        ),
        sa.CheckConstraint(
            "resolved_date IS NULL OR onset_date IS NULL OR resolved_date >= onset_date",
            name="ck_clinical_history_resolution_after_onset",
        ),
        *_precision_checks("onset_date"),
        *_precision_checks("resolved_date"),
        *_precision_checks("occurred_on"),
        sa.CheckConstraint(
            "origin <> 'professional' OR confirmed_at IS NOT NULL",
            name="ck_clinical_history_professional_confirmed",
        ),
        sa.CheckConstraint(
            "(confirmed_at IS NULL) = (confirmed_by_staff_id IS NULL)", name="ck_clinical_history_confirmation"
        ),
        sa.CheckConstraint(
            "(hidden_at IS NULL) = (hidden_by_staff_id IS NULL) AND (hidden_at IS NULL) = (hidden_reason IS NULL)",
            name="ck_clinical_history_hidden",
        ),
        sa.CheckConstraint(
            "(deleted_at IS NULL) = (deleted_by_user_id IS NULL) AND (deleted_at IS NOT NULL OR deletion_reason IS NULL)",
            name="ck_clinical_history_deleted",
        ),
        sa.CheckConstraint("version >= 1", name="ck_clinical_history_version"),
    )
    op.create_index("ix_clinical_history_entries_clinic_id", "clinical_history_entries", ["clinic_id"])
    op.create_index("ix_clinical_history_entries_patient_id", "clinical_history_entries", ["patient_id"])
    op.create_index(
        "ix_clinical_history_live_by_patient",
        "clinical_history_entries",
        ["clinic_id", "patient_id", "category"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "clinical_history_revisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("change_kind", _enum("history_change_kind"), nullable=False),
        sa.Column("changed_by_user_id", sa.UUID(), nullable=False),
        sa.Column("change_reason", sa.String(length=500), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["entry_id", "clinic_id"],
            ["clinical_history_entries.id", "clinical_history_entries.clinic_id"],
            name="fk_clinical_history_revisions_entry_clinic",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("entry_id", "version", name="uq_clinical_history_revisions_entry_version"),
        sa.CheckConstraint("version >= 1", name="ck_clinical_history_revisions_version"),
    )
    op.create_index("ix_clinical_history_revisions_entry_id", "clinical_history_revisions", ["entry_id"])

    # --- medications -------------------------------------------------------------------------
    op.add_column(
        "medications",
        sa.Column("origin", _enum("history_origin"), server_default="professional", nullable=False),
    )
    op.add_column("medications", sa.Column("declared_by_user_id", sa.UUID(), nullable=True))
    op.add_column("medications", sa.Column("confirmed_by_staff_id", sa.UUID(), nullable=True))
    op.add_column("medications", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("medications", sa.Column("hidden_by_staff_id", sa.UUID(), nullable=True))
    op.add_column("medications", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("medications", sa.Column("hidden_reason", sa.String(length=500), nullable=True))
    op.add_column("medications", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("medications", sa.Column("deleted_by_user_id", sa.UUID(), nullable=True))
    op.add_column("medications", sa.Column("deletion_reason", sa.String(length=500), nullable=True))
    # Existing medication was prescribed by a professional: confirmed by that professional when created.
    op.execute("UPDATE medications SET confirmed_at = created_at, confirmed_by_staff_id = prescribed_by_staff_id")
    op.alter_column("medications", "prescribed_by_staff_id", existing_type=sa.UUID(), nullable=True)
    op.alter_column("medications", "dosage", existing_type=sa.String(length=200), nullable=True)
    op.create_foreign_key(
        "medications_declared_by_user_id_fkey", "medications", "users", ["declared_by_user_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "medications_deleted_by_user_id_fkey", "medications", "users", ["deleted_by_user_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_medications_confirmed_staff_clinic",
        "medications",
        "staff",
        ["confirmed_by_staff_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_medications_hidden_staff_clinic",
        "medications",
        "staff",
        ["hidden_by_staff_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_medications_professional",
        "medications",
        "origin <> 'professional' OR (prescribed_by_staff_id IS NOT NULL AND dosage IS NOT NULL "
        "AND confirmed_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_medications_patient_declared",
        "medications",
        "origin <> 'patient_declared' OR (declared_by_user_id IS NOT NULL AND prescribed_by_staff_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_medications_confirmation", "medications", "(confirmed_at IS NULL) = (confirmed_by_staff_id IS NULL)"
    )
    op.create_check_constraint(
        "ck_medications_hidden",
        "medications",
        "(hidden_at IS NULL) = (hidden_by_staff_id IS NULL) AND (hidden_at IS NULL) = (hidden_reason IS NULL)",
    )
    op.create_check_constraint(
        "ck_medications_deleted",
        "medications",
        "(deleted_at IS NULL) = (deleted_by_user_id IS NULL) AND (deleted_at IS NOT NULL OR deletion_reason IS NULL)",
    )

    for value in AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    bind = op.get_bind()
    entries = bind.execute(sa.text("SELECT count(*) FROM clinical_history_entries")).scalar_one()
    declared = bind.execute(sa.text("SELECT count(*) FROM medications WHERE origin = 'patient_declared'")).scalar_one()
    if entries or declared:
        raise RuntimeError(
            f"Refusing to downgrade: {entries} clinical history entries and {declared} patient-declared "
            "medications would be lost. Export or remove them deliberately first."
        )
    for name in (
        "ck_medications_deleted",
        "ck_medications_hidden",
        "ck_medications_confirmation",
        "ck_medications_patient_declared",
        "ck_medications_professional",
    ):
        op.drop_constraint(name, "medications", type_="check")
    for name in (
        "fk_medications_hidden_staff_clinic",
        "fk_medications_confirmed_staff_clinic",
        "medications_deleted_by_user_id_fkey",
        "medications_declared_by_user_id_fkey",
    ):
        op.drop_constraint(name, "medications", type_="foreignkey")
    op.alter_column("medications", "dosage", existing_type=sa.String(length=200), nullable=False)
    op.alter_column("medications", "prescribed_by_staff_id", existing_type=sa.UUID(), nullable=False)
    for column in (
        "deletion_reason",
        "deleted_by_user_id",
        "deleted_at",
        "hidden_reason",
        "hidden_at",
        "hidden_by_staff_id",
        "confirmed_at",
        "confirmed_by_staff_id",
        "declared_by_user_id",
        "origin",
    ):
        op.drop_column("medications", column)
    op.drop_table("clinical_history_revisions")
    op.drop_table("clinical_history_entries")
    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
