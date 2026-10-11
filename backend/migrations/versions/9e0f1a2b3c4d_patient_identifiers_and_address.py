"""Patient identifiers (NIF, NISS) and postal address.

Revision ID: 9e0f1a2b3c4d
Revises: 8d9e0f1a2b3c

- patients.nif, patients.niss: optional personal identifiers. The existing
  national_health_number is the Nº de utente do SNS.
- patients.address_street / address_postal_code / address_locality.
- One NIF per clinic, only when filled in (partial unique index).
- Audit actions for revealing and changing identifiers.

No existing data is changed. Downgrade drops the columns and the index; the
audit enum labels stay (PostgreSQL cannot drop enum labels, and historical
audit rows may hold them).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9e0f1a2b3c4d"
down_revision: str | Sequence[str] | None = "8d9e0f1a2b3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("nif", sa.String(length=9), nullable=True))
    op.add_column("patients", sa.Column("niss", sa.String(length=11), nullable=True))
    op.add_column("patients", sa.Column("address_street", sa.String(length=200), nullable=True))
    op.add_column("patients", sa.Column("address_postal_code", sa.String(length=8), nullable=True))
    op.add_column("patients", sa.Column("address_locality", sa.String(length=100), nullable=True))
    op.create_index(
        "uq_patients_clinic_nif",
        "patients",
        ["clinic_id", "nif"],
        unique=True,
        postgresql_where=sa.text("nif IS NOT NULL"),
    )
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'patient_identifiers_viewed'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'patient_identifiers_updated'")


def downgrade() -> None:
    op.drop_index("uq_patients_clinic_nif", table_name="patients")
    for column in ("address_locality", "address_postal_code", "address_street", "niss", "nif"):
        op.drop_column("patients", column)
