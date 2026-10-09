"""
Test fixtures.

Requires a real, dedicated Postgres database named by TEST_DATABASE_URL
(see tests/db_safety.py — the suite refuses to start otherwise). We use
Postgres in tests — not SQLite — because our migrations rely on
Postgres-specific features (UUID, native ENUM types, ON DELETE RESTRICT
semantics, triggers) that SQLite doesn't replicate faithfully.

The schema is built once per session by running the real Alembic
migrations (never `Base.metadata.create_all`), so every test exercises the
schema production actually gets. Tests are isolated by truncating every
table before each test instead of dropping the schema.
"""

import os
import tempfile
from pathlib import Path

import pytest

from tests.db_safety import UnsafeTestDatabaseError, require_safe_test_database_url

try:
    TEST_DATABASE_URL = require_safe_test_database_url()
except UnsafeTestDatabaseError as exc:  # pragma: no cover - exercised manually / in CI misconfiguration
    pytest.exit(f"Unsafe test database configuration: {exc}", returncode=4)

# The application, Alembic and the audit logger must all write to the test
# database — never to whatever DATABASE_URL happens to be in the environment.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["MIGRATION_DATABASE_URL"] = TEST_DATABASE_URL
# Audit timestamps are asserted as UTC; psycopg honours PGTZ for the session
# timezone, so the suite does not depend on the local cluster's default.
os.environ.setdefault("PGTZ", "UTC")
# Document uploads need a writable directory; the production default is not.
os.environ.setdefault("DOCUMENT_STORAGE_DIR", tempfile.mkdtemp(prefix="myvita-test-documents-"))

# Public registration is enabled only for synthetic test fixtures. Production
# Compose explicitly defaults these controls to false.
os.environ.setdefault("ALLOW_PUBLIC_CLINIC_ONBOARDING", "true")
os.environ.setdefault("ALLOW_PUBLIC_PATIENT_REGISTRATION", "true")
os.environ.setdefault("ALLOW_DIRECT_STAFF_CREATION", "true")
# Most suites predate mandatory staff MFA and exercise other behaviour; the
# MFA suites switch enforcement on explicitly (see tests/test_mfa.py).
os.environ.setdefault("MFA_REQUIRED_FOR_STAFF", "false")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core import mfa  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import audit_engine  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
AUDIT_TRIGGERS = ("audit_logs_append_only", "audit_logs_no_truncate")


def csrf_headers(client) -> dict:
    """
    Reads the (non-httpOnly) CSRF cookie the app set after login/registration
    and returns it as the header the frontend is expected to send back on
    every state-changing authenticated request. Test helper only — the
    frontend does the equivalent by reading document.cookie.
    """
    from app.core.config import settings

    token = client.cookies.get(settings.CSRF_COOKIE_NAME)
    if not token:
        return {}
    return {settings.CSRF_HEADER_NAME: token}


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def reset_schema_to_head(url: str) -> None:
    """Drop everything in the (validated) test database and migrate to head."""
    engine = create_engine(url, future=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    command.upgrade(alembic_config(), "head")


def truncate_all_tables(url: str) -> None:
    engine = create_engine(url, future=True)
    with engine.begin() as connection:
        tables = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'")
        ).scalars()
        names = ", ".join(f'"{name}"' for name in tables)
        if names:
            # The audit table rejects TRUNCATE by design; only the owner (the
            # test role here) can lift that guard, and only inside this
            # transaction.
            for trigger in AUDIT_TRIGGERS:
                connection.execute(text(f"ALTER TABLE audit_logs DISABLE TRIGGER {trigger}"))
            connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
            for trigger in AUDIT_TRIGGERS:
                connection.execute(text(f"ALTER TABLE audit_logs ENABLE TRIGGER {trigger}"))
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema():
    reset_schema_to_head(TEST_DATABASE_URL)
    yield


# Set by tests/phase1_world.world while its module-scoped two-clinic dataset is
# alive; per-test truncation would wipe it. Other fixtures named `world`
# (e.g. test_clinical_security_matrix) are function-scoped and unaffected.
module_world_active = False


@pytest.fixture(autouse=True)
def _clean_database(_migrated_schema):
    if not module_world_active:
        truncate_all_tables(TEST_DATABASE_URL)
    yield


@pytest.fixture(autouse=True)
def _reset_audit_pool():
    """The audit logger has its own pool; drop its connections between tests so a
    truncated/reset schema never meets a stale pooled connection."""
    yield
    audit_engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """
    The rate limiter's in-memory storage is process-global (by design — it
    has to survive across requests within one running app). Left alone, one
    test's login/registration attempts would count against another test's
    quota since the test client always calls from the same fake address.
    Reset before every test so each one gets a fresh bucket, exactly like a
    real deployment where these limits reset per client per time window.
    """
    limiter.reset()
    yield


@pytest.fixture(scope="session")
def engine(_migrated_schema):
    eng = create_engine(TEST_DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    """Each test runs inside an outer transaction + SAVEPOINT that's rolled
    back afterwards, so tests never see each other's data and a session.commit()
    inside the test code doesn't end the outer transaction early."""
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, future=True, join_transaction_mode="create_savepoint")
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# --- account lifecycle / MFA fixtures (helpers live in tests/account_support.py) ---


@pytest.fixture()
def client():
    from tests.account_support import http_client  # imports conftest itself

    with http_client() as c:
        yield c


@pytest.fixture()
def second_client():
    """Independent cookie jar on the same app (another browser)."""
    from fastapi.testclient import TestClient

    from app.main import app  # after the environment above is in place

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def mfa_enforced(monkeypatch):
    """Switches mandatory staff MFA on immediately."""
    monkeypatch.setattr(settings, "MFA_REQUIRED_FOR_STAFF", True)


@pytest.fixture()
def enforce_mfa(monkeypatch):
    """Call to switch mandatory staff MFA on after fixtures/accounts exist."""
    return lambda: monkeypatch.setattr(settings, "MFA_REQUIRED_FOR_STAFF", True)


@pytest.fixture()
def totp_clock(monkeypatch):
    """Deterministic TOTP time steps (tests/account_support.TotpClock)."""
    from tests.account_support import TotpClock

    clock = TotpClock()
    monkeypatch.setattr(mfa, "current_step", lambda now=None: clock.step)
    return clock


# Phase 1 two-clinic dataset (module-scoped); see tests/phase1_world.py.
from tests.phase1_world import world  # noqa: E402, F401
