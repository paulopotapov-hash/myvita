"""Phase B history, tenant integrity and lifecycle audit actions.

Revision ID: b2c3d4e5f6a7
Revises: af1b2c3d4e5f
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "af1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for action in ("staff_deactivated", "staff_reactivated"):
        op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{action}'")
    op.add_column("medical_records", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.create_unique_constraint("uq_patients_id_clinic", "patients", ["id", "clinic_id"])
    op.create_unique_constraint("uq_staff_id_clinic", "staff", ["id", "clinic_id"])
    for table, constraint in (
        ("appointments", "appointments_patient_id_fkey"),
        ("appointments", "appointments_staff_id_fkey"),
        ("medical_records", "medical_records_patient_id_fkey"),
        ("medications", "medications_patient_id_fkey"),
        ("consents", "consents_patient_id_fkey"),
    ):
        op.drop_constraint(constraint, table, type_="foreignkey")
    for table, name in (
        ("appointments", "fk_appointments_patient_clinic"),
        ("medical_records", "fk_records_patient_clinic"),
        ("medications", "fk_medications_patient_clinic"),
        ("consents", "fk_consents_patient_clinic"),
    ):
        op.create_foreign_key(
            name, table, "patients", ["patient_id", "clinic_id"], ["id", "clinic_id"], ondelete="RESTRICT"
        )
    op.create_foreign_key(
        "fk_appointments_staff_clinic",
        "appointments",
        "staff",
        ["staff_id", "clinic_id"],
        ["id", "clinic_id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "medical_record_revisions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "record_id", sa.UUID(), sa.ForeignKey("medical_records.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("clinic_id", sa.UUID(), sa.ForeignKey("clinics.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column(
            "editor_user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["patient_id", "clinic_id"],
            ["patients.id", "patients.clinic_id"],
            name="fk_revisions_patient_clinic",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_record_revisions_record_version",
        "medical_record_revisions",
        ["record_id", "version"],
        unique=True,
    )
    op.execute(
        """CREATE FUNCTION reject_immutable_clinical_history() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'clinical history is immutable'; END; $$ LANGUAGE plpgsql"""
    )
    for table in ("consents", "medical_record_revisions"):
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_immutable_clinical_history()"
        )


def downgrade() -> None:
    for table in ("consents", "medical_record_revisions"):
        op.execute(f"DROP TRIGGER IF EXISTS immutable_{table} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_immutable_clinical_history")
    op.drop_table("medical_record_revisions")
    op.drop_constraint("fk_appointments_staff_clinic", "appointments", type_="foreignkey")
    for table, name in (
        ("appointments", "fk_appointments_patient_clinic"),
        ("medical_records", "fk_records_patient_clinic"),
        ("medications", "fk_medications_patient_clinic"),
        ("consents", "fk_consents_patient_clinic"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
    for table, target, column, ondelete in (
        ("appointments", "patients", "patient_id", "CASCADE"),
        ("appointments", "staff", "staff_id", "RESTRICT"),
        ("medical_records", "patients", "patient_id", "RESTRICT"),
        ("medications", "patients", "patient_id", "RESTRICT"),
        ("consents", "patients", "patient_id", "RESTRICT"),
    ):
        op.create_foreign_key(None, table, target, [column], ["id"], ondelete=ondelete)
    op.drop_constraint("uq_staff_id_clinic", "staff", type_="unique")
    op.drop_constraint("uq_patients_id_clinic", "patients", type_="unique")
    op.drop_column("medical_records", "version")
