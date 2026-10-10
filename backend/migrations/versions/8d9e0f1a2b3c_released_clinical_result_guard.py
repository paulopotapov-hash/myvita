"""Database guard: a released clinical result can never be updated or deleted.

Revision ID: 8d9e0f1a2b3c
Revises: 7c8d9e0f1a2b

Until now the immutability of released results (P2.4) was enforced by the
services, an ORM flush guard and the runtime role's column-level privileges.
None of those stopped a bulk/raw SQL UPDATE of a released row's clinical
columns by the runtime role. This row trigger does, for every role (the owner
included) while it is enabled; only the table owner or a superuser can disable
it. It follows the audit_logs precedent (migration f6a7b8c9d0e1):

- UPDATE of a row whose OLD status is 'released' -> rejected (any column);
- DELETE of a row whose OLD status is 'released' -> rejected;
- drafts stay editable/deletable, and the draft -> released transition is allowed
  (its OLD status is 'draft').

Residual risk (documented in app/models/clinical_result.py and
docs/data-protection-readiness.md): the table owner or a superuser can disable
or drop the trigger; this is not protection against the database administrator. TRUNCATE is not granted to the runtime role.
No data is changed by this migration. Downgrade drops the trigger and function.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8d9e0f1a2b3c"
down_revision: str | Sequence[str] | None = "7c8d9e0f1a2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION clinical_results_release_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'released' THEN
        RAISE EXCEPTION 'clinical result % is released and immutable: % rejected', OLD.id, TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;
"""


def upgrade() -> None:
    op.execute(GUARD_FUNCTION)
    op.execute(
        "CREATE TRIGGER clinical_results_released_immutable BEFORE UPDATE OR DELETE ON clinical_results "
        "FOR EACH ROW EXECUTE FUNCTION clinical_results_release_guard()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS clinical_results_released_immutable ON clinical_results")
    op.execute("DROP FUNCTION IF EXISTS clinical_results_release_guard()")
