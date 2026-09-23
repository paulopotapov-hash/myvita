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

from app.core.database import Base
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
    limiter.reset()
    yield


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
    # Other integration fixtures drop tables between tests; restore the schema
    # before transactional tests regardless of test order.
    Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, future=True, join_transaction_mode="create_savepoint")
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
