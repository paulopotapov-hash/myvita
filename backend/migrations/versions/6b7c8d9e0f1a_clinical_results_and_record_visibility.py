"""Clinical results (P2.4), patient visibility of medical records (P2.5) and
idempotent, target-aware notifications (P2.6).

Revision ID: 6b7c8d9e0f1a
Revises: 5a6b7c8d9e0f

- `clinical_results`: one row per result, scoped to its patient AND clinic by
  composite foreign keys (patient, author, releaser and optional document must
  all belong to the same clinic). Draft -> released is one-way (check
  constraint on the release columns). A correction is a new row that points at
  the result it corrects, for the same patient and clinic (composite foreign
  key), with a mandatory reason; a result is corrected at most once (partial
  unique index), so corrections form a chain.
- `medical_records.patient_visibility` (+ who/when of the last explicit
  decision) and `medical_record_revisions.patient_visibility`: records are
  internal by default. Rows that already exist were readable by their patient
  under the previous policy; they are backfilled as `legacy_shared`, which keeps
  that access without pretending a professional shared them (no decision
  author, no timestamp, no notification). Revisions are backfilled the same way.
- `notifications.result_target_id` / `notifications.record_target_id`: deep
  links to a result or a medical record (same-clinic foreign keys); the target
  check constraint accepts the new 'result' and 'medical_record' types.
- `notifications.event_key` + partial unique index: a domain event that fires
  twice (retry, double submit) yields one notification per recipient.

The backfill is a single deterministic UPDATE inside the migration transaction,
under the ACCESS EXCLUSIVE lock taken by ADD COLUMN, so no row can be inserted
between adding the column and backfilling it. It sends no notification.

Downgrade restores the previous schema, where every record (and its revision
history) is readable by the patient and clinical results do not exist. It
therefore REFUSES, changing nothing, when that would expose or destroy data:
any internal record or internal revision (it would become patient-readable), or
any clinical result (it would be deleted). Resolve those rows deliberately
before downgrading. Notifications that point at a record keep their row and
generic text; only their target is cleared. PostgreSQL enum labels added to
audit_action stay, as in earlier migrations.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6b7c8d9e0f1a"
down_revision: str | Sequence[str] | None = "5a6b7c8d9e0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_VALUES = (
    "clinical_result_created",
    "clinical_result_draft_updated",
    "clinical_result_released",
    "clinical_result_corrected",
    "clinical_result_viewed",
    "medical_record_shared",
    "medical_record_unshared",
)

_OLD_TARGET_CHECK = (
    "(target_type IS NULL AND target_id IS NULL AND conversation_target_id IS NULL) OR "
    "(target_type = 'document' AND target_id IS NOT NULL AND conversation_target_id IS NULL) OR "
    "(target_type = 'conversation' AND target_id IS NULL AND conversation_target_id IS NOT NULL)"
)
# Same text as app.models.notification.TARGET_TYPE_CHECK (migrations never import app code).
_NEW_TARGET_CHECK = (
    "(target_type IS NULL AND target_id IS NULL AND conversation_target_id IS NULL "
    "AND result_target_id IS NULL AND record_target_id IS NULL) OR "
    "(target_type = 'document' AND target_id IS NOT NULL AND conversation_target_id IS NULL "
    "AND result_target_id IS NULL AND record_target_id IS NULL) OR "
    "(target_type = 'conversation' AND target_id IS NULL AND conversation_target_id IS NOT NULL "
    "AND result_target_id IS NULL AND record_target_id IS NULL) OR "
    "(target_type = 'result' AND target_id IS NULL AND conversation_target_id IS NULL "
    "AND result_target_id IS NOT NULL AND record_target_id IS NULL) OR "
    "(target_type = 'medical_record' AND target_id IS NULL AND conversation_target_id IS NULL "
    "AND result_target_id IS NULL AND record_target_id IS NOT NULL)"
)
_VISIBILITY_CHECK = (
    "(patient_visibility = 'shared' AND visibility_changed_by_staff_id IS NOT NULL "
    "AND visibility_changed_at IS NOT NULL) OR "
    "(patient_visibility = 'legacy_shared' AND visibility_changed_by_staff_id IS NULL "
    "AND visibility_changed_at IS NULL) OR "
    "(patient_visibility = 'internal' AND "
    "(visibility_changed_by_staff_id IS NULL) = (visibility_changed_at IS NULL))"
)


def upgrade() -> None:
    for value in _AUDIT_VALUES:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    category = postgresql.ENUM(
        "laboratory", "imaging", "pathology", "other", name="clinical_result_category", create_type=False
    )
    result_status = postgresql.ENUM("draft", "released", name="clinical_result_status", create_type=False)
    visibility = postgresql.ENUM(
        "internal", "shared", "legacy_shared", name="medical_record_visibility", create_type=False
    )
    for enum_type in (category, result_status, visibility):
        enum_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "clinical_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("author_staff_id", sa.UUID(), nullable=False),
        sa.Column("category", category, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("reference_range", sa.String(length=100), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("result_date", sa.Date(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("status", result_status, nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by_staff_id", sa.UUID(), nullable=True),
        sa.Column("corrects_result_id", sa.UUID(), nullable=True),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(status = 'released' AND released_at IS NOT NULL AND released_by_staff_id IS NOT NULL) OR "
            "(status = 'draft' AND released_at IS NULL AND released_by_staff_id IS NULL)",
            name="ck_clinical_results_release_state",
        ),
        sa.CheckConstraint(
            "(corrects_result_id IS NULL AND correction_reason IS NULL) OR "
            "(corrects_result_id IS NOT NULL AND correction_reason IS NOT NULL AND corrects_result_id <> id)",
            name="ck_clinical_results_correction",
        ),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_clinical_results_patient_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["author_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_clinical_results_author_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["released_by_staff_id", "clinic_id"],
            ["staff.id", "staff.clinic_id"],
            name="fk_clinical_results_releaser_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "clinic_id"],
            ["documents.id", "documents.clinic_id"],
            name="fk_clinical_results_document_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["corrects_result_id", "patient_id", "clinic_id"],
            ["clinical_results.id", "clinical_results.patient_id", "clinical_results.clinic_id"],
            name="fk_clinical_results_corrects_same_patient",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_clinical_results_id_clinic"),
        sa.UniqueConstraint("id", "patient_id", "clinic_id", name="uq_clinical_results_id_patient_clinic"),
    )
    op.create_index(op.f("ix_clinical_results_clinic_id"), "clinical_results", ["clinic_id"])
    op.create_index(op.f("ix_clinical_results_patient_id"), "clinical_results", ["patient_id"])
    op.create_index(
        "ix_clinical_results_clinic_patient_date", "clinical_results", ["clinic_id", "patient_id", "result_date"]
    )
    op.create_index(
        "uq_clinical_results_corrects_result_id",
        "clinical_results",
        ["corrects_result_id"],
        unique=True,
        postgresql_where=sa.text("corrects_result_id IS NOT NULL"),
    )

    # Medical record visibility. New rows default to 'internal'; every existing
    # row (and its history) keeps the patient access it had, as 'legacy_shared'.
    for table in ("medical_records", "medical_record_revisions"):
        op.add_column(
            table,
            sa.Column("patient_visibility", visibility, server_default=sa.text("'internal'"), nullable=False),
        )
        op.execute(f"UPDATE {table} SET patient_visibility = 'legacy_shared'")
    op.add_column("medical_records", sa.Column("visibility_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("medical_records", sa.Column("visibility_changed_by_staff_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_medical_records_visibility_staff_clinic",
        "medical_records",
        "staff",
        ["visibility_changed_by_staff_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint("ck_medical_records_visibility_decision", "medical_records", _VISIBILITY_CHECK)
    op.create_unique_constraint("uq_medical_records_id_clinic", "medical_records", ["id", "clinic_id"])

    op.add_column("notifications", sa.Column("result_target_id", sa.UUID(), nullable=True))
    op.add_column("notifications", sa.Column("record_target_id", sa.UUID(), nullable=True))
    op.add_column("notifications", sa.Column("event_key", sa.String(length=200), nullable=True))
    op.create_foreign_key(
        "fk_notification_result_target",
        "notifications",
        "clinical_results",
        ["result_target_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_notification_record_target",
        "notifications",
        "medical_records",
        ["record_target_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("ck_notification_target_type", "notifications", type_="check")
    op.create_check_constraint("ck_notification_target_type", "notifications", _NEW_TARGET_CHECK)
    op.create_index(
        "uq_notifications_user_event_key",
        "notifications",
        ["user_id", "event_key"],
        unique=True,
        postgresql_where=sa.text("event_key IS NOT NULL"),
    )


def _refuse_unsafe_downgrade() -> None:
    bind = op.get_bind()
    internal_records = bind.execute(
        sa.text("SELECT count(*) FROM medical_records WHERE patient_visibility = 'internal'")
    ).scalar_one()
    internal_revisions = bind.execute(
        sa.text("SELECT count(*) FROM medical_record_revisions WHERE patient_visibility = 'internal'")
    ).scalar_one()
    results = bind.execute(sa.text("SELECT count(*) FROM clinical_results")).scalar_one()
    if internal_records or internal_revisions or results:
        raise RuntimeError(
            "Refusing to downgrade 6b7c8d9e0f1a: the previous schema makes every medical record and "
            "its revision history readable by the patient and has no clinical results table. "
            f"Found {internal_records} internal record(s), {internal_revisions} internal revision(s) "
            f"and {results} clinical result(s) that would be exposed or deleted. Resolve them "
            "deliberately first. No data was changed."
        )


def downgrade() -> None:
    _refuse_unsafe_downgrade()

    op.drop_index("uq_notifications_user_event_key", table_name="notifications")
    # Keep the notification and its generic text; only the record target goes away.
    # (No result target can exist: the refusal above requires an empty clinical_results.)
    op.execute(
        "UPDATE notifications SET target_type = NULL, record_target_id = NULL WHERE target_type = 'medical_record'"
    )
    op.drop_constraint("ck_notification_target_type", "notifications", type_="check")
    op.create_check_constraint("ck_notification_target_type", "notifications", _OLD_TARGET_CHECK)
    op.drop_constraint("fk_notification_record_target", "notifications", type_="foreignkey")
    op.drop_constraint("fk_notification_result_target", "notifications", type_="foreignkey")
    op.drop_column("notifications", "event_key")
    op.drop_column("notifications", "record_target_id")
    op.drop_column("notifications", "result_target_id")

    op.drop_constraint("uq_medical_records_id_clinic", "medical_records", type_="unique")
    op.drop_constraint("ck_medical_records_visibility_decision", "medical_records", type_="check")
    op.drop_constraint("fk_medical_records_visibility_staff_clinic", "medical_records", type_="foreignkey")
    op.drop_column("medical_records", "visibility_changed_by_staff_id")
    op.drop_column("medical_records", "visibility_changed_at")
    for table in ("medical_record_revisions", "medical_records"):
        op.drop_column(table, "patient_visibility")

    op.drop_index("uq_clinical_results_corrects_result_id", table_name="clinical_results")
    op.drop_index("ix_clinical_results_clinic_patient_date", table_name="clinical_results")
    op.drop_index(op.f("ix_clinical_results_patient_id"), table_name="clinical_results")
    op.drop_index(op.f("ix_clinical_results_clinic_id"), table_name="clinical_results")
    op.drop_table("clinical_results")
    for name in ("medical_record_visibility", "clinical_result_status", "clinical_result_category"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
