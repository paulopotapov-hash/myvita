"""
Phase 8 — centralized audit infrastructure.

Covers the central service (actor/clinic/action/resource/UTC/request-id,
metadata sanitization), privacy guarantees (no secrets or clinical content
persisted), transaction semantics, and one representative event per migrated
module. There is deliberately no tenant-facing audit read API (Parent A's rule,
restored at integration): the trail leaves the database only through the SIEM
export.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.audit import ALLOWED_METADATA_KEYS, record_audit_event, sanitize_metadata
from app.main import app
from app.models import AuditAction, AuditLog, AuditResult
from tests.phase1_world import PASSWORD, RECORD_MARKER, Actor, World

AUDIT = "/api/v1/audit-logs"
ADMIN_ONLY = "/api/v1/staff"


def _rows(world: World, **filters) -> list[AuditLog]:
    with world.db() as db:
        query = select(AuditLog)
        for column, value in filters.items():
            query = query.where(getattr(AuditLog, column) == value)
        return list(db.scalars(query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())))


def _latest(world: World, action: AuditAction, **filters) -> AuditLog:
    rows = _rows(world, action=action, **filters)
    assert rows, f"no audit row for {action}"
    return rows[0]


# --------------------------------------------------------------------------
# Central service
# --------------------------------------------------------------------------


def test_central_service_records_actor_clinic_action_resource_and_utc_timestamp(world: World):
    doctor = world.a.doctor
    patient = world.a.patients["a1"]
    before = datetime.now(UTC) - timedelta(seconds=5)
    response = doctor.get(
        f"/api/v1/patients/{patient.patient_id}", headers={"X-Request-ID": "phase8-req-0001"}
    )
    assert response.status_code == 200

    row = _latest(world, AuditAction.STAFF_VIEWED_PATIENT, resource_id=uuid.UUID(patient.patient_id))
    assert str(row.actor_user_id) == doctor.user_id
    assert row.actor_email == doctor.email
    assert str(row.clinic_id) == world.a.clinic_id
    assert row.resource_type == "patient"
    assert row.result == AuditResult.SUCCESS
    assert row.ip_address and row.request_id == "phase8-req-0001"
    assert row.timestamp.tzinfo is not None and row.timestamp.utcoffset() == timedelta(0)
    assert row.timestamp >= before


def test_service_layer_events_pick_up_the_request_id_from_context(world: World):
    actor = Actor("ctx", world.a.nurse.email)
    assert (
        actor.client.post(
            "/api/v1/auth/login",
            json={"email": actor.email, "password": "definitely-wrong-1!"},
            headers={"X-Request-ID": "phase8-login-fail-01"},
        ).status_code
        == 401
    )
    row = _latest(world, AuditAction.LOGIN_FAILURE, actor_email=world.a.nurse.email)
    assert row.request_id == "phase8-login-fail-01"
    assert row.result == AuditResult.FAILURE


def test_metadata_sanitizer_allowlists_keys_and_strips_sensitive_values():
    dirty = {
        "count": 3,
        "patient_id": uuid.UUID(int=1),
        "password": "hunter2",
        "token": "eyJ...",
        "Authorization": "Bearer x",
        "cookie": "myvita_session=abc",
        "csrf": "zzz",
        "message_body": "Patient says...",
        "document_content": b"%PDF",
        "medical_record": "diagnosis",
        "unknown_key": "whatever",
        "required_roles": ["clinic_admin", "staff"],
        "filters": {"action": "login_success", "secret": "nope"},
        "path": "x" * 500,
    }
    clean = sanitize_metadata(dirty)
    assert clean is not None
    assert set(clean) == {"count", "patient_id", "required_roles", "filters", "path"}
    assert clean["patient_id"] == str(uuid.UUID(int=1))
    assert clean["filters"] == {"action": "login_success"}
    assert len(clean["path"]) == 200
    assert sanitize_metadata({}) is None and sanitize_metadata(None) is None
    assert sanitize_metadata({"password": "x"}) is None
    forbidden = ("password", "token", "cookie", "csrf", "secret", "authorization", "body", "content")
    assert not any(any(word in key for word in forbidden) for key in ALLOWED_METADATA_KEYS)


def test_record_audit_event_never_persists_disallowed_metadata(world: World):
    marker = f"leak-{uuid.uuid4().hex}"
    record_audit_event(
        action=AuditAction.LOGOUT,
        result=AuditResult.SUCCESS,
        actor_email=f"{marker}@phase8.example",
        metadata={"password": marker, "token": marker, "message": marker, "count": 1},
    )
    row = _latest(world, AuditAction.LOGOUT, actor_email=f"{marker}@phase8.example")
    assert row.event_metadata == {"count": 1}
    assert marker not in str(row.event_metadata)


# --------------------------------------------------------------------------
# Transaction semantics
# --------------------------------------------------------------------------


def test_successful_operation_leaves_an_audit_row(world: World):
    doctor = world.a.doctor
    patient = world.a.patients["a2"]
    created = doctor.post(
        f"/api/v1/patients/{patient.patient_id}/medical-records",
        json={"title": "Phase 8", "content": f"{RECORD_MARKER} phase8"},
    )
    assert created.status_code == 201
    row = _latest(world, AuditAction.MEDICAL_RECORD_CREATED, resource_id=uuid.UUID(created.json()["id"]))
    # `actor_staff_role` is attached centrally for staff actors (app/core/audit.py).
    assert row.event_metadata == {"patient_id": patient.patient_id, "actor_staff_role": "doctor"}


def test_rolled_back_operation_does_not_claim_success(world: World, monkeypatch):
    doctor = world.a.doctor
    patient = world.a.patients["a2"]
    before = len(_rows(world, action=AuditAction.APPOINTMENT_CREATED))

    def explode(*_args, **_kwargs):
        raise RuntimeError("synthetic failure inside the business transaction")

    monkeypatch.setattr("app.modules.appointments.service._add_staff_notification", explode)
    crashing = Actor("crash", doctor.email, raise_server_exceptions=False)
    assert crashing.login().status_code == 200
    response = crashing.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient.patient_id,
            "staff_id": doctor.staff_id,
            "scheduled_at": "2041-01-01T10:00:00+00:00",
        },
    )
    assert response.status_code == 500
    assert len(_rows(world, action=AuditAction.APPOINTMENT_CREATED)) == before


def test_denied_and_failed_events_are_recorded_even_though_the_request_fails(world: World):
    patient = world.a.patients["a1"]
    assert patient.post(ADMIN_ONLY, json={}).status_code == 403
    row = _latest(world, AuditAction.PERMISSION_DENIED, actor_user_id=uuid.UUID(patient.user_id))
    assert row.result == AuditResult.DENIED
    assert row.event_metadata == {"path": ADMIN_ONLY, "required_roles": ["clinic_admin"]}


# --------------------------------------------------------------------------
# No tenant-facing audit read API (Parent A's rule; UAT-18)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["admin", "doctor", "nurse", "staff_admin", "patient"])
def test_no_role_can_read_the_audit_trail_over_the_api(world: World, who: str):
    actor = world.a.patients["a1"] if who == "patient" else getattr(world.a, who)
    assert actor.get(AUDIT).status_code == 404
    assert actor.get(f"{AUDIT}?page_size=100").status_code == 404


# --------------------------------------------------------------------------
# Privacy: nothing sensitive is ever persisted
# --------------------------------------------------------------------------


def test_no_secrets_or_clinical_content_in_any_audit_row(world: World):
    doctor = world.a.doctor
    patient = world.a.patients["a1"]
    body = f"PHASE8-MESSAGE-{uuid.uuid4().hex}"
    conversation = doctor.post("/api/v1/conversations", json={"patient_id": patient.patient_id})
    assert conversation.status_code in (200, 201), conversation.text
    sent = doctor.post(f"/api/v1/conversations/{conversation.json()['id']}/messages", json={"body": body})
    assert sent.status_code == 201
    pdf = b"%PDF-1.4 PHASE8-DOCUMENT-CONTENT"
    uploaded = doctor.client.post(
        f"/api/v1/patients/{patient.patient_id}/documents",
        data={"title": "PHASE8-DOCUMENT-TITLE"},
        files={"file": ("phase8.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": doctor.csrf_token or ""},
    )
    assert uploaded.status_code == 201, uploaded.text

    with world.db() as db:
        blob = " ".join(
            f"{r.actor_email} {r.resource_type} {r.event_metadata} {r.user_agent} {r.ip_address} {r.request_id}"
            for r in db.scalars(select(AuditLog))
        )
    assert PASSWORD not in blob
    assert body not in blob and "PHASE8-DOCUMENT-CONTENT" not in blob and RECORD_MARKER not in blob
    assert "PHASE8-DOCUMENT-TITLE" not in blob
    assert doctor.session_token not in blob and doctor.csrf_token not in blob
    assert "phase8.pdf" not in blob
    for word in ("password", "token", "cookie", "csrf", "authorization"):
        assert f"'{word}'" not in blob and f'"{word}"' not in blob

    sent_row = _latest(world, AuditAction.MESSAGE_SENT, resource_id=uuid.UUID(sent.json()["id"]))
    assert sent_row.event_metadata == {"conversation_id": conversation.json()["id"], "actor_staff_role": "doctor"}
    doc_row = _latest(world, AuditAction.DOCUMENT_UPLOADED, resource_id=uuid.UUID(uploaded.json()["id"]))
    assert doc_row.event_metadata == {"patient_id": patient.patient_id, "actor_staff_role": "doctor"}


# --------------------------------------------------------------------------
# Representative events per migrated module
# --------------------------------------------------------------------------


def test_representative_events_for_every_migrated_module(world: World):
    a = world.a
    doctor, patient, admin = a.doctor, a.patients["a1"], a.admin
    # Logout bumps token_epoch for the whole account, so use the nurse for the login/logout pair.
    fresh = Actor("fresh", a.nurse.email)
    assert fresh.login().status_code == 200
    assert fresh.post("/api/v1/auth/logout").status_code == 204
    assert a.nurse.login().status_code == 200

    appointment = doctor.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient.patient_id,
            "staff_id": doctor.staff_id,
            "scheduled_at": "2042-02-02T10:00:00+00:00",
        },
    )
    assert appointment.status_code == 201
    appointment_id = appointment.json()["id"]
    assert (
        doctor.patch(
            f"/api/v1/appointments/{appointment_id}", json={"scheduled_at": "2042-02-02T11:00:00+00:00"}
        ).status_code
        == 200
    )
    assert doctor.post(f"/api/v1/appointments/{appointment_id}/cancel").status_code == 200

    notification_id = patient.get("/api/v1/notifications").json()[0]["id"]
    assert patient.post(f"/api/v1/notifications/{notification_id}/read").status_code == 200
    assert patient.post("/api/v1/notifications/read-all").status_code == 200

    conversation = doctor.post("/api/v1/conversations", json={"patient_id": patient.patient_id}).json()["id"]
    assert doctor.get(f"/api/v1/conversations/{conversation}").status_code == 200
    assert patient.post(f"/api/v1/conversations/{conversation}/read").status_code == 200

    # Deterministic: this test seeds its own document instead of relying on one
    # uploaded by an earlier test in the module-scoped world.
    uploaded = doctor.client.post(
        f"/api/v1/patients/{patient.patient_id}/documents",
        data={"title": "Representative events"},
        files={"file": ("representative.pdf", b"%PDF-1.4 representative", "application/pdf")},
        headers={"X-CSRF-Token": doctor.csrf_token or ""},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    listed = doctor.get(f"/api/v1/patients/{patient.patient_id}/documents")
    assert document_id in {item["id"] for item in listed.json()}
    assert doctor.get(f"/api/v1/documents/{document_id}/download").status_code == 200
    # Documents are append-only (D3): there is no delete event to produce.

    assert doctor.get(f"/api/v1/medical-records/{patient.res['record']}").status_code == 200
    assert patient.get(f"/api/v1/consents/{patient.res['consent']}").status_code == 200
    assert doctor.get(f"/api/v1/medications/{patient.res['medication']}").status_code == 200

    expectations = {
        AuditAction.LOGIN_SUCCESS: dict(actor_user_id=uuid.UUID(a.nurse.user_id)),
        AuditAction.LOGOUT: dict(actor_user_id=uuid.UUID(a.nurse.user_id)),
        AuditAction.APPOINTMENT_CREATED: dict(resource_id=uuid.UUID(appointment_id)),
        AuditAction.APPOINTMENT_UPDATED: dict(resource_id=uuid.UUID(appointment_id)),
        AuditAction.APPOINTMENT_CANCELLED: dict(resource_id=uuid.UUID(appointment_id)),
        AuditAction.NOTIFICATION_READ: dict(actor_user_id=uuid.UUID(patient.user_id)),
        AuditAction.CONVERSATION_VIEWED: dict(resource_id=uuid.UUID(conversation)),
        AuditAction.MESSAGE_READ: dict(resource_id=uuid.UUID(conversation)),
        AuditAction.DOCUMENT_UPLOADED: dict(resource_id=uuid.UUID(document_id)),
        AuditAction.DOCUMENT_VIEWED: dict(resource_id=uuid.UUID(patient.patient_id)),
        AuditAction.DOCUMENT_DOWNLOADED: dict(resource_id=uuid.UUID(document_id)),
        AuditAction.MEDICAL_RECORD_VIEWED: dict(resource_id=uuid.UUID(patient.res["record"])),
        AuditAction.CONSENT_VIEWED: dict(resource_id=uuid.UUID(patient.res["consent"])),
        AuditAction.MEDICATION_VIEWED: dict(resource_id=uuid.UUID(patient.res["medication"])),
    }
    for action, filters in expectations.items():
        row = _latest(world, action, **filters)
        assert str(row.clinic_id) == a.clinic_id, action
        assert row.request_id, action
        assert row.result == AuditResult.SUCCESS, action

    read_all = [
        r
        for r in _rows(world, action=AuditAction.NOTIFICATION_READ)
        if r.event_metadata and r.event_metadata.get("operation") == "read_all"
    ]
    assert read_all and read_all[0].resource_id is None

    appointment_rows = _rows(world, resource_id=uuid.UUID(appointment_id))
    assert {r.action for r in appointment_rows} == {
        AuditAction.APPOINTMENT_CREATED,
        AuditAction.APPOINTMENT_UPDATED,
        AuditAction.APPOINTMENT_CANCELLED,
    }
    assert all(r.event_metadata and r.event_metadata["patient_id"] == patient.patient_id for r in appointment_rows)
    assert admin.get(f"{AUDIT}?resource_id={appointment_id}").status_code == 404


def test_openapi_exposes_no_audit_read_api(world: World):
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if "audit" in p.lower()]
