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

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://myvita:myvita@localhost:5432/myvita"
)


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
