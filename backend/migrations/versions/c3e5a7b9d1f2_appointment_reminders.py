"""Scheduling step 7: appointment reminders and the patient's confirmation.

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1

- appointments.patient_confirmed_at: the patient confirmed they will come.
- reminder_deliveries: one row per appointment and channel (in_app; email and sms are
  prepared but not active), written by the background job. Append-only for the runtime
  role (db_provisioning).
- notifications.appointment_target_id: a reminder links to its appointment (same-clinic
  foreign key); the target-type check now covers the new column.
- Audit action for the patient's confirmation.

Nothing existing changes. Downgrade refuses while reminders or appointment-linked
notifications exist; otherwise it removes what this revision added.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3e5a7b9d1f2"
down_revision: str | Sequence[str] | None = "b2d4f6a8c0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = {
    "document": "target_id",
    "conversation": "conversation_target_id",
    "result": "result_target_id",
    "medical_record": "record_target_id",
}
AFTER = {**BEFORE, "appointment": "appointment_target_id"}


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
    op.add_column("appointments", sa.Column("patient_confirmed_at", sa.DateTime(timezone=True), nullable=True))

    postgresql.ENUM("in_app", "email", "sms", name="reminder_channel").create(bind, checkfirst=True)
    postgresql.ENUM("sent", "failed", name="reminder_status").create(bind, checkfirst=True)
    op.create_table(
        "reminder_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("appointment_id", sa.UUID(), nullable=False),
        sa.Column("channel", postgresql.ENUM(name="reminder_channel", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="reminder_status", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_reminder_deliveries_appointment_clinic",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("appointment_id", "channel", name="uq_reminder_deliveries_appointment_channel"),
    )

    op.add_column("notifications", sa.Column("appointment_target_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_notification_appointment_target",
        "notifications",
        "appointments",
        ["appointment_target_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("ck_notification_target_type", "notifications", type_="check")
    op.create_check_constraint("ck_notification_target_type", "notifications", _target_type_check(AFTER))

    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'appointment_patient_confirmed'")


def downgrade() -> None:
    bind = op.get_bind()
    in_use = bind.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM reminder_deliveries) "
            "+ (SELECT count(*) FROM notifications WHERE appointment_target_id IS NOT NULL) "
            "+ (SELECT count(*) FROM appointments WHERE patient_confirmed_at IS NOT NULL)"
        )
    ).scalar_one()
    if in_use:
        raise RuntimeError(f"Refusing to downgrade: {in_use} reminders, reminder notifications or confirmations would be lost.")
    op.drop_constraint("ck_notification_target_type", "notifications", type_="check")
    op.create_check_constraint("ck_notification_target_type", "notifications", _target_type_check(BEFORE))
    op.drop_constraint("fk_notification_appointment_target", "notifications", type_="foreignkey")
    op.drop_column("notifications", "appointment_target_id")
    op.drop_table("reminder_deliveries")
    postgresql.ENUM(name="reminder_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="reminder_channel").drop(bind, checkfirst=True)
    op.drop_column("appointments", "patient_confirmed_at")
