"""P2.6 — domain events produce consistent, privacy-preserving, idempotent notifications."""

import inspect
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import Notification
from app.modules.notifications.events import (
    TEMPLATES,
    NotificationEvent,
    NotificationTarget,
    TargetType,
    notify,
)
from tests.clinical_support import Tenant, book, make_tenant, slot


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, "events")


def _rows(client: TestClient, user_id: str | None = None) -> list[Notification]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        query = db.query(Notification)
        if user_id is not None:
            query = query.filter(Notification.user_id == uuid.UUID(user_id))
        rows = query.order_by(Notification.created_at).all()
        for row in rows:
            db.expunge(row)
        return rows


# --- privacy by construction ------------------------------------------------------


def test_every_event_has_fixed_generic_text():
    assert set(TEMPLATES) == set(NotificationEvent)
    for event, (title, message) in TEMPLATES.items():
        assert title and message, event
        # Fixed strings: no placeholders that could later carry clinical data.
        assert not re.search(r"[{}%]", title + message), event
        assert len(title) <= 200


def test_notify_accepts_no_free_text():
    parameters = set(inspect.signature(notify).parameters)
    assert parameters == {
        "db",
        "event",
        "clinic_id",
        "recipient_user_id",
        "target",
        "dedupe_key",
        "coalesce_unread",
    }


# --- recipient validation, idempotency --------------------------------------------


def test_recipient_from_another_clinic_never_gets_the_notification(client: TestClient, tenant: Tenant):
    other = make_tenant(client, "events-b")
    with client.session_factory() as db:  # type: ignore[attr-defined]
        notify(
            db,
            NotificationEvent.DOCUMENT_ADDED,
            clinic_id=tenant.clinic_id,
            recipient_user_id=other.user_ids["patient"],
        )
        notify(db, NotificationEvent.DOCUMENT_ADDED, clinic_id=tenant.clinic_id, recipient_user_id=uuid.uuid4())
        db.commit()
    assert _rows(client, other.user_ids["patient"]) == []
    assert _rows(client) == []


def test_repeated_event_with_the_same_key_creates_one_notification(client: TestClient, tenant: Tenant):
    with client.session_factory() as db:  # type: ignore[attr-defined]
        for _ in range(3):
            notify(
                db,
                NotificationEvent.APPOINTMENT_REQUEST_ACCEPTED,
                clinic_id=tenant.clinic_id,
                recipient_user_id=tenant.user_ids["patient"],
                dedupe_key="request-1",
            )
        db.commit()
        # A retry in a later transaction is a no-op too.
        notify(
            db,
            NotificationEvent.APPOINTMENT_REQUEST_ACCEPTED,
            clinic_id=tenant.clinic_id,
            recipient_user_id=tenant.user_ids["patient"],
            dedupe_key="request-1",
        )
        db.commit()
    assert len(_rows(client, tenant.user_ids["patient"])) == 1


def test_a_rolled_back_operation_leaves_no_notification(client: TestClient, tenant: Tenant):
    with client.session_factory() as db:  # type: ignore[attr-defined]
        notify(
            db,
            NotificationEvent.APPOINTMENT_CREATED,
            clinic_id=tenant.clinic_id,
            recipient_user_id=tenant.user_ids["patient"],
        )
        db.rollback()
    assert _rows(client) == []


# --- workflows ----------------------------------------------------------------------


def test_failed_business_operations_produce_no_notification(client: TestClient, tenant: Tenant):
    # Unauthorized release attempt and an invalid result.
    created = client.post(
        f"/api/v1/patients/{tenant.patient_id}/results",
        headers=tenant.act(client, "doctor"),
        json={"category": "imaging", "title": "RX", "summary": "s", "result_date": "2026-01-01"},
    )
    assert created.status_code == 201
    denied = client.post(f"/api/v1/results/{created.json()['id']}/release", headers=tenant.act(client, "physiotherapist"))
    assert denied.status_code == 403
    invalid = client.post(
        f"/api/v1/patients/{tenant.patient_id}/results",
        headers=tenant.act(client, "doctor"),
        json={"category": "imaging", "title": "RX", "summary": "s", "result_date": "2026-01-01", "release": True, "document_id": str(uuid.uuid4())},
    )
    assert invalid.status_code == 422
    # Overlapping appointment: the conflict rolls back the notifications as well.
    book(client, tenant, role="clinic_admin")
    before = len(_rows(client))
    conflict = client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "clinic_admin"),
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": slot(), "duration_minutes": 30},
    )
    assert conflict.status_code == 409
    assert len(_rows(client)) == before
    assert all(row.target_type is None for row in _rows(client))


def test_appointment_events_notify_patient_and_professional(client: TestClient, tenant: Tenant):
    appointment = book(client, tenant, role="clinic_admin")
    patient_rows = _rows(client, tenant.user_ids["patient"])
    doctor_rows = _rows(client, tenant.user_ids["doctor"])
    assert [(r.title, r.message) for r in patient_rows] == [TEMPLATES[NotificationEvent.APPOINTMENT_CREATED]]
    assert [(r.title, r.message) for r in doctor_rows] == [TEMPLATES[NotificationEvent.APPOINTMENT_ASSIGNED]]
    assert all(str(r.clinic_id) == tenant.clinic_id for r in patient_rows + doctor_rows)
    # The free-text reason never travels in a notification.
    assert all("reason" not in r.message for r in patient_rows)

    confirmed = client.patch(
        f"/api/v1/appointments/{appointment['id']}", headers=tenant.act(client, "clinic_admin"), json={"status": "confirmed"}
    )
    assert confirmed.status_code == 200, confirmed.text
    cancelled = client.post(f"/api/v1/appointments/{appointment['id']}/cancel", headers=tenant.act(client, "clinic_admin"))
    assert cancelled.status_code == 200, cancelled.text
    assert [r.title for r in _rows(client, tenant.user_ids["patient"])] == [
        "Consulta criada",
        "Consulta confirmada",
        "Consulta cancelada",
    ]
    assert [r.message for r in _rows(client, tenant.user_ids["doctor"])][-1] == TEMPLATES[
        NotificationEvent.APPOINTMENT_CANCELLED_FOR_STAFF
    ][1]
    # Nobody outside the appointment is notified.
    assert _rows(client, tenant.user_ids["other_patient"]) == []
    assert _rows(client, tenant.user_ids["nurse"]) == []


def test_appointment_request_events_reach_schedulers_then_the_patient(client: TestClient, tenant: Tenant):
    preferred = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    created = client.post(
        "/api/v1/appointment-requests",
        headers=tenant.act(client, "patient"),
        json={"preferred_start": preferred, "reason": "Dor torácica intensa"},
    )
    assert created.status_code == 201, created.text
    # Scheduling roles only: the clinic admin and the administrative staff member.
    received = TEMPLATES[NotificationEvent.APPOINTMENT_REQUEST_RECEIVED]
    for role in ("clinic_admin", "admin"):
        assert [(r.title, r.message) for r in _rows(client, tenant.user_ids[role])] == [received], role
    for role in ("doctor", "nurse", "patient", "other_patient"):
        assert _rows(client, tenant.user_ids[role]) == [], role
    assert all("torácica" not in f"{r.title} {r.message}" for r in _rows(client))

    accepted = client.post(
        f"/api/v1/appointment-requests/{created.json()['id']}/accept",
        headers=tenant.act(client, "clinic_admin"),
        json={"staff_id": tenant.staff_ids["doctor"], "scheduled_at": slot(days=6)},
    )
    assert accepted.status_code == 200, accepted.text
    again = client.post(
        f"/api/v1/appointment-requests/{created.json()['id']}/accept",
        headers=tenant.act(client, "clinic_admin"),
        json={"staff_id": tenant.staff_ids["doctor"], "scheduled_at": slot(days=7)},
    )
    assert again.status_code == 409
    titles = [r.title for r in _rows(client, tenant.user_ids["patient"])]
    assert titles.count("Pedido de consulta aceite") == 1
    assert "Consulta criada" in titles


def test_message_notifications_link_to_the_conversation_and_do_not_pile_up(client: TestClient, tenant: Tenant):
    opened = client.post(
        "/api/v1/conversations", headers=tenant.act(client, "doctor"), json={"patient_id": tenant.patient_id}
    )
    assert opened.status_code in {200, 201}, opened.text
    conversation_id = opened.json()["id"]
    url = f"/api/v1/conversations/{conversation_id}/messages"
    for body in ("Primeira mensagem confidencial", "Segunda mensagem confidencial"):
        assert client.post(url, headers=tenant.act(client, "doctor"), json={"body": body}).status_code == 201

    rows = _rows(client, tenant.user_ids["patient"])
    assert len(rows) == 1  # one unread notification for the burst
    assert rows[0].target_type == "conversation" and str(rows[0].conversation_target_id) == conversation_id
    assert "confidencial" not in f"{rows[0].title} {rows[0].message}"

    # Once read, the next message notifies again.
    tenant.act(client, "patient")
    notification_id = client.get("/api/v1/notifications").json()[0]["id"]
    assert client.post(f"/api/v1/notifications/{notification_id}/read", headers=tenant.act(client, "patient")).status_code == 200
    assert client.get("/api/v1/notifications/unread-count").json() == {"count": 0}
    assert client.post(url, headers=tenant.act(client, "doctor"), json={"body": "Terceira"}).status_code == 201
    assert len(_rows(client, tenant.user_ids["patient"])) == 2
    tenant.act(client, "patient")
    assert client.get("/api/v1/notifications/unread-count").json() == {"count": 1}


def test_deep_links_never_grant_access(client: TestClient, tenant: Tenant):
    """Opening a notification's target re-checks current permissions."""
    opened = client.post("/api/v1/conversations", headers=tenant.act(client, "doctor"), json={"patient_id": tenant.patient_id})
    conversation_id = opened.json()["id"]
    client.post(
        f"/api/v1/conversations/{conversation_id}/messages", headers=tenant.act(client, "patient"), json={"body": "Olá"}
    )
    (doctor_notification,) = _rows(client, tenant.user_ids["doctor"])
    assert str(doctor_notification.conversation_target_id) == conversation_id

    # The care assignment ends: the notification stays, the conversation is no longer readable.
    ended = client.delete(
        f"/api/v1/patients/{tenant.patient_id}/care-team/{tenant.staff_ids['doctor']}",
        headers=tenant.act(client, "clinic_admin"),
    )
    assert ended.status_code == 200
    tenant.act(client, "doctor")
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code in {403, 404}
    assert len(client.get("/api/v1/notifications").json()) == 1

    # A released result's notification belongs to its patient only.
    nurse_headers = tenant.act(client, "nurse")
    result = client.post(
        f"/api/v1/patients/{tenant.patient_id}/results",
        headers=nurse_headers,
        json={"category": "other", "title": "T", "summary": "S", "result_date": "2026-01-01", "release": True},
    ).json()
    (result_notification,) = [r for r in _rows(client, tenant.user_ids["patient"]) if r.target_type == "result"]
    assert str(result_notification.result_target_id) == result["id"]
    tenant.act(client, "other_patient")
    assert client.get(f"/api/v1/results/{result['id']}").status_code == 404
    assert client.get("/api/v1/notifications").json() == []
    assert client.post(f"/api/v1/notifications/{result_notification.id}/read", headers=tenant.act(client, "other_patient")).status_code == 404


def test_document_upload_notifies_the_patient_once_with_a_deep_link(client: TestClient, tenant: Tenant):
    upload = client.post(
        f"/api/v1/patients/{tenant.patient_id}/documents",
        headers=tenant.act(client, "doctor"),
        data={"title": "Biópsia hepática"},
        files={"file": ("biopsia.pdf", b"%PDF-1.7\nx", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    (row,) = _rows(client, tenant.user_ids["patient"])
    assert (row.title, row.message) == TEMPLATES[NotificationEvent.DOCUMENT_ADDED]
    assert row.target_type == "document" and str(row.target_id) == upload.json()["id"]
    assert "Biópsia" not in row.message and "biopsia" not in row.message


def test_target_columns_match_their_type():
    target_id = uuid.uuid4()
    assert NotificationTarget(TargetType.RESULT, target_id).columns() == {
        "target_id": None,
        "conversation_target_id": None,
        "result_target_id": target_id,
        "record_target_id": None,
        "appointment_target_id": None,
    }
    assert NotificationTarget(TargetType.MEDICAL_RECORD, target_id).columns() == {
        "target_id": None,
        "conversation_target_id": None,
        "result_target_id": None,
        "record_target_id": target_id,
        "appointment_target_id": None,
    }
    assert NotificationTarget(TargetType.DOCUMENT, target_id).columns()["target_id"] == target_id
    assert NotificationTarget(TargetType.CONVERSATION, target_id).columns()["conversation_target_id"] == target_id
    # Step 7: a reminder links to its appointment.
    assert NotificationTarget(TargetType.APPOINTMENT, target_id).columns()["appointment_target_id"] == target_id
