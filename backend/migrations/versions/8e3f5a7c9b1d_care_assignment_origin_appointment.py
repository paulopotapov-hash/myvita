"""Care assignment: the appointment that created it automatically.

Revision ID: 8e3f5a7c9b1d
Revises: 7d2e4b9a1c3f

- appointments: UNIQUE (id, clinic_id), the target of same-clinic composite keys.
- clinical_care_assignments.origin_appointment_id (NULL = assigned by an admin), with a
  same-clinic foreign key to that appointment and an index.
- Backfill: an active link that a booking created (audit "care_assignment_created" with
  via "appointment") gets that appointment as its origin, when the appointment still
  exists in the same clinic for the same patient and professional. Every other link stays
  NULL, so it is never ended automatically.

Downgrade drops the column, key, index and unique constraint; no row is deleted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e3f5a7c9b1d"
down_revision: str | Sequence[str] | None = "7d2e4b9a1c3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_appointments_id_clinic", "appointments", ["id", "clinic_id"])
    op.add_column("clinical_care_assignments", sa.Column("origin_appointment_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_care_assignment_origin_appointment_clinic",
        "clinical_care_assignments",
        "appointments",
        ["origin_appointment_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_care_assignments_origin_appointment", "clinical_care_assignments", ["origin_appointment_id"])
    op.execute(
        "UPDATE clinical_care_assignments c SET origin_appointment_id = a.id "
        "FROM audit_logs l JOIN appointments a "
        "  ON a.id::text = l.metadata ->> 'appointment_id' "
        "WHERE l.action::text = 'care_assignment_created' AND l.resource_type = 'care_assignment' "
        "  AND l.metadata ->> 'via' = 'appointment' AND l.resource_id = c.id "
        "  AND c.active IS TRUE AND a.clinic_id = c.clinic_id "
        "  AND a.patient_id = c.patient_id AND a.staff_id = c.staff_id"
    )


def downgrade() -> None:
    op.drop_index("ix_care_assignments_origin_appointment", table_name="clinical_care_assignments")
    op.drop_constraint("fk_care_assignment_origin_appointment_clinic", "clinical_care_assignments", type_="foreignkey")
    op.drop_column("clinical_care_assignments", "origin_appointment_id")
    op.drop_constraint("uq_appointments_id_clinic", "appointments", type_="unique")
