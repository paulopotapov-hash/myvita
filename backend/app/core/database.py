"""
Database engine and session management.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)

# Audit rows are written in their own transaction while the request still holds a
# connection from `engine`. Drawing both from one pool deadlocks under load (every
# connection held by a request that is waiting for a second one), so audit writes
# use a dedicated pool. Audit holders never ask for another connection, so there is
# no circular wait; they are held for milliseconds.
audit_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=7,
    pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
    future=True,
)

AuditSessionLocal = sessionmaker(
    bind=audit_engine,
    autocommit=False,
    autoflush=False,
    future=True,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
