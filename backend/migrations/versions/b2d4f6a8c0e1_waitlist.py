"""Scheduling step 6: waiting list (entries and offers).

Revision ID: b2d4f6a8c0e1
Revises: 9a4c6e8f0b2d

- waitlist_entries: a patient's request for an earlier slot for one of their appointments,
  with the same professional or specialty; at most one active entry per appointment
  (partial unique index). Same-clinic composite keys everywhere.
- waitlist_offers: a freed slot offered to an entry, until expires_at; the same slot is
  offered once per entry.
- The runtime role gets no DELETE on either table and may UPDATE only the status columns
  (db_provisioning).
- Audit actions for joining, leaving and answering offers.

Nothing existing changes. Downgrade refuses while any entry exists; otherwise it drops the
two tables and their types. The audit enum labels stay.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d4f6a8c0e1"
down_revision: str | Sequence[str] | None = "9a4c6e8f0b2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS = {
    "waitlist_scope": ("professional", "specialty"),
    "waitlist_status": ("active", "fulfilled", "left", "closed"),
    "waitlist_offer_status": ("open", "accepted", "declined", "expired", "closed"),
}
AUDIT_ACTIONS = ("waitlist_joined", "waitlist_left", "waitlist_offer_accepted", "waitlist_offer_declined")


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("appointment_id", sa.UUID(), nullable=False),
        sa.Column("scope", _enum("waitlist_scope"), nullable=False),
        sa.Column("staff_id", sa.UUID(), nullable=False),
        sa.Column("specialty_id", sa.UUID(), nullable=False),
        sa.Column("appointment_type_id", sa.UUID(), nullable=False),
        sa.Column("status", _enum("waitlist_status"), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"], ["patients.id", "patients.clinic_id"], name="fk_waitlist_entries_patient_clinic", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_waitlist_entries_appointment_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"], name="fk_waitlist_entries_staff_clinic", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["specialty_id", "clinic_id"],
            ["specialties.id", "specialties.clinic_id"],
            name="fk_waitlist_entries_specialty_clinic",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_type_id", "clinic_id"],
            ["appointment_types.id", "appointment_types.clinic_id"],
            name="fk_waitlist_entries_type_clinic",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "clinic_id", name="uq_waitlist_entries_id_clinic"),
    )
    op.create_index("ix_waitlist_entries_patient_id", "waitlist_entries", ["patient_id"])
    op.create_index("ix_waitlist_entries_clinic_status", "waitlist_entries", ["clinic_id", "status"])
    op.create_index(
        "uq_waitlist_entries_active_appointment",
        "waitlist_entries",
        ["appointment_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "waitlist_offers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("clinic_id", sa.UUID(), nullable=False),
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("staff_id", sa.UUID(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", _enum("waitlist_offer_status"), server_default="open", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_appointment_id", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["entry_id", "clinic_id"], ["waitlist_entries.id", "waitlist_entries.clinic_id"], name="fk_waitlist_offers_entry_clinic", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["staff_id", "clinic_id"], ["staff.id", "staff.clinic_id"], name="fk_waitlist_offers_staff_clinic", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["new_appointment_id", "clinic_id"],
            ["appointments.id", "appointments.clinic_id"],
            name="fk_waitlist_offers_new_appointment_clinic",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("entry_id", "staff_id", "starts_at", name="uq_waitlist_offers_entry_slot"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_waitlist_offers_interval"),
    )
    op.create_index("ix_waitlist_offers_entry_id", "waitlist_offers", ["entry_id"])
    op.create_index(
        "ix_waitlist_offers_open_slot",
        "waitlist_offers",
        ["clinic_id", "staff_id", "starts_at"],
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index("ix_waitlist_offers_open_expiry", "waitlist_offers", ["expires_at"], postgresql_where=sa.text("status = 'open'"))

    for value in AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    bind = op.get_bind()
    entries = bind.execute(sa.text("SELECT count(*) FROM waitlist_entries")).scalar_one()
    if entries:
        raise RuntimeError(f"Refusing to downgrade: {entries} waiting-list entries would be lost.")
    op.drop_table("waitlist_offers")
    op.drop_table("waitlist_entries")
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
