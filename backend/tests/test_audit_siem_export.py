"""
Phase 8.1 — optional SIEM export of the centralized audit trail.

Uses a local in-process HTTP server as the "SIEM"; never a real one. Verifies
the privacy surface, disabled-by-default behaviour, every failure mode, batch
bounds and the at-least-once cursor semantics.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.core import audit_export
from app.core.audit import record_audit_event
from app.core.audit_export import (
    EXPORT_FIELDS,
    ExportCursor,
    HttpJsonAuditSink,
    SiemDisabledError,
    SiemExportError,
    export_audit_events,
    fetch_batch,
    forbidden_terms_present,
    load_cursor,
    save_cursor,
    serialize_event,
    sink_from_settings,
)
from app.core.config import Settings, settings
from app.models import AuditAction, AuditLog, AuditResult
from tests.phase1_world import PASSWORD, RECORD_MARKER, World

# --------------------------------------------------------------------------
# Fake SIEM
# --------------------------------------------------------------------------


class _FakeSiem:
    """Scriptable HTTP sink: each request pops the next behaviour from `plan`."""

    def __init__(self) -> None:
        self.received: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self.plan: list[int | str] = []
        self.lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                with fake.lock:
                    behaviour: int | str = fake.plan.pop(0) if fake.plan else 200
                    fake.headers.append({k.lower(): v for k, v in self.headers.items()})
                if behaviour == "hang":
                    time.sleep(1.5)
                    behaviour = 200
                if behaviour == 200:
                    with fake.lock:
                        fake.received.append({"batch": json.loads(body), "path": self.path})
                self.send_response(int(behaviour))
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_args: Any) -> None:
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/ingest"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    @property
    def events(self) -> list[dict[str, Any]]:
        return [event for item in self.received for event in item["batch"]]


@pytest.fixture()
def siem():
    fake = _FakeSiem()
    yield fake
    fake.close()


def _settings(**overrides: Any) -> Settings:
    base = {"JWT_SECRET_KEY": "x" * 40, "ENVIRONMENT": "development"}
    return Settings(**{**base, **overrides})


def _seed(world: World, n: int, marker: str) -> list[uuid.UUID]:
    for index in range(n):
        record_audit_event(
            action=AuditAction.LOGOUT,
            result=AuditResult.SUCCESS,
            clinic_id=world.a.clinic_id,
            actor_user_id=world.a.doctor.user_id,
            actor_email=f"{marker}-{index}@phase81.example",
            metadata={"count": index, "password": "hunter2", "token": "jwt-secret"},
        )
    with world.db() as db:
        return list(
            db.scalars(
                select(AuditLog.id)
                .where(AuditLog.actor_email.like(f"{marker}-%"))
                .order_by(AuditLog.timestamp, AuditLog.id)
            )
        )


# --------------------------------------------------------------------------
# Configuration / disabled
# --------------------------------------------------------------------------


def test_siem_is_disabled_by_default_and_opens_no_connection(monkeypatch, siem):
    assert settings.SIEM_ENABLED is False
    monkeypatch.setattr(settings, "SIEM_ENDPOINT", siem.url)
    with pytest.raises(SiemDisabledError):
        sink_from_settings()
    assert siem.received == [] and siem.headers == []


def test_enabling_siem_requires_a_valid_endpoint_and_https_in_production():
    with pytest.raises(ValueError, match="SIEM_ENDPOINT"):
        _settings(SIEM_ENABLED=True)
    with pytest.raises(ValueError, match="SIEM_ENDPOINT"):
        _settings(SIEM_ENABLED=True, SIEM_ENDPOINT="ftp://siem.example")
    with pytest.raises(ValueError, match="HTTPS"):
        _settings(
            SIEM_ENABLED=True,
            SIEM_ENDPOINT="http://siem.example/ingest",
            ENVIRONMENT="production",
            DATABASE_URL="postgresql+psycopg://prod:S3cureP@ss@db/prod",
            JWT_SECRET_KEY="qwertyuiopasdfghjklzxcvbnm1234567890QWERTY",
            CORS_ORIGINS=["https://app.example"],
            ALLOWED_HOSTS=["api.example"],
        )
    ok = _settings(SIEM_ENABLED=True, SIEM_ENDPOINT="http://localhost:9/ingest", SIEM_API_KEY="k-123")
    assert ok.SIEM_API_KEY is not None and "k-123" not in repr(ok.SIEM_API_KEY) and "k-123" not in str(ok)


def test_malformed_endpoint_is_rejected_before_any_network_call():
    for bad in ("", "not-a-url", "file:///etc/passwd", "https://"):
        with pytest.raises(ValueError):
            HttpJsonAuditSink(bad, None, 1.0)


# --------------------------------------------------------------------------
# Serialization / privacy
# --------------------------------------------------------------------------


def test_serialized_event_has_exactly_the_safe_fields(world: World):
    ids = _seed(world, 1, f"shape-{uuid.uuid4().hex[:6]}")
    with world.db() as db:
        row = db.get(AuditLog, ids[0])
        assert row is not None
        event = serialize_event(row)
    assert set(event) == {*EXPORT_FIELDS, "schema_version"}
    assert event["id"] == str(ids[0]) and event["request_id"] is None or isinstance(event["request_id"], str)
    assert event["timestamp"].endswith("+00:00")
    assert event["metadata"] == {"count": 0}  # write-time sanitizer already dropped password/token
    assert "user_agent" not in event


def test_export_never_contains_secrets_or_clinical_content(world: World, siem, monkeypatch):
    doctor, patient = world.a.doctor, world.a.patients["a1"]
    body = f"SIEM-MESSAGE-{uuid.uuid4().hex}"
    conversation = doctor.post("/api/v1/conversations", json={"patient_id": patient.patient_id})
    assert conversation.status_code in (200, 201)
    assert (
        doctor.post(
            f"/api/v1/conversations/{conversation.json()['id']}/messages", json={"body": body}
        ).status_code
        == 201
    )
    uploaded = doctor.client.post(
        f"/api/v1/patients/{patient.patient_id}/documents",
        files={"file": ("siem-secret.pdf", b"%PDF-1.4 SIEM-DOCUMENT-CONTENT", "application/pdf")},
        headers={"X-CSRF-Token": doctor.csrf_token or ""},
    )
    assert uploaded.status_code == 201

    monkeypatch.setattr(settings, "SIEM_ENABLED", True)
    monkeypatch.setattr(settings, "SIEM_ENDPOINT", siem.url)
    monkeypatch.setattr(settings, "SIEM_API_KEY", None)
    with world.db() as db:
        export_audit_events(db, sink_from_settings(), cursor=None, batch_size=500, max_batches=20)
    assert siem.events
    forbidden = [
        PASSWORD,
        body,
        "SIEM-DOCUMENT-CONTENT",
        "siem-secret.pdf",
        RECORD_MARKER,
        doctor.session_token or "no-session",
        doctor.csrf_token or "no-csrf",
        '"password"',
        '"token"',
        '"cookie"',
        '"csrf"',
        '"authorization"',
        '"api_key"',
        "hunter2",
        "jwt-secret",
    ]
    assert forbidden_terms_present(siem.events, forbidden) == []
    assert all(set(e) == {*EXPORT_FIELDS, "schema_version"} for e in siem.events)


# --------------------------------------------------------------------------
# Transport behaviour
# --------------------------------------------------------------------------


def test_successful_export_sends_bearer_key_and_batches(world: World, siem, tmp_path: Path):
    marker = f"batch-{uuid.uuid4().hex[:6]}"
    ids = _seed(world, 7, marker)
    sink = HttpJsonAuditSink(siem.url, "secret-api-key", 2.0)
    cursor_file = tmp_path / "cursor.json"
    with world.db() as db:
        start = fetch_batch(db, None, limit=1)  # not used; ensures DB reachable
        assert start
        before = db.get(AuditLog, ids[0])
        assert before is not None
        # Start just before our seeded rows so the batch maths is deterministic.
        cursor = ExportCursor(timestamp=before.timestamp - timedelta(microseconds=1), id=uuid.UUID(int=0))
        report = export_audit_events(
            db,
            sink,
            cursor=cursor,
            batch_size=3,
            max_batches=10,
            on_cursor=lambda c: save_cursor(cursor_file, c),
        )
    assert report.batches == 3 and report.events == 7
    assert [len(item["batch"]) for item in siem.received] == [3, 3, 1]
    assert all(h.get("authorization") == "Bearer secret-api-key" for h in siem.headers)
    assert all(h.get("content-type") == "application/json" for h in siem.headers)
    assert [e["id"] for e in siem.events] == [str(i) for i in ids]
    assert (
        load_cursor(cursor_file)
        == report.cursor
        == ExportCursor(timestamp=report.cursor.timestamp, id=ids[-1])
    )  # type: ignore[union-attr]


def test_max_batches_bounds_a_single_run(world: World, siem):
    marker = f"bound-{uuid.uuid4().hex[:6]}"
    ids = _seed(world, 5, marker)
    with world.db() as db:
        first = db.get(AuditLog, ids[0])
        assert first is not None
        cursor = ExportCursor(timestamp=first.timestamp - timedelta(microseconds=1), id=uuid.UUID(int=0))
        report = export_audit_events(
            db, HttpJsonAuditSink(siem.url, None, 2.0), cursor=cursor, batch_size=2, max_batches=1
        )
    assert report.batches == 1 and report.events == 2 and len(siem.events) == 2
    assert all("authorization" not in h for h in siem.headers)  # no key configured → no header


@pytest.mark.parametrize("behaviour", [400, 401, 403, 500, 503])
def test_4xx_and_5xx_stop_the_run_without_advancing_the_cursor(world: World, siem, behaviour: int):
    marker = f"fail{behaviour}-{uuid.uuid4().hex[:6]}"
    ids = _seed(world, 4, marker)
    siem.plan = [200, behaviour]
    saved: list[ExportCursor] = []
    with world.db() as db:
        first = db.get(AuditLog, ids[0])
        assert first is not None
        cursor = ExportCursor(timestamp=first.timestamp - timedelta(microseconds=1), id=uuid.UUID(int=0))
        with pytest.raises(SiemExportError, match=str(behaviour)):
            export_audit_events(
                db,
                HttpJsonAuditSink(siem.url, None, 2.0),
                cursor=cursor,
                batch_size=2,
                max_batches=5,
                on_cursor=saved.append,
            )
    assert len(siem.events) == 2
    assert saved == [ExportCursor(timestamp=siem_ts(world, ids[1]), id=ids[1])]


def siem_ts(world: World, row_id: uuid.UUID) -> datetime:
    with world.db() as db:
        row = db.get(AuditLog, row_id)
        assert row is not None
        return row.timestamp


def test_timeout_is_a_clean_export_error(world: World, siem):
    marker = f"slow-{uuid.uuid4().hex[:6]}"
    ids = _seed(world, 1, marker)
    siem.plan = ["hang"]
    with world.db() as db:
        first = db.get(AuditLog, ids[0])
        assert first is not None
        cursor = ExportCursor(timestamp=first.timestamp - timedelta(microseconds=1), id=uuid.UUID(int=0))
        with pytest.raises(SiemExportError, match="unreachable"):
            export_audit_events(
                db, HttpJsonAuditSink(siem.url, None, 0.3), cursor=cursor, batch_size=10, max_batches=1
            )


def test_unreachable_endpoint_is_a_clean_export_error():
    sink = HttpJsonAuditSink("http://127.0.0.1:9/nothing-listens-here", None, 0.5)
    with pytest.raises(SiemExportError, match="unreachable"):
        sink.send([{"id": "x"}])


def test_siem_failures_never_affect_the_clinical_application(world: World, siem, monkeypatch):
    """The exporter is out-of-band: with SIEM pointing at a 500/timeout sink, requests still succeed and are audited."""
    siem.plan = [500, "hang", 503]
    monkeypatch.setattr(settings, "SIEM_ENABLED", True)
    monkeypatch.setattr(settings, "SIEM_ENDPOINT", siem.url)
    monkeypatch.setattr(settings, "SIEM_API_KEY", None)
    patient = world.a.patients["a1"]
    started = time.monotonic()
    assert patient.get(f"/api/v1/patients/{patient.patient_id}").status_code == 200
    assert world.a.doctor.get("/api/v1/appointments").status_code == 200
    assert time.monotonic() - started < 1.0  # no synchronous SIEM round-trip inside requests
    assert siem.received == []  # requests never talk to the SIEM at all
    with world.db() as db:
        assert db.scalar(
            select(AuditLog.id).where(AuditLog.actor_user_id == uuid.UUID(patient.user_id)).limit(1)
        )


# --------------------------------------------------------------------------
# At-least-once / dedup semantics
# --------------------------------------------------------------------------


def test_resuming_after_a_crash_re_sends_the_unacknowledged_batch_only(world: World, siem):
    marker = f"resume-{uuid.uuid4().hex[:6]}"
    ids = _seed(world, 4, marker)
    with world.db() as db:
        first = db.get(AuditLog, ids[0])
        assert first is not None
        start = ExportCursor(timestamp=first.timestamp - timedelta(microseconds=1), id=uuid.UUID(int=0))
        sink = HttpJsonAuditSink(siem.url, None, 2.0)
        # Run 1 delivers batch #1 but "crashes" before persisting the cursor for batch #2.
        persisted: list[ExportCursor] = []

        def flaky_persist(c: ExportCursor) -> None:
            if len(persisted) == 1:
                raise KeyboardInterrupt
            persisted.append(c)

        with pytest.raises(KeyboardInterrupt):
            export_audit_events(db, sink, cursor=start, batch_size=2, max_batches=5, on_cursor=flaky_persist)
        # Run 2 resumes from the last persisted cursor.
        report = export_audit_events(db, sink, cursor=persisted[-1], batch_size=2, max_batches=5)
    assert report.events == 2
    delivered = [e["id"] for e in siem.events]
    assert delivered == [str(ids[0]), str(ids[1]), str(ids[2]), str(ids[3]), str(ids[2]), str(ids[3])]
    # Duplicates are identical and dedup-able on `id` (+ request_id/timestamp).
    by_id = {}
    for e in siem.events:
        by_id.setdefault(e["id"], e)
        assert e == by_id[e["id"]]
    assert len(by_id) == 4


def test_cursor_file_round_trip(tmp_path: Path):
    cursor = ExportCursor(timestamp=datetime(2026, 10, 8, 12, 0, tzinfo=UTC), id=uuid.uuid4())
    path = tmp_path / "nested" / "cursor.json"
    assert load_cursor(path) is None
    save_cursor(path, cursor)
    assert load_cursor(path) == cursor
    assert not path.with_suffix(".json.tmp").exists()


def test_export_script_exits_2_when_disabled(monkeypatch):
    from scripts import export_audit_siem

    monkeypatch.setattr(audit_export.settings, "SIEM_ENABLED", False)
    assert export_audit_siem.main([]) == 2
