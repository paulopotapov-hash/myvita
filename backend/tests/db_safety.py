"""
Guard rails that stop the test suite from ever touching a non-test database.

The suite resets the whole `public` schema of the database it is pointed at
(drop + `alembic upgrade head`) and truncates every table between tests.
That is only acceptable on a disposable database, so before anything is
imported or connected we require an explicit TEST_DATABASE_URL and refuse
to run unless it unmistakably names a local test database.
"""

import os

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
REQUIRED_DATABASE_SUFFIX = "_test"
EXTRA_HOSTS_ENV = "MYVITA_TEST_DB_ALLOWED_HOSTS"


class UnsafeTestDatabaseError(RuntimeError):
    """Raised when the configured test database could be a real database."""


def validate_test_database_url(url: str | None, *, environment: str | None, extra_hosts: str | None) -> str:
    """Return the URL unchanged if it is safe for destructive test setup."""
    if not url:
        raise UnsafeTestDatabaseError(
            "TEST_DATABASE_URL is not set. The test suite resets its database, so it never "
            "falls back to DATABASE_URL or a default. Point it at a dedicated database whose "
            f"name ends in '{REQUIRED_DATABASE_SUFFIX}'."
        )
    if environment in {"production", "staging"}:
        raise UnsafeTestDatabaseError(f"Refusing to run tests with ENVIRONMENT={environment}.")
    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise UnsafeTestDatabaseError("TEST_DATABASE_URL is not a valid SQLAlchemy URL.") from exc
    if not parsed.drivername.startswith("postgresql"):
        raise UnsafeTestDatabaseError("TEST_DATABASE_URL must point to PostgreSQL.")
    database = parsed.database or ""
    if not database.endswith(REQUIRED_DATABASE_SUFFIX):
        raise UnsafeTestDatabaseError(
            f"Refusing to use database '{database}': test database names must end in "
            f"'{REQUIRED_DATABASE_SUFFIX}' (for example 'myvita_test')."
        )
    allowed_hosts = set(LOCAL_HOSTS)
    if extra_hosts:
        allowed_hosts |= {host.strip() for host in extra_hosts.split(",") if host.strip()}
    if (parsed.host or "localhost") not in allowed_hosts:
        raise UnsafeTestDatabaseError(
            f"Refusing to use test database host '{parsed.host}'. Only local hosts are allowed "
            f"unless explicitly listed in {EXTRA_HOSTS_ENV}."
        )
    return url


def require_safe_test_database_url() -> str:
    return validate_test_database_url(
        os.environ.get("TEST_DATABASE_URL"),
        environment=os.environ.get("ENVIRONMENT"),
        extra_hosts=os.environ.get(EXTRA_HOSTS_ENV),
    )
