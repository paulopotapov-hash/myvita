"""The current time for the scheduling rules (a function, so tests can move the clock)."""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
