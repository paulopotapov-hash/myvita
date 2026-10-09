"""
Optional SIEM export for the centralized audit trail.

    audit_logs (PostgreSQL) ──► export_audit_events() ──► AuditSink.send(batch)
                                   │                          │
                                   │ cursor (timestamp, id)   └── HttpJsonAuditSink → POST JSON array
                                   ▼
                              cursor file

Design constraints (see docs/audit-logging.md § SIEM export):
  * Provider-neutral: any system that accepts an HTTPS POST of a JSON array
    works. No vendor SDK, no new runtime dependency (stdlib urllib).
  * Out-of-band: nothing here runs inside a clinical request. The exporter is
    invoked by `scripts/export_audit_siem.py` (cron / compose job). With
    SIEM_ENABLED=false it refuses to run and opens no connection.
  * At-least-once: a batch is acknowledged by advancing the cursor only after
    the sink accepted it. A crash between send and cursor save re-sends that
    batch; consumers deduplicate on `id` (UUID, globally unique).
  * Same privacy surface as the admin API: `event_metadata` is already
    allowlisted at write time by `sanitize_metadata`; the serializer here adds
    nothing and never reads other tables.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings, siem_endpoint_problem
from app.models.audit_log import AuditLog

logger = logging.getLogger("myvita.audit.siem")

EXPORT_SCHEMA_VERSION = 1
# Only these columns are ever serialized. `user_agent` is deliberately omitted
# (attacker-controlled free text with no SIEM value beyond the IP).
EXPORT_FIELDS = (
    "id",
    "timestamp",
    "clinic_id",
    "actor_user_id",
    "actor_email",
    "action",
    "resource_type",
    "resource_id",
    "result",
    "ip_address",
    "request_id",
    "metadata",
)


class SiemExportError(RuntimeError):
    """The sink did not accept a batch. The cursor is not advanced."""


class SiemDisabledError(RuntimeError):
    """Export was requested while SIEM_ENABLED is false."""


@dataclass(frozen=True, order=True)
class ExportCursor:
    """Position of the last acknowledged event: strictly increasing (timestamp, id)."""

    timestamp: datetime
    id: uuid.UUID

    def to_json(self) -> str:
        return json.dumps({"timestamp": self.timestamp.astimezone(UTC).isoformat(), "id": str(self.id)})

    @classmethod
    def from_json(cls, raw: str) -> ExportCursor:
        data = json.loads(raw)
        return cls(timestamp=datetime.fromisoformat(data["timestamp"]), id=uuid.UUID(data["id"]))


def serialize_event(row: AuditLog) -> dict[str, Any]:
    """Stable, JSON-safe representation. Exactly EXPORT_FIELDS, plus the schema version."""
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "id": str(row.id),
        "timestamp": row.timestamp.astimezone(UTC).isoformat(),
        "clinic_id": str(row.clinic_id) if row.clinic_id else None,
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "actor_email": row.actor_email,
        "action": row.action.value,
        "resource_type": row.resource_type,
        "resource_id": str(row.resource_id) if row.resource_id else None,
        "result": row.result.value,
        "ip_address": row.ip_address,
        "request_id": row.request_id,
        "metadata": row.event_metadata,
    }


class AuditSink(Protocol):
    def send(self, events: Sequence[dict[str, Any]]) -> None:
        """Deliver one batch. Must raise SiemExportError on any non-acceptance."""


class HttpJsonAuditSink:
    """POSTs each batch as a JSON array. Authenticates with `Authorization: Bearer <key>` when a key is set."""

    def __init__(self, endpoint: str, api_key: str | None, timeout_seconds: float) -> None:
        problem = siem_endpoint_problem(endpoint)
        if problem:
            raise ValueError(problem)
        self.endpoint = endpoint
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds

    def send(self, events: Sequence[dict[str, Any]]) -> None:
        body = json.dumps(list(events), separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "myvita-audit-export/1"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            # Bandit B310 is suppressed on the next line on purpose: the URL was checked in __init__ by
            # siem_endpoint_problem (https, or http to loopback only), so urllib's file:/ftp:/custom
            # schemes can never be reached here. Covered by test_sink_only_accepts_https_or_loopback_http.
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310  # nosec B310
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            # Never include the response body: it may echo our request (and the key is a header, not a body).
            raise SiemExportError(f"SIEM endpoint returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise SiemExportError(f"SIEM endpoint unreachable: {type(exc).__name__}") from None
        if not 200 <= status < 300:
            raise SiemExportError(f"SIEM endpoint returned HTTP {status}")


def sink_from_settings() -> HttpJsonAuditSink:
    if not settings.SIEM_ENABLED:
        raise SiemDisabledError("SIEM export is disabled (SIEM_ENABLED=false).")
    assert settings.SIEM_ENDPOINT is not None  # guaranteed by Settings validator
    key = settings.SIEM_API_KEY.get_secret_value() if settings.SIEM_API_KEY else None
    return HttpJsonAuditSink(settings.SIEM_ENDPOINT, key, settings.SIEM_TIMEOUT_SECONDS)


def _after_cursor(cursor: ExportCursor | None) -> Any:
    if cursor is None:
        return True
    return or_(
        AuditLog.timestamp > cursor.timestamp,
        and_(AuditLog.timestamp == cursor.timestamp, AuditLog.id > cursor.id),
    )


def fetch_batch(
    db: Session, cursor: ExportCursor | None, *, limit: int, until: datetime | None = None
) -> list[AuditLog]:
    query = select(AuditLog).where(_after_cursor(cursor))
    if until is not None:
        query = query.where(AuditLog.timestamp <= until)
    return list(db.scalars(query.order_by(AuditLog.timestamp, AuditLog.id).limit(limit)))


@dataclass
class ExportReport:
    batches: int = 0
    events: int = 0
    cursor: ExportCursor | None = None


def export_audit_events(
    db: Session,
    sink: AuditSink,
    *,
    cursor: ExportCursor | None,
    batch_size: int,
    max_batches: int,
    until: datetime | None = None,
    on_cursor: Any = None,
) -> ExportReport:
    """Stream events after `cursor` to `sink`, bounded by `batch_size * max_batches`.

    `on_cursor(cursor)` is called after every accepted batch so the caller can
    persist progress; a failing batch raises SiemExportError and leaves the
    cursor at the last acknowledged position (at-least-once).
    """
    report = ExportReport(cursor=cursor)
    for _ in range(max_batches):
        rows = fetch_batch(db, report.cursor, limit=batch_size, until=until)
        if not rows:
            break
        sink.send([serialize_event(row) for row in rows])
        last = rows[-1]
        report.cursor = ExportCursor(timestamp=last.timestamp, id=last.id)
        report.batches += 1
        report.events += len(rows)
        if on_cursor is not None:
            on_cursor(report.cursor)
    return report


def load_cursor(path: Path) -> ExportCursor | None:
    if not path.exists():
        return None
    return ExportCursor.from_json(path.read_text(encoding="utf-8"))


def save_cursor(path: Path, cursor: ExportCursor) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(cursor.to_json(), encoding="utf-8")
    tmp.replace(path)


def forbidden_terms_present(events: Iterable[dict[str, Any]], terms: Iterable[str]) -> list[str]:
    """Test helper used by the privacy suite: which of `terms` appear anywhere in the serialized batch."""
    blob = json.dumps(list(events)).lower()
    return [term for term in terms if term.lower() in blob]
