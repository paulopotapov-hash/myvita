"""
Database-level least privilege and audit immutability.

These run real SQL as a freshly provisioned runtime role, so they need a
test-database login allowed to CREATE ROLE (CI's Postgres superuser is).
Without it they are skipped — unless MYVITA_REQUIRE_DB_PRIVILEGE_TESTS=1
(set in CI), in which case a missing privilege fails the run instead of
silently hiding these checks.
"""

import os
import secrets
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.db_provisioning import ProvisioningError, provision_runtime_role
from tests.conftest import TEST_DATABASE_URL


def _can_create_roles() -> bool:
    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with engine.connect() as connection:
            return bool(
                connection.execute(
                    text("SELECT rolcreaterole OR rolsuper FROM pg_roles WHERE rolname = current_user")
                ).scalar_one()
            )
    finally:
        engine.dispose()


@pytest.fixture()
def runtime_role():
    if not _can_create_roles():
        message = "test database login cannot CREATE ROLE"
        if os.environ.get("MYVITA_REQUIRE_DB_PRIVILEGE_TESTS") == "1":
            pytest.fail(message)
        pytest.skip(message)
    role = f"myvita_app_test_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(24)
    owner_engine = create_engine(TEST_DATABASE_URL, future=True)
    with owner_engine.begin() as connection:
        provision_runtime_role(connection, role=role, password=password)
    runtime_url = make_url(TEST_DATABASE_URL).set(username=role, password=password)
    runtime_engine = create_engine(runtime_url, future=True)
    yield owner_engine, runtime_engine, role
    runtime_engine.dispose()
    with owner_engine.begin() as connection:
        # PostgreSQL 16: a CREATEROLE (non-superuser) creator holds ADMIN on
        # the role and must take membership before DROP OWNED.
        connection.execute(text(f'GRANT "{role}" TO CURRENT_USER'))
        connection.execute(text(f'DROP OWNED BY "{role}"'))
        connection.execute(text(f'DROP ROLE "{role}"'))
    owner_engine.dispose()


def _seed_audit_row(engine) -> uuid.UUID:
    row_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO audit_logs (id, action, result) VALUES (:id, 'logout', 'success')"),
            {"id": row_id},
        )
    return row_id


INSUFFICIENT_PRIVILEGE = "42501"


def _expect_denied(engine, statement: str, params: dict | None = None) -> str:
    """Run a statement that must be refused; return the server message."""
    with pytest.raises((ProgrammingError, DBAPIError)) as excinfo:
        with engine.begin() as connection:
            connection.execute(text(statement), params or {})
    assert excinfo.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE, str(excinfo.value.orig)
    return str(excinfo.value.orig)


def test_runtime_role_can_append_but_never_rewrite_audit_history(runtime_role):
    _, runtime, _ = runtime_role
    row_id = _seed_audit_row(runtime)
    with runtime.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM audit_logs WHERE id = :id"), {"id": row_id}).scalar() == 1

    _expect_denied(
        runtime, "UPDATE audit_logs SET action = 'login_success' WHERE id = :id", {"id": row_id}
    )
    _expect_denied(runtime, "DELETE FROM audit_logs WHERE id = :id", {"id": row_id})
    _expect_denied(runtime, "TRUNCATE audit_logs")


def test_runtime_role_has_application_dml_but_no_ddl(runtime_role):
    _, runtime, _ = runtime_role
    clinic_id = uuid.uuid4()
    with runtime.begin() as connection:
        connection.execute(text("INSERT INTO clinics (id, name) VALUES (:id, 'Synthetic')"), {"id": clinic_id})
        connection.execute(text("UPDATE clinics SET name = 'Synthetic 2' WHERE id = :id"), {"id": clinic_id})
        connection.execute(text("DELETE FROM clinics WHERE id = :id"), {"id": clinic_id})
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar()

    _expect_denied(runtime, "CREATE TABLE intruder (id int)")
    _expect_denied(runtime, "DROP TABLE clinics")
    _expect_denied(runtime, "ALTER TABLE users ADD COLUMN backdoor text")
    _expect_denied(runtime, "UPDATE alembic_version SET version_num = 'x'")
    _expect_denied(runtime, "ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_append_only")


def test_runtime_role_attributes_are_minimal(runtime_role):
    owner, _, role = runtime_role
    with owner.connect() as connection:
        attrs = connection.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolcanlogin "
                "FROM pg_roles WHERE rolname = :role"
            ),
            {"role": role},
        ).one()
    assert tuple(attrs) == (False, False, False, False, False, True)


def test_provisioning_is_idempotent_and_rejects_unsafe_input(runtime_role):
    owner, _, role = runtime_role
    with owner.begin() as connection:
        provision_runtime_role(connection, role=role, password=secrets.token_urlsafe(24))
    with owner.begin() as connection:
        current = connection.execute(text("SELECT current_user")).scalar_one()
        with pytest.raises(ProvisioningError):
            provision_runtime_role(connection, role=current, password=secrets.token_urlsafe(24))
        with pytest.raises(ProvisioningError):
            provision_runtime_role(connection, role='bad"; DROP ROLE x; --', password=secrets.token_urlsafe(24))
        with pytest.raises(ProvisioningError):
            provision_runtime_role(connection, role=role, password="short")


def test_audit_triggers_block_owner_rewrites_but_allow_fk_set_null(engine):
    """Even the schema owner cannot edit or delete audit rows by accident."""
    row_id = _seed_audit_row(engine)
    assert "append-only" in _expect_denied(
        engine, "UPDATE audit_logs SET action = 'login_success' WHERE id = :id", {"id": row_id}
    )
    assert "append-only" in _expect_denied(engine, "DELETE FROM audit_logs WHERE id = :id", {"id": row_id})
    assert "append-only" in _expect_denied(engine, "TRUNCATE audit_logs")

    # Deleting a referenced user must still work (FK ON DELETE SET NULL),
    # keeping the audit row and its actor_email.
    user_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, full_name, role, is_active, token_epoch) "
                "VALUES (:id, 'gone@example.test', 'x', 'Gone', 'patient', true, 0)"
            ),
            {"id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO audit_logs (id, action, result, actor_user_id, actor_email) "
                "VALUES (:id, 'logout', 'success', :uid, 'gone@example.test')"
            ),
            {"id": uuid.uuid4(), "uid": user_id},
        )
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        row = connection.execute(
            text("SELECT actor_user_id, actor_email FROM audit_logs WHERE actor_email = 'gone@example.test'")
        ).one()
    assert row.actor_user_id is None
    assert row.actor_email == "gone@example.test"
