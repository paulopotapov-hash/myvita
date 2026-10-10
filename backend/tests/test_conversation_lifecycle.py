"""Care-team messaging lifecycle (docs/clinical-messaging.md): team inbox, nurse triage and
escalation, doctor review and close, generic notifications, audit and isolation."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import AuditLog, Conversation, Message, Notification
from app.modules.notifications.events import TEMPLATES, NotificationEvent
from tests.clinical_support import Tenant, make_tenant

SECRET = "Dor torácica intensa desde ontem"


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, "lifecycle")


def _open(client: TestClient, tenant: Tenant, role: str = "doctor") -> str:
    response = client.post(
        "/api/v1/conversations", headers=tenant.act(client, role), json={"patient_id": tenant.patient_id}
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()["id"]


def _send(client: TestClient, tenant: Tenant, role: str, conversation_id: str, body: str = "Olá"):
    return client.post(
        f"/api/v1/conversations/{conversation_id}/messages", headers=tenant.act(client, role), json={"body": body}
    )


def _status(client: TestClient, tenant: Tenant, role: str, conversation_id: str, value: str):
    return client.post(
        f"/api/v1/conversations/{conversation_id}/status", headers=tenant.act(client, role), json={"status": value}
    )


def _escalate(client: TestClient, tenant: Tenant, role: str, conversation_id: str):
    return client.post(f"/api/v1/conversations/{conversation_id}/escalate", headers=tenant.act(client, role))


def _detail(client: TestClient, tenant: Tenant, role: str, conversation_id: str) -> dict:
    tenant.act(client, role)
    response = client.get(f"/api/v1/conversations/{conversation_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _notifications(client: TestClient, tenant: Tenant, role: str) -> list[Notification]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = (
            db.query(Notification)
            .filter(Notification.user_id == uuid.UUID(tenant.user_ids[role]))
            .order_by(Notification.created_at)
            .all()
        )
        for row in rows:
            db.expunge(row)
        return rows


def _audit(client: TestClient, action: str, conversation_id: str) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.action == action, AuditLog.resource_id == uuid.UUID(conversation_id))
            .order_by(AuditLog.timestamp)
            .all()
        )
        for row in rows:
            db.expunge(row)
        return rows


def _count(client: TestClient, model: Any, **filters: Any) -> int:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(model).filter_by(**filters).count()


def test_patient_replies_reach_the_whole_active_care_team(client: TestClient, tenant: Tenant):
    conversation = _open(client, tenant)
    assert _send(client, tenant, "doctor", conversation).status_code == 201
    assert _detail(client, tenant, "doctor", conversation)["status"] == "waiting_for_patient"

    assert _send(client, tenant, "patient", conversation, SECRET).status_code == 201
    for role in ("doctor", "nurse"):
        (notification,) = _notifications(client, tenant, role)
        assert (notification.title, notification.message) == TEMPLATES[NotificationEvent.MESSAGE_RECEIVED]
        assert str(notification.conversation_target_id) == conversation
        assert SECRET not in notification.message
    # Not the physiotherapist (assigned, but without messaging permission) nor other patients.
    assert _notifications(client, tenant, "physiotherapist") == []
    assert _notifications(client, tenant, "other_patient") == []

    # The team inbox shows the shared unread flag; the first member who opens it clears it.
    tenant.act(client, "nurse")
    (row,) = client.get("/api/v1/conversations").json()
    assert row["status"] == "waiting_for_team"
    assert row["unread_count"] == 1
    assert row["team"]["needs_doctor_review"] is False
    assert client.post(f"/api/v1/conversations/{conversation}/read", headers=tenant.act(client, "nurse")).json() == {
        "updated_count": 1
    }
    tenant.act(client, "doctor")
    assert client.get("/api/v1/conversations").json()[0]["unread_count"] == 0
    # Staff never mark each other's messages: the doctor's message stays unread for the patient.
    messages = _detail(client, tenant, "patient", conversation)["messages"]
    assert [(m["sender_role"], m["read_at"] is None) for m in messages] == [("patient", False), ("doctor", True)]


def test_patients_never_see_triage_metadata(client: TestClient, tenant: Tenant):
    conversation = _open(client, tenant)
    _send(client, tenant, "doctor", conversation)
    assert _escalate(client, tenant, "nurse", conversation).status_code == 200
    tenant.act(client, "patient")
    (row,) = client.get("/api/v1/conversations").json()
    assert row["team"] is None
    assert client.get("/api/v1/conversations?needs_review=true").json() == [row]
    detail = _detail(client, tenant, "patient", conversation)
    assert detail["team"] is None
    assert "needs_doctor_review" not in str(detail)


def test_nurse_escalation_notifies_doctors_and_a_doctor_reply_resolves_it(client: TestClient, tenant: Tenant):
    conversation = _open(client, tenant, role="nurse")
    _send(client, tenant, "nurse", conversation)
    _send(client, tenant, "patient", conversation, SECRET)
    doctor_before = len(_notifications(client, tenant, "doctor"))

    escalated = _escalate(client, tenant, "nurse", conversation)
    assert escalated.status_code == 200, escalated.text
    team = escalated.json()["team"]
    assert team["needs_doctor_review"] is True and team["escalated_by_name"] == "Nurse lifecycle"
    doctor_notifications = _notifications(client, tenant, "doctor")
    assert len(doctor_notifications) == doctor_before + 1
    assert (doctor_notifications[-1].title, doctor_notifications[-1].message) == TEMPLATES[
        NotificationEvent.CONVERSATION_ESCALATED
    ]
    assert all(n.title != "Conversa para revisão médica" for n in _notifications(client, tenant, "patient"))
    (row,) = _audit(client, "conversation_escalated", conversation)
    assert str(row.actor_user_id) == tenant.user_ids["nurse"]

    # Repeating it while pending is not a new escalation.
    assert _escalate(client, tenant, "nurse", conversation).status_code == 200
    assert len(_notifications(client, tenant, "doctor")) == doctor_before + 1
    assert len(_audit(client, "conversation_escalated", conversation)) == 1

    # The doctor finds it in the review queue; the doctor cannot escalate.
    tenant.act(client, "doctor")
    assert [r["id"] for r in client.get("/api/v1/conversations?needs_review=true").json()] == [conversation]
    assert _escalate(client, tenant, "doctor", conversation).status_code == 403

    # A nurse reply does not resolve it; a doctor reply does, audited.
    _send(client, tenant, "nurse", conversation, "Vou pedir ao médico.")
    assert _detail(client, tenant, "nurse", conversation)["team"]["needs_doctor_review"] is True
    _send(client, tenant, "doctor", conversation, "Revi o caso.")
    assert _detail(client, tenant, "nurse", conversation)["team"]["needs_doctor_review"] is False
    (cleared,) = _audit(client, "conversation_escalation_cleared", conversation)
    assert str(cleared.actor_user_id) == tenant.user_ids["doctor"]
    assert client.get("/api/v1/conversations?needs_review=true", headers=tenant.act(client, "doctor")).json() == []


def test_nurses_triage_but_only_doctors_close_and_reopen(client: TestClient, tenant: Tenant):
    conversation = _open(client, tenant)
    _send(client, tenant, "doctor", conversation)

    triaged = _status(client, tenant, "nurse", conversation, "waiting_for_team")
    assert triaged.status_code == 200 and triaged.json()["status"] == "waiting_for_team"
    (row,) = _audit(client, "conversation_status_changed", conversation)
    assert (row.event_metadata["from"], row.event_metadata["to"]) == ("waiting_for_patient", "waiting_for_team")
    # Same status: nothing to record.
    assert _status(client, tenant, "nurse", conversation, "waiting_for_team").status_code == 200
    assert len(_audit(client, "conversation_status_changed", conversation)) == 1

    assert _status(client, tenant, "nurse", conversation, "closed").status_code == 403
    assert _detail(client, tenant, "doctor", conversation)["status"] == "waiting_for_team"
    assert _escalate(client, tenant, "nurse", conversation).status_code == 200

    closed = _status(client, tenant, "doctor", conversation, "closed")
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["status"] == "closed" and body["closed_at"]
    assert body["team"]["closed_by_name"] == "Doctor lifecycle"
    # Closing resolves the review request and tells the patient generically.
    assert body["team"]["needs_doctor_review"] is False
    assert _notifications(client, tenant, "patient")[-1].title == TEMPLATES[NotificationEvent.CONVERSATION_CLOSED][0]

    # Closed is read-only for everyone, enforced by the backend.
    for role in ("patient", "nurse", "doctor"):
        refused = _send(client, tenant, role, conversation, "Mais uma coisa")
        assert refused.status_code == 403, role
    assert _count(client, Message, conversation_id=uuid.UUID(conversation)) == 1
    assert _detail(client, tenant, "patient", conversation)["can_reply"] is False
    assert _escalate(client, tenant, "nurse", conversation).status_code == 409
    # Only a doctor reopens.
    assert _status(client, tenant, "nurse", conversation, "open").status_code == 403
    reopened = _status(client, tenant, "doctor", conversation, "open")
    assert reopened.json()["status"] == "open" and reopened.json()["closed_at"] is None
    assert _send(client, tenant, "patient", conversation, "Obrigado").status_code == 201


def test_starting_a_conversation_again_reopens_a_closed_thread(client: TestClient, tenant: Tenant):
    conversation = _open(client, tenant, role="nurse")
    _status(client, tenant, "doctor", conversation, "closed")
    again = client.post(
        "/api/v1/conversations", headers=tenant.act(client, "nurse"), json={"patient_id": tenant.patient_id}
    )
    assert again.status_code == 200 and again.json()["id"] == conversation
    assert again.json()["status"] == "open"
    rows = _audit(client, "conversation_status_changed", conversation)
    assert rows[-1].event_metadata == {
        "from": "closed",
        "to": "open",
        "operation": "start",
        "actor_staff_role": "nurse",
    }


@pytest.mark.parametrize("role", ["patient", "other_patient", "physiotherapist", "admin", "clinic_admin"])
def test_lifecycle_actions_are_staff_only(client: TestClient, tenant: Tenant, role: str):
    conversation = _open(client, tenant)
    _send(client, tenant, "doctor", conversation)
    assert _status(client, tenant, role, conversation, "closed").status_code == 404
    assert _escalate(client, tenant, role, conversation).status_code == 404
    assert _detail(client, tenant, "doctor", conversation)["status"] == "waiting_for_patient"
    assert _audit(client, "permission_denied", conversation)


def test_unassigned_and_other_clinic_staff_cannot_change_the_lifecycle(client: TestClient, tenant: Tenant):
    conversation = _open(client, tenant)
    client.delete(
        f"/api/v1/patients/{tenant.patient_id}/care-team/{tenant.staff_ids['nurse']}",
        headers=tenant.act(client, "clinic_admin"),
    )
    assert _status(client, tenant, "nurse", conversation, "waiting_for_team").status_code == 404
    assert _escalate(client, tenant, "nurse", conversation).status_code == 404
    other = make_tenant(client, "lifecycle-b")
    for role in ("doctor", "nurse"):
        assert _status(client, other, role, conversation, "closed").status_code == 404
        assert _escalate(client, other, role, conversation).status_code == 404
    with client.session_factory() as db:  # type: ignore[attr-defined]
        row = db.get(Conversation, uuid.UUID(conversation))
        assert row.status.value == "open" and row.needs_doctor_review is False


def test_status_filter_and_invalid_values(client: TestClient, tenant: Tenant):
    first = _open(client, tenant)
    _send(client, tenant, "doctor", first)
    second = _open(client, tenant, role="nurse")
    tenant.act(client, "doctor")
    assert [r["id"] for r in client.get("/api/v1/conversations?status=open").json()] == [second]
    assert [r["id"] for r in client.get("/api/v1/conversations?status=waiting_for_patient").json()] == [first]
    assert client.get("/api/v1/conversations?status=archived").status_code == 422
    assert _status(client, tenant, "doctor", first, "archived").status_code == 422
    assert client.post(
        f"/api/v1/conversations/{first}/status", headers=tenant.act(client, "doctor"), json={"status": "closed", "x": 1}
    ).status_code == 422
