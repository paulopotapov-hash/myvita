"""
Test fixtures.

Requires a real Postgres reachable via TEST_DATABASE_URL (defaults to the
same DB the app uses locally). We use Postgres in tests — not SQLite —
because our migrations rely on Postgres-specific features (UUID, native
ENUM types, ON DELETE RESTRICT semantics) that SQLite doesn't replicate
faithfully. Testing against a fake dialect would hide real bugs.
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Public registration is enabled only for synthetic test fixtures. Production
# Compose explicitly defaults these controls to false.
os.environ.setdefault("ALLOW_PUBLIC_CLINIC_ONBOARDING", "true")
os.environ.setdefault("ALLOW_PUBLIC_PATIENT_REGISTRATION", "true")
os.environ.setdefault("ALLOW_DIRECT_STAFF_CREATION", "true")

from app.core.database import Base, audit_engine
from app.core.database import engine as app_engine
from app.core.rate_limit import limiter

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://myvita:myvita@localhost:5432/myvita"
)


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
    # Clear connections both before and after a test: module-scoped fixtures
    # may recreate ENUM types during their own teardown, after this fixture's
    # previous teardown has run.
    app_engine.dispose()
    limiter.reset()
    yield
    # Several integration modules deliberately drop/recreate PostgreSQL
    # ENUM-backed tables. The application audit logger uses its own global
    # pool, so a pooled connection can otherwise retain stale type OIDs and
    # fail a later audit insert with "cache lookup failed for type".
    app_engine.dispose()


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
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


# Phase 1 two-clinic dataset (module-scoped); see tests/phase1_world.py.
from tests.phase1_world import world  # noqa: E402, F401


@pytest.fixture(autouse=True)
def _reset_audit_pool():
    """Tests drop and recreate tables/enum types; pooled audit connections must not outlive them."""
    yield
    audit_engine.dispose()


class _AnyClinicMayRegister(list):
    """Test-only stand-in for settings.PUBLIC_CLINIC_IDS. Never use outside tests.

    Why it exists: POST /api/v1/patients/register only accepts clinics listed in
    PUBLIC_CLINIC_IDS (see patients/service.register_patient), but many fixtures
    (tests/phase1_world.py and ~12 test modules) create a clinic at runtime and
    then self-register patients into it, so its id cannot be known up front.
    This value is an *empty* list, so the public clinic directory behaves exactly
    as with the production default `[]`, yet reports every clinic as a member, so
    those registration fixtures keep working.

    Registration-security tests MUST override it with a real list via
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [...]); otherwise they
    would silently test this shim instead of the allowlist (see
    tests/test_registration_controls.py and tests/test_public_clinic_directory.py).

    TODO(follow-up): create test patients through a DB/service factory or the
    invitation flow instead of public self-registration, then delete this shim.
    """

    def __contains__(self, item: object) -> bool:
        return True


@pytest.fixture(scope="session", autouse=True)
def _test_clinics_accept_self_registration():
    from app.core.config import settings

    original = settings.PUBLIC_CLINIC_IDS
    settings.PUBLIC_CLINIC_IDS = _AnyClinicMayRegister()
    yield
    settings.PUBLIC_CLINIC_IDS = original
