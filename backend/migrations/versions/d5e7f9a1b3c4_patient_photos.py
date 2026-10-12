"""Patient profile photo with the doctor's approval.

Revision ID: d5e7f9a1b3c4
Revises: c3e5a7b9d1f2

- patient_photos: at most one pending, one approved and one rejected (reason only, no
  image) per patient. Images live in the document storage; rows and files of photos no
  longer in use are deleted at once (decision of 2026-10-12, docs/patient-photos.md), so
  the runtime role gets DELETE on this table only, and UPDATE on its status columns.
- storage_deletions: files to delete for good, retried by the background job; the
  runtime role may insert and mark them done, never delete.
- notifications.patient_target_id: a photo notification links to the patient (staff) or
  to the profile (the patient); the target-type check covers the new column.
- Audit actions for uploading, approving, rejecting, removing and deleting a photo.

Nothing existing changes. Downgrade refuses while any photo exists, or a file is still
queued for deletion.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5e7f9a1b3c4"
down_revision: str | Sequence[str] | None = "c3e5a7b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = {
    "document": "target_id",
    "conversation": "conversation_target_id",
    "result": "result_target_id",
    "medical_record": "record_target_id",
    "appointment": "appointment_target_id",
}
AFTER = {**BEFORE, "patient": "patient_target_id"}
AUDIT_ACTIONS = (
    "patient_photo_uploaded",
    "patient_photo_approved",
    "patient_photo_rejected",
    "patient_photo_removed",
    "patient_photo_deleted",
)


def _target_type_check(columns: dict[str, str]) -> str:
    """Exactly one target column per target type, or none (same text as the model's)."""
    none = " AND ".join(f"{column} IS NULL" for column in columns.values())
    branches = [f"(target_type IS NULL AND {none})"]
    for kind, own in columns.items():
        others = " AND ".join(f"{column} IS NULL" for column in columns.values() if column != own)
        branches.append(f"(target_type = '{kind}' AND {own} IS NOT NULL AND {others})")
    return " OR ".join(branches)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM("pending", "approved", "rejected", name="patient_photo_status").create(bind, checkfirst=True)
    op.create_table(
        "patient_photos",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="patient_photo_status", create_type=False), nullable=False),
        sa.Column("storage_key", sa.String(length=64), nullable=True),
        sa.Column("uploaded_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_by_staff_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"], ["patients.id", "patients.clinic_id"], name="fk_patient_photos_patient_clinic", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by_staff_id"], ["staff.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("storage_key"),
        sa.CheckConstraint(
            "(status = 'rejected' AND storage_key IS NULL AND rejection_reason IS NOT NULL) "
            "OR (status <> 'rejected' AND storage_key IS NOT NULL AND rejection_reason IS NULL)",
            name="ck_patient_photos_image",
        ),
    )
    op.create_index("ix_patient_photos_patient_id", "patient_photos", ["patient_id"])
    for status in ("pending", "approved", "rejected"):
        op.create_index(
            f"uq_patient_photos_{status}", "patient_photos", ["patient_id"], unique=True, postgresql_where=sa.text(f"status = '{status}'")
        )

    op.create_table(
        "storage_deletions",
        sa.Column("storage_key", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("storage_key"),
    )
    op.create_index("ix_storage_deletions_pending", "storage_deletions", ["requested_at"], postgresql_where=sa.text("deleted_at IS NULL"))

    op.add_column("notifications", sa.Column("patient_target_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_notification_patient_target",
        "notifications",
        "patients",
        ["patient_target_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("ck_notification_target_type", "notifications", type_="check")
    op.create_check_constraint("ck_notification_target_type", "notifications", _target_type_check(AFTER))

    for value in AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    bind = op.get_bind()
    in_use = bind.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM patient_photos) "
            "+ (SELECT count(*) FROM storage_deletions WHERE deleted_at IS NULL) "
            "+ (SELECT count(*) FROM notifications WHERE patient_target_id IS NOT NULL)"
        )
    ).scalar_one()
    if in_use:
        raise RuntimeError(f"Refusing to downgrade: {in_use} photos, pending file deletions or photo notifications would be lost.")
    op.drop_constraint("ck_notification_target_type", "notifications", type_="check")
    op.create_check_constraint("ck_notification_target_type", "notifications", _target_type_check(BEFORE))
    op.drop_constraint("fk_notification_patient_target", "notifications", type_="foreignkey")
    op.drop_column("notifications", "patient_target_id")
    op.drop_table("storage_deletions")
    op.drop_table("patient_photos")
    postgresql.ENUM(name="patient_photo_status").drop(bind, checkfirst=True)
