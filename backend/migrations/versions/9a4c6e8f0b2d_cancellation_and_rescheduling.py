"""Scheduling step 5: cancellation, rescheduling and requests with preferences and proposals.

Revision ID: 9a4c6e8f0b2d
Revises: 8e3f5a7c9b1d

- appointments: cancelled_at / cancelled_by_user_id (who cancelled, from now on), and
  rescheduled_from_id: the appointment this one replaces (same clinic, at most one
  successor per appointment).
- appointment_requests:
  - preferred_start becomes optional: a request carries either that legacy single time or a
    preference window (preferred_from / preferred_to, weekdays, morning or afternoon);
  - appointment_type_id and staff_id (the preferred professional, NULL = any), same clinic;
  - reschedule_of_id: the appointment the patient asks to move;
  - the clinic's proposal: proposed_staff_id, proposed_start, proposed_duration_minutes,
    proposed_at, proposed_by_user_id;
  - statuses "proposed" (waiting for the patient) and "declined" (the patient said no).
- The runtime role may update the proposal columns (column-level UPDATE, db_provisioning).
- Audit actions for rescheduling and proposals.

Existing rows keep every value; every new column starts NULL. Downgrade refuses while any
row uses what this revision added (it would lose it); otherwise it drops the new columns.
The enum labels stay (PostgreSQL cannot drop them).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9a4c6e8f0b2d"
down_revision: str | Sequence[str] | None = "8e3f5a7c9b1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT_ACTIONS = (
    "appointment_rescheduled",
    "appointment_request_proposed",
    "appointment_request_proposal_accepted",
    "appointment_request_proposal_declined",
)


def upgrade() -> None:
    # --- appointments -------------------------------------------------------------------------
    op.add_column("appointments", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("appointments", sa.Column("cancelled_by_user_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_appointments_cancelled_by", "appointments", "users", ["cancelled_by_user_id"], ["id"], ondelete="RESTRICT"
    )
    op.add_column("appointments", sa.Column("rescheduled_from_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_appointments_rescheduled_from_clinic",
        "appointments",
        "appointments",
        ["rescheduled_from_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_appointments_rescheduled_from", "appointments", ["rescheduled_from_id"])

    # --- appointment requests -----------------------------------------------------------------
    op.execute("ALTER TYPE appointment_request_status ADD VALUE IF NOT EXISTS 'proposed'")
    op.execute("ALTER TYPE appointment_request_status ADD VALUE IF NOT EXISTS 'declined'")
    period = postgresql.ENUM("morning", "afternoon", name="request_period")
    period.create(op.get_bind(), checkfirst=True)
    op.alter_column("appointment_requests", "preferred_start", existing_type=sa.DateTime(timezone=True), nullable=True)
    for name, column_type in (
        ("appointment_type_id", sa.UUID()),
        ("staff_id", sa.UUID()),
        ("preferred_from", sa.Date()),
        ("preferred_to", sa.Date()),
        ("preferred_weekdays", postgresql.ARRAY(sa.SmallInteger())),
        ("preferred_period", postgresql.ENUM(name="request_period", create_type=False)),
        ("reschedule_of_id", sa.UUID()),
        ("proposed_staff_id", sa.UUID()),
        ("proposed_start", sa.DateTime(timezone=True)),
        ("proposed_duration_minutes", sa.Integer()),
        ("proposed_at", sa.DateTime(timezone=True)),
        ("proposed_by_user_id", sa.UUID()),
    ):
        op.add_column("appointment_requests", sa.Column(name, column_type, nullable=True))
    for name, columns, target in (
        ("fk_appointment_requests_type_clinic", ["appointment_type_id", "clinic_id"], "appointment_types"),
        ("fk_appointment_requests_staff_clinic", ["staff_id", "clinic_id"], "staff"),
        ("fk_appointment_requests_reschedule_of_clinic", ["reschedule_of_id", "clinic_id"], "appointments"),
        ("fk_appointment_requests_proposed_staff_clinic", ["proposed_staff_id", "clinic_id"], "staff"),
    ):
        op.create_foreign_key(name, "appointment_requests", target, columns, ["id", "clinic_id"], ondelete="RESTRICT")
    op.create_foreign_key(
        "fk_appointment_requests_proposed_by",
        "appointment_requests",
        "users",
        ["proposed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_appointment_requests_reschedule_of", "appointment_requests", ["reschedule_of_id"])
    op.create_check_constraint(
        "ck_appointment_requests_preference",
        "appointment_requests",
        "preferred_start IS NOT NULL OR preferred_from IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_appointment_requests_window",
        "appointment_requests",
        "preferred_to IS NULL OR (preferred_from IS NOT NULL AND preferred_to >= preferred_from)",
    )
    op.create_check_constraint(
        "ck_appointment_requests_weekdays",
        "appointment_requests",
        "preferred_weekdays IS NULL OR (cardinality(preferred_weekdays) BETWEEN 1 AND 7 "
        "AND preferred_weekdays <@ ARRAY[0, 1, 2, 3, 4, 5, 6]::smallint[])",
    )
    op.create_check_constraint(
        "ck_appointment_requests_proposal",
        "appointment_requests",
        "(proposed_start IS NULL) = (proposed_staff_id IS NULL) "
        "AND (proposed_start IS NULL) = (proposed_duration_minutes IS NULL) "
        "AND (proposed_duration_minutes IS NULL OR proposed_duration_minutes BETWEEN 5 AND 480)",
    )

    for value in AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    bind = op.get_bind()
    in_use = bind.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM appointments WHERE rescheduled_from_id IS NOT NULL) "
            "+ (SELECT count(*) FROM appointment_requests WHERE status::text IN ('proposed', 'declined') "
            "   OR preferred_start IS NULL OR appointment_type_id IS NOT NULL OR reschedule_of_id IS NOT NULL)"
        )
    ).scalar_one()
    if in_use:
        raise RuntimeError(
            f"Refusing to downgrade: {in_use} rescheduled appointments or requests with preferences, "
            "types or proposals would be lost."
        )
    for name in (
        "ck_appointment_requests_proposal",
        "ck_appointment_requests_weekdays",
        "ck_appointment_requests_window",
        "ck_appointment_requests_preference",
    ):
        op.drop_constraint(name, "appointment_requests", type_="check")
    op.drop_index("ix_appointment_requests_reschedule_of", table_name="appointment_requests")
    for name in (
        "fk_appointment_requests_proposed_by",
        "fk_appointment_requests_proposed_staff_clinic",
        "fk_appointment_requests_reschedule_of_clinic",
        "fk_appointment_requests_staff_clinic",
        "fk_appointment_requests_type_clinic",
    ):
        op.drop_constraint(name, "appointment_requests", type_="foreignkey")
    for name in (
        "proposed_by_user_id",
        "proposed_at",
        "proposed_duration_minutes",
        "proposed_start",
        "proposed_staff_id",
        "reschedule_of_id",
        "preferred_period",
        "preferred_weekdays",
        "preferred_to",
        "preferred_from",
        "staff_id",
        "appointment_type_id",
    ):
        op.drop_column("appointment_requests", name)
    op.alter_column("appointment_requests", "preferred_start", existing_type=sa.DateTime(timezone=True), nullable=False)
    postgresql.ENUM(name="request_period").drop(bind, checkfirst=True)

    op.drop_constraint("uq_appointments_rescheduled_from", "appointments", type_="unique")
    op.drop_constraint("fk_appointments_rescheduled_from_clinic", "appointments", type_="foreignkey")
    op.drop_column("appointments", "rescheduled_from_id")
    op.drop_constraint("fk_appointments_cancelled_by", "appointments", type_="foreignkey")
    op.drop_column("appointments", "cancelled_by_user_id")
    op.drop_column("appointments", "cancelled_at")
