"""
Phase 8 — centralized audit infrastructure.

Covers the central service (actor/clinic/action/resource/UTC/request-id,
metadata sanitization), the administrator read endpoint (auth, RBAC, tenant
isolation, IDOR, pagination, filters, safe output), privacy guarantees
(no secrets or clinical content persisted), transaction semantics, and one
representative event per migrated module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.audit import ALLOWED_METADATA_KEYS, record_audit_event, sanitize_metadata
from app.main import app
from app.models import AuditAction, AuditLog, AuditResult, User
from app.modules.audit_logs.service import resolve_actor_names
from tests.phase1_world import PASSWORD, RECORD_MARKER, Actor, World

AUDIT = "/api/v1/audit-logs"


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
    assert row.event_metadata == {"patient_id": patient.patient_id}


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
    assert patient.get(AUDIT).status_code == 403
    row = _latest(world, AuditAction.PERMISSION_DENIED, actor_user_id=uuid.UUID(patient.user_id))
    assert row.result == AuditResult.DENIED
    assert row.event_metadata == {"path": AUDIT, "required_roles": ["clinic_admin"]}


# --------------------------------------------------------------------------
# Administrator read endpoint — security
# --------------------------------------------------------------------------


def test_audit_endpoint_requires_authentication():
    assert Actor("anon").get(AUDIT).status_code == 401


@pytest.mark.parametrize("who", ["doctor", "nurse", "staff_admin", "patient"])
def test_audit_endpoint_rejects_non_administrators(world: World, who: str):
    actor = world.a.patients["a1"] if who == "patient" else getattr(world.a, who)
    assert actor.get(AUDIT).status_code == 403


def test_audit_endpoint_is_clinic_scoped_and_ignores_client_supplied_clinic(world: World):
    for tenant, other in ((world.a, world.b), (world.b, world.a)):
        page = tenant.admin.get(f"{AUDIT}?page_size=100")
        assert page.status_code == 200
        rows = page.json()
        assert rows
        with world.db() as db:
            ids = [uuid.UUID(r["id"]) for r in rows]
            clinics = set(db.scalars(select(AuditLog.clinic_id).where(AuditLog.id.in_(ids))))
        assert clinics == {uuid.UUID(tenant.clinic_id)}
        other_users = {
            other.admin.user_id,
            other.doctor.user_id,
            *[p.user_id for p in other.patients.values()],
        }
        assert not {r["actor"]["user_id"] for r in rows} & other_users
        # Any clinic parameter is unknown to the API and has no effect (reading adds only this clinic's own AUDIT_LOG_VIEWED row).
        forged = tenant.admin.get(f"{AUDIT}?clinic_id={other.clinic_id}&page_size=100").json()
        assert {r["id"] for r in rows} <= {r["id"] for r in forged}
        assert all(r["actor"]["user_id"] not in other_users for r in forged)


def test_audit_endpoint_idor_filters_cannot_reach_another_clinic(world: World):
    b_patient = world.b.patients["b1"]
    assert b_patient.get(f"/api/v1/patients/{b_patient.patient_id}").status_code == 200
    assert _rows(
        world, action=AuditAction.PATIENT_VIEWED_OWN_RECORD, actor_user_id=uuid.UUID(b_patient.user_id)
    )
    by_actor = world.a.admin.get(f"{AUDIT}?actor_user_id={b_patient.user_id}")
    by_resource = world.a.admin.get(f"{AUDIT}?resource_id={b_patient.patient_id}")
    assert by_actor.status_code == 200 and by_actor.json() == [] and by_actor.headers["X-Total-Count"] == "0"
    assert by_resource.status_code == 200 and by_resource.json() == []


def test_audit_endpoint_filters_pagination_and_safe_output(world: World):
    admin = world.a.admin
    doctor = world.a.doctor
    patient = world.a.patients["a1"]
    assert doctor.get(f"/api/v1/patients/{patient.patient_id}").status_code == 200

    filtered = admin.get(
        f"{AUDIT}?action=staff_viewed_patient&actor_user_id={doctor.user_id}&resource_type=patient"
        f"&resource_id={patient.patient_id}&page_size=5"
    )
    assert filtered.status_code == 200
    items = filtered.json()
    assert items and all(
        i["action"] == "staff_viewed_patient"
        and i["actor"]["user_id"] == doctor.user_id
        and i["resource_id"] == patient.patient_id
        for i in items
    )
    assert int(filtered.headers["X-Total-Count"]) >= len(items)
    timestamps = [i["timestamp"] for i in items]
    assert timestamps == sorted(timestamps, reverse=True)
    assert set(items[0]) == {
        "id",
        "timestamp",
        "actor",
        "action",
        "result",
        "resource_type",
        "resource_id",
        "ip_address",
        "request_id",
        "metadata",
    }
    assert "user_agent" not in items[0] and "actor_email" not in items[0]

    # Pin pagination to a filter the listing itself does not add rows to.
    page1 = admin.get(f"{AUDIT}?action=login_success&page=1&page_size=2").json()
    page2 = admin.get(f"{AUDIT}?action=login_success&page=2&page_size=2").json()
    assert len(page1) == 2 and not {i["id"] for i in page1} & {i["id"] for i in page2}
    assert admin.get(f"{AUDIT}?page_size=101").status_code == 422
    assert admin.get(f"{AUDIT}?page=0").status_code == 422
    assert admin.get(f"{AUDIT}?action=not_an_action").status_code == 422
    assert admin.get(f"{AUDIT}?resource_type=patient;drop").status_code == 422
    assert admin.get(f"{AUDIT}?actor_user_id=not-a-uuid").status_code == 422
    assert (
        admin.get(f"{AUDIT}?date_from=2031-01-02T00:00:00Z&date_to=2031-01-01T00:00:00Z").status_code == 422
    )

    future = quote((datetime.now(UTC) + timedelta(days=1)).isoformat())
    assert admin.get(f"{AUDIT}?date_from={future}").json() == []
    past = quote((datetime.now(UTC) - timedelta(days=1)).isoformat())
    assert admin.get(f"{AUDIT}?date_from={past}&date_to={future}&page_size=1").json()


def test_reading_the_audit_trail_is_itself_audited_with_identifiers_only(world: World):
    admin = world.a.admin
    doctor = world.a.doctor
    assert admin.get(f"{AUDIT}?action=logout&actor_user_id={doctor.user_id}").status_code == 200
    row = _latest(world, AuditAction.AUDIT_LOG_VIEWED, actor_user_id=uuid.UUID(admin.user_id))
    assert row.resource_type == "audit_log"
    assert row.event_metadata["filters"] == {"action": "logout", "actor_user_id": doctor.user_id}
    assert "count" in row.event_metadata


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
    assert doctor.session_token not in blob and doctor.csrf_token not in blob
    assert "phase8.pdf" not in blob
    for word in ("password", "token", "cookie", "csrf", "authorization"):
        assert f"'{word}'" not in blob and f'"{word}"' not in blob

    sent_row = _latest(world, AuditAction.MESSAGE_SENT, resource_id=uuid.UUID(sent.json()["id"]))
    assert sent_row.event_metadata == {"conversation_id": conversation.json()["id"]}
    doc_row = _latest(world, AuditAction.DOCUMENT_UPLOADED, resource_id=uuid.UUID(uploaded.json()["id"]))
    assert doc_row.event_metadata == {"patient_id": patient.patient_id}


def test_admin_api_output_never_exposes_message_or_document_content(world: World):
    text = world.a.admin.get(f"{AUDIT}?page_size=100").text
    assert (
        "PHASE8-MESSAGE" not in text and "PHASE8-DOCUMENT-CONTENT" not in text and RECORD_MARKER not in text
    )
    assert PASSWORD not in text


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

    documents = doctor.get(f"/api/v1/patients/{patient.patient_id}/documents").json()
    assert documents
    assert doctor.get(f"/api/v1/documents/{documents[0]['id']}/download").status_code == 200
    assert (
        doctor.client.delete(
            f"/api/v1/documents/{documents[0]['id']}", headers={"X-CSRF-Token": doctor.csrf_token or ""}
        ).status_code
        == 204
    )

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
        AuditAction.DOCUMENT_DOWNLOADED: dict(resource_id=uuid.UUID(documents[0]["id"])),
        AuditAction.DOCUMENT_DELETED: dict(resource_id=uuid.UUID(documents[0]["id"])),
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

    listing = admin.get(f"{AUDIT}?resource_id={appointment_id}").json()
    assert {i["action"] for i in listing} == {
        "appointment_created",
        "appointment_updated",
        "appointment_cancelled",
    }
    assert all(
        i["metadata"] == {"patient_id": patient.patient_id}
        or i["metadata"]["patient_id"] == patient.patient_id
        for i in listing
    )


def test_openapi_exposes_only_the_get_listing(world: World):
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths["/api/v1/audit-logs"]) == {"get"}
    assert not any(p.startswith("/api/v1/audit-logs/") for p in paths)


# --------------------------------------------------------------------------
# Actor name resolution (Phase 8.1)
# --------------------------------------------------------------------------


def test_actor_name_is_resolved_for_current_users_and_shaped_consistently(world: World):
    doctor, patient, admin = world.a.doctor, world.a.patients["a1"], world.a.admin
    assert doctor.get(f"/api/v1/patients/{patient.patient_id}").status_code == 200
    rows = admin.get(f"{AUDIT}?action=staff_viewed_patient&actor_user_id={doctor.user_id}&page_size=1").json()
    assert rows and rows[0]["actor"] == {"user_id": doctor.user_id, "email": doctor.email, "name": "Doctor A"}
    # Single-token names are just the stored full_name.
    with world.db() as db:
        db.execute(update(User).where(User.id == uuid.UUID(doctor.user_id)).values(full_name="Mononym"))
        db.commit()
    try:
        rows = admin.get(f"{AUDIT}?actor_user_id={doctor.user_id}&page_size=1").json()
        assert rows[0]["actor"]["name"] == "Mononym"
    finally:
        with world.db() as db:
            db.execute(update(User).where(User.id == uuid.UUID(doctor.user_id)).values(full_name="Doctor A"))
            db.commit()


def test_deleted_actor_keeps_historical_email_and_has_no_name(world: World):
    admin = world.a.admin
    marker = f"gone-{uuid.uuid4().hex[:6]}@phase81.example"
    record_audit_event(
        action=AuditAction.LOGOUT,
        result=AuditResult.SUCCESS,
        clinic_id=world.a.clinic_id,
        actor_user_id=None,  # FK already SET NULL, as after a user deletion
        actor_email=marker,
    )
    rows = admin.get(f"{AUDIT}?action=logout&page_size=100").json()
    gone = [r for r in rows if r["actor"]["email"] == marker]
    assert gone and gone[0]["actor"] == {"user_id": None, "email": marker, "name": None}
    # Anonymous system/security events resolve the same way.
    anon = [
        r
        for r in admin.get(f"{AUDIT}?action=login_failure&page_size=100").json()
        if r["actor"]["user_id"] is None
    ]
    assert all(r["actor"]["name"] is None for r in anon)


def test_actor_names_never_resolve_across_clinics(world: World):
    b_doctor = world.b.doctor
    assert b_doctor.get("/api/v1/appointments").status_code == 200
    with world.db() as db:
        names = resolve_actor_names(
            db, uuid.UUID(world.a.clinic_id), _rows(world, actor_user_id=uuid.UUID(b_doctor.user_id))
        )
    assert names == {}
    # And the API path cannot be coaxed into it: the filter is ANDed with the admin's clinic.
    assert world.a.admin.get(f"{AUDIT}?actor_user_id={b_doctor.user_id}").json() == []
    text = world.a.admin.get(f"{AUDIT}?page_size=100").text
    assert "Doctor B" not in text and b_doctor.email not in text


@pytest.mark.parametrize("who", ["doctor", "nurse", "staff_admin", "patient"])
def test_actor_names_are_only_visible_to_audit_viewers(world: World, who: str):
    actor = world.a.patients["a1"] if who == "patient" else getattr(world.a, who)
    response = actor.get(AUDIT)
    assert response.status_code == 403 and "Doctor A" not in response.text
