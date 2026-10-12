"""Scheduling: specialties, appointment types, weekly schedules, absences, booking settings,
and database-level protection against double booking.

Revision ID: 7d2e4b9a1c3f
Revises: 5f3a9c1e7b2d

- CREATE EXTENSION btree_gist (1.7, a "trusted" extension in PostgreSQL 16: the schema
  owner can create it without superuser; verified on the dev, CI and production images).
- specialties, appointment_types, clinic_booking_settings, schedule_rules,
  schedule_rule_types, schedule_absences.
- staff.specialty_id (from the existing free-text specialty, one specialty per distinct
  name per clinic) and staff.accepts_new_patients (true).
- appointments.ends_at (= scheduled_at + duration), appointment_type_id (NULL for existing
  appointments, shown as "Consulta"), booked_via ("staff" for existing ones).
- Two exclusion constraints over [scheduled_at, ends_at) of active appointments
  (scheduled/confirmed): one per professional, one per patient. Adjacent intervals are
  allowed; cancelled/finished appointments never block.

Existing data: nothing is deleted or moved. If active appointments already overlap, the
upgrade refuses (changing nothing) and reports how many, so they can be resolved first.
Downgrade refuses while scheduling configuration or typed appointments exist; otherwise it
removes what this revision added. The extension and the audit enum labels stay.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7d2e4b9a1c3f"
down_revision: str | Sequence[str] | None = "5f3a9c1e7b2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS = {
    "booking_mode": ("direct", "request"),
    "absence_kind": ("vacation", "other"),
    "booking_source": ("staff", "patient", "request", "waitlist"),
}
AUDIT_ACTIONS = (
    "specialty_created",
    "specialty_updated",
    "appointment_type_created",
    "appointment_type_updated",
    "booking_settings_updated",
    "schedule_updated",
    "staff_booking_profile_updated",
    "absence_created",
    "absence_deleted",
)
ACTIVE = "status IN ('scheduled', 'confirmed')"
OVERLAP = "tstzrange(a.scheduled_at, a.ends_at, '[)') && tstzrange(b.scheduled_at, b.ends_at, '[)')"


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "specialties",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("clinic_id", "name", name="uq_specialties_clinic_name"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_specialties_id_clinic"),
    )
    op.create_index("ix_specialties_clinic_id", "specialties", ["clinic_id"])

    op.create_table(
        "appointment_types",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("specialty_id", sa.UUID(), nullable=False),
        sa.Column("booking_mode", _enum("booking_mode"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["specialty_id", "clinic_id"],
            ["specialties.id", "specialties.clinic_id"],
            name="fk_appointment_types_specialty_clinic",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("clinic_id", "name", name="uq_appointment_types_clinic_name"),
        sa.UniqueConstraint("id", "clinic_id", name="uq_appointment_types_id_clinic"),
        sa.CheckConstraint("duration_minutes BETWEEN 5 AND 480", name="ck_appointment_types_duration"),
    )
    op.create_index("ix_appointment_types_clinic_id", "appointment_types", ["clinic_id"])

    op.create_table(
        "clinic_booking_settings",
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("cancellation_deadline_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("waitlist_offer_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("reminder_hours_before", sa.Integer(), server_default="24", nullable=False),
        sa.Column("booking_horizon_days", sa.Integer(), server_default="90", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("clinic_id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("cancellation_deadline_hours BETWEEN 0 AND 336", name="ck_booking_settings_deadline"),
        sa.CheckConstraint("waitlist_offer_minutes BETWEEN 5 AND 2880", name="ck_booking_settings_offer"),
        sa.CheckConstraint("reminder_hours_before BETWEEN 1 AND 168", name="ck_booking_settings_reminder"),
        sa.CheckConstraint("booking_horizon_days BETWEEN 1 AND 365", name="ck_booking_settings_horizon"),
    )

    op.create_table(
        "schedule_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("staff_id", sa.UUID(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"], name="fk_schedule_rules_staff_clinic", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("id", "clinic_id", name="uq_schedule_rules_id_clinic"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_schedule_rules_weekday"),
        sa.CheckConstraint("end_time > start_time", name="ck_schedule_rules_hours"),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from", name="ck_schedule_rules_validity"
        ),
    )
    op.create_index("ix_schedule_rules_clinic_id", "schedule_rules", ["clinic_id"])
    op.create_index("ix_schedule_rules_staff_id", "schedule_rules", ["staff_id"])

    op.create_table(
        "schedule_rule_types",
        sa.Column("rule_id", sa.UUID(), nullable=False),
        sa.Column("appointment_type_id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("rule_id", "appointment_type_id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["rule_id", "clinic_id"],
            ["schedule_rules.id", "schedule_rules.clinic_id"],
            name="fk_schedule_rule_types_rule_clinic",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_types.id", "appointment_types.clinic_id"],
            name="fk_schedule_rule_types_type_clinic",
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "schedule_absences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("staff_id", sa.UUID(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", _enum("absence_kind"), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"], name="fk_schedule_absences_staff_clinic", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_schedule_absences_period"),
    )
    op.create_index("ix_schedule_absences_clinic_id", "schedule_absences", ["clinic_id"])
    op.create_index("ix_schedule_absences_staff_id", "schedule_absences", ["staff_id"])

    # --- staff: bookable specialty (from the existing free text) and new-patient flag ---------
    op.add_column("staff", sa.Column("specialty_id", sa.UUID(), nullable=True))
    op.add_column("staff", sa.Column("accepts_new_patients", sa.Boolean(), server_default="true", nullable=False))
    op.execute(
        "INSERT INTO specialties (id, clinic_id, name) "
        "SELECT gen_random_uuid(), clinic_id, name FROM ("
        "  SELECT DISTINCT clinic_id, btrim(specialty) AS name FROM staff "
        "  WHERE specialty IS NOT NULL AND btrim(specialty) <> ''"
        ") AS named"
    )
    op.execute(
        "UPDATE staff SET specialty_id = s.id FROM specialties s "
        "WHERE s.clinic_id = staff.clinic_id AND s.name = btrim(staff.specialty)"
    )
    op.create_foreign_key(
        "fk_staff_specialty_clinic",
        "staff",
        "specialties",
        ["specialty_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )

    # --- appointments --------------------------------------------------------------------------
    op.add_column("appointments", sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE appointments SET ends_at = scheduled_at + make_interval(mins => duration_minutes)")
    op.alter_column("appointments", "ends_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.add_column("appointments", sa.Column("appointment_type_id", sa.UUID(), nullable=True))
    op.add_column(
        "appointments", sa.Column("booked_via", _enum("booking_source"), server_default="staff", nullable=False)
    )
    op.create_foreign_key(
        "fk_appointments_type_clinic",
        "appointments",
        "appointment_types",
        ["appointment_type_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_appointments_staff_scheduled_at", "appointments", ["staff_id", "scheduled_at"])

    for column, label in (("staff_id", "professional"), ("patient_id", "patient")):
        overlaps = bind.execute(
            sa.text(
                f"SELECT count(*) FROM appointments a JOIN appointments b "
                f"ON a.{column} = b.{column} AND a.id < b.id "
                f"WHERE {ACTIVE.replace('status', 'a.status')} AND {ACTIVE.replace('status', 'b.status')} AND {OVERLAP}"
            )
        ).scalar_one()
        if overlaps:
            raise RuntimeError(
                f"Refusing to add the double-booking protection: {overlaps} pairs of active appointments "
                f"already overlap for the same {label}. Resolve them (reschedule or cancel) and run again."
            )
    op.execute(
        "ALTER TABLE appointments ADD CONSTRAINT ex_appointments_staff_no_overlap "
        "EXCLUDE USING gist (staff_id WITH =, tstzrange(scheduled_at, ends_at, '[)') WITH &&) "
        f"WHERE ({ACTIVE})"
    )
    op.execute(
        "ALTER TABLE appointments ADD CONSTRAINT ex_appointments_patient_no_overlap "
        "EXCLUDE USING gist (patient_id WITH =, tstzrange(scheduled_at, ends_at, '[)') WITH &&) "
        f"WHERE ({ACTIVE})"
    )

    for value in AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    bind = op.get_bind()
    configured = bind.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM appointment_types) + (SELECT count(*) FROM schedule_rules) "
            "+ (SELECT count(*) FROM schedule_absences) + (SELECT count(*) FROM clinic_booking_settings) "
            "+ (SELECT count(*) FROM appointments WHERE appointment_type_id IS NOT NULL OR booked_via <> 'staff')"
        )
    ).scalar_one()
    if configured:
        raise RuntimeError(
            f"Refusing to downgrade: {configured} scheduling rows (types, schedules, absences, settings or "
            "typed/self-booked appointments) would be lost."
        )
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_patient_no_overlap")
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_staff_no_overlap")
    op.drop_index("ix_appointments_staff_scheduled_at", table_name="appointments")
    op.drop_constraint("fk_appointments_type_clinic", "appointments", type_="foreignkey")
    for column in ("booked_via", "appointment_type_id", "ends_at"):
        op.drop_column("appointments", column)
    op.drop_constraint("fk_staff_specialty_clinic", "staff", type_="foreignkey")
    op.drop_column("staff", "accepts_new_patients")
    op.drop_column("staff", "specialty_id")
    for table in (
        "schedule_absences",
        "schedule_rule_types",
        "schedule_rules",
        "clinic_booking_settings",
        "appointment_types",
        "specialties",
    ):
        op.drop_table(table)
    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
