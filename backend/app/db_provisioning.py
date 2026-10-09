"""
Provision the least-privilege PostgreSQL role the application runs as.

Run as the schema owner (the role that runs Alembic), after migrations:

    APP_DB_ROLE=myvita_app APP_DB_PASSWORD=... python -m app.db_provisioning

Idempotent: safe to run on every deployment. The runtime role ends up with:
- LOGIN, and none of SUPERUSER / CREATEDB / CREATEROLE / REPLICATION /
  BYPASSRLS (verified; an existing role with any of them is refused);
- CONNECT on the database and USAGE (never CREATE) on schema public, so it
  cannot create, alter or drop objects;
- SELECT/INSERT/UPDATE/DELETE on application tables (including tables
  created by future migrations, via default privileges);
- SELECT/INSERT only on audit_logs and documents — it can append to each but
  never edit, delete or truncate them (a database trigger also stops
  accidental audit-history rewrites; documents are append-only by decision D3);
- SELECT/INSERT plus column-level UPDATE (no DELETE) on conversations,
  messages, invitations and appointment_requests (see COLUMN_UPDATE_TABLES);
- no privilege at all on the deprecated Parent A tables (NO_ACCESS_TABLES);
- SELECT only on alembic_version.

Default privileges grant full DML on new tables; a future append-only
table must be added to APPEND_ONLY_TABLES here.
"""

import os
import re
import sys

from sqlalchemy import String, create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

APPEND_ONLY_TABLES = ("audit_logs", "documents")
READ_ONLY_TABLES = ("alembic_version",)
# Tables the app inserts into and updates only specific columns of (column-level UPDATE,
# no DELETE). Each column list is exactly what the services write, including onupdate columns.
COLUMN_UPDATE_TABLES: dict[str, tuple[str, ...]] = {
    "conversations": ("updated_at",),
    "messages": ("read_at",),
    "invitations": ("status", "accepted_at"),
    "appointment_requests": ("status", "decided_by_user_id", "decided_at", "appointment_id", "updated_at"),
}
# Deprecated tables kept by integration decision (app/core/schema_policy.py): the app never
# touches them, so the runtime role gets no privilege at all on them.
NO_ACCESS_TABLES = (
    "clinical_conversations",
    "clinical_messages",
    "clinical_documents",
    "clinical_document_versions",
    "deprecated_notification_targets",
)
_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class ProvisioningError(RuntimeError):
    pass


def _quote_literal(connection: Connection, value: str) -> str:
    processor = String().literal_processor(dialect=connection.dialect)
    assert processor is not None
    return str(processor(value))


def provision_runtime_role(connection: Connection, *, role: str, password: str) -> None:
    if not _ROLE_NAME.match(role):
        raise ProvisioningError("APP_DB_ROLE must be a lower-case PostgreSQL identifier.")
    if len(password) < 16:
        raise ProvisioningError("APP_DB_PASSWORD must be at least 16 characters.")
    owner = connection.execute(text("SELECT current_user")).scalar_one()
    if role == owner:
        raise ProvisioningError("The runtime role must differ from the schema owner running migrations.")
    database = connection.execute(text("SELECT current_database()")).scalar_one()

    exists = connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}).first()
    password_sql = _quote_literal(connection, password)
    verb = "ALTER" if exists else "CREATE"
    try:
        # Elevated attributes all default to false, and a non-superuser owner
        # may not even name them; they are verified below instead.
        connection.execute(text(f'{verb} ROLE "{role}" LOGIN PASSWORD {password_sql}'))
    except DBAPIError as exc:
        # The failing statement contains the password: never let it reach
        # logs or tracebacks.
        sqlstate = getattr(exc.orig, "sqlstate", None)
        raise ProvisioningError(f"Could not {verb.lower()} role '{role}' (SQLSTATE {sqlstate}).") from None

    attributes = connection.execute(
        text(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = :role"
        ),
        {"role": role},
    ).one()
    if any(attributes):
        raise ProvisioningError(
            f"Role '{role}' has elevated attributes (SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS); "
            "remove them manually before provisioning."
        )

    statements = [
        f'GRANT CONNECT ON DATABASE "{database}" TO "{role}"',
        f'GRANT USAGE ON SCHEMA public TO "{role}"',
        f'REVOKE CREATE ON SCHEMA public FROM "{role}"',
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"',
        f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"',
        f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA public '
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"',
        f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA public '
        f'GRANT USAGE, SELECT ON SEQUENCES TO "{role}"',
    ]
    for table in APPEND_ONLY_TABLES:
        statements.append(f'REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON "{table}" FROM "{role}"')
        statements.append(f'GRANT SELECT, INSERT ON "{table}" TO "{role}"')
    for table in READ_ONLY_TABLES:
        statements.append(f'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON "{table}" FROM "{role}"')
        statements.append(f'GRANT SELECT ON "{table}" TO "{role}"')
    for table, columns in COLUMN_UPDATE_TABLES.items():
        column_list = ", ".join(f'"{column}"' for column in columns)
        statements.append(f'REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON "{table}" FROM "{role}"')
        statements.append(f'GRANT SELECT, INSERT ON "{table}" TO "{role}"')
        statements.append(f'GRANT UPDATE ({column_list}) ON "{table}" TO "{role}"')
    for table in NO_ACCESS_TABLES:
        # Tolerate databases where a deprecated table never existed (e.g. built from Parent B).
        statements.append(
            f"DO $$ BEGIN IF to_regclass('public.\"{table}\"') IS NOT NULL THEN "
            f'REVOKE ALL ON "{table}" FROM "{role}"; END IF; END $$'
        )
    for statement in statements:
        connection.execute(text(statement))


def main() -> int:
    url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    role = os.environ.get("APP_DB_ROLE", "")
    password = os.environ.get("APP_DB_PASSWORD", "")
    if not url:
        print("MIGRATION_DATABASE_URL (or DATABASE_URL) must point at the schema owner.", file=sys.stderr)
        return 2
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as connection:
            provision_runtime_role(connection, role=role, password=password)
    except ProvisioningError as exc:
        print(f"Provisioning refused: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    # Never print the password or the URL.
    print(f"Runtime role '{role}' provisioned with least privilege.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
