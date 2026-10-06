import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from app.models import ClinicalMessage, Notification
from tests.clinical_support import Tenant, audit, make_tenant


@pytest.fixture()
def tenants(client: TestClient) -> tuple[Tenant, Tenant]:
    return make_tenant(client, "messages-a"), make_tenant(client, "messages-b")


def start(client: TestClient, tenant: Tenant, role: str = "doctor", patient_id: str | None = None):
    return client.post(
        f"/api/v1/messages/patients/{patient_id or tenant.patient_id}/conversations",
        headers=tenant.act(client, role),
        json={"subject": "Plano de recuperação", "body": "Vamos rever a evolução na próxima semana."},
    )


def test_clinical_team_initiates_patient_replies_and_team_notifications(client: TestClient, tenants):
    a, b = tenants
    created = start(client, a, "doctor")
    assert created.status_code == 201, created.text
    conversation = created.json()
    conversation_id = conversation["id"]
    assert conversation["status"] == "waiting_for_patient"
    assert conversation["messages"][0]["sender_name"] == "Doctor messages-a"
    assert conversation["messages"][0]["sender_role"] == "doctor"
    assert conversation["messages"][0]["body"] == "Vamos rever a evolução na próxima semana."

    with client.session_factory() as db:  # type: ignore[attr-defined]
        patient_notices = db.query(Notification).filter(
            Notification.user_id == uuid.UUID(a.user_ids["patient"]),
            Notification.conversation_target_id == conversation_id,
        ).all()
        assert len(patient_notices) == 1
        assert patient_notices[0].target_type == "conversation"
        assert "evolução" not in patient_notices[0].message

    # Staff can create, but patients cannot start a new conversation.
    assert start(client, a, "nurse").status_code == 201
    assert start(client, a, "patient").status_code == 404
    assert start(client, a, "physiotherapist").status_code == 403
    assert start(client, a, "admin").status_code == 403
    assert start(client, a, "doctor", a.other_patient_id).status_code == 403
    assert start(client, b, "doctor", a.patient_id).status_code == 404

    patient_reply = client.post(
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        headers=a.act(client, "patient"),
        json={"body": "Já estou a sentir melhorias."},
    )
    assert patient_reply.status_code == 200, patient_reply.text
    thread = patient_reply.json()
    assert thread["status"] == "waiting_for_team"
    assert thread["messages"][-1]["sender_name"] == "Patient 0 messages-a"
    assert thread["messages"][-1]["sender_role"] == "patient"

    with client.session_factory() as db:  # type: ignore[attr-defined]
        notice_users = {
            str(row.user_id)
            for row in db.query(Notification)
            .filter(Notification.conversation_target_id == conversation_id)
            .all()
        }
    assert str(uuid.UUID(a.user_ids["doctor"])) in notice_users
    assert str(uuid.UUID(a.user_ids["nurse"])) in notice_users
    assert str(uuid.UUID(a.user_ids["physiotherapist"])) not in notice_users
    assert str(uuid.UUID(a.user_ids["admin"])) not in notice_users
    assert client.get(
        f"/api/v1/messages/conversations/{conversation_id}", headers=a.act(client, "other_patient")
    ).status_code == 404
    assert client.post(
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        headers=b.act(client, "patient"),
        json={"body": "Tentativa cross-clinic."},
    ).status_code == 404
    assert client.get("/api/v1/messages/inbox", headers=a.act(client, "physiotherapist")).status_code == 403

    inbox = client.get("/api/v1/messages/inbox", headers=a.act(client, "nurse"))
    assert inbox.status_code == 200
    item = next(row for row in inbox.json() if row["id"] == conversation_id)
    assert item["patient_name"] == "Patient 0 messages-a"
    assert item["last_message"]["sender_role"] == "patient"
    assert item["unread"] is True

    assert audit(client, "conversation_created", resource_id=conversation_id)
    assert audit(client, "message_sent", resource_id=conversation_id)
    assert audit(client, "conversation_viewed", resource_id=conversation_id)
    assert audit(client, "permission_denied", resource_id=conversation_id)


def test_nurse_triage_escalates_to_assigned_doctor_and_doctor_closes(client: TestClient, tenants):
    a, b = tenants
    created = start(client, a, "nurse")
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    replied = client.post(
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        headers=a.act(client, "nurse"),
        json={"body": "Vou acompanhar o caso."},
    )
    assert replied.status_code == 200
    status_change = client.patch(
        f"/api/v1/messages/conversations/{conversation_id}/status",
        headers=a.act(client, "nurse"),
        json={"status": "open"},
    )
    assert status_change.status_code == 200
    assert status_change.json()["status"] == "open"

    escalation = client.post(
        f"/api/v1/messages/conversations/{conversation_id}/escalation",
        headers=a.act(client, "nurse"),
    )
    assert escalation.status_code == 200, escalation.text
    assert escalation.json()["needs_doctor_review"] is True
    with client.session_factory() as db:  # type: ignore[attr-defined]
        notices = db.query(Notification).filter(
            Notification.conversation_target_id == conversation_id,
            Notification.title == "Conversa escalada para médico",
        ).all()
        assert len(notices) == 1
        assert str(notices[0].user_id) == a.user_ids["doctor"]

    assert client.post(
        f"/api/v1/messages/conversations/{conversation_id}/escalation", headers=a.act(client, "doctor")
    ).status_code == 403
    assert client.patch(
        f"/api/v1/messages/conversations/{conversation_id}/status",
        headers=a.act(client, "nurse"),
        json={"status": "closed"},
    ).status_code == 403

    doctor_reply = client.post(
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        headers=a.act(client, "doctor"),
        json={"body": "Revisei o caso e podemos manter o plano."},
    )
    assert doctor_reply.status_code == 200
    assert doctor_reply.json()["needs_doctor_review"] is False
    assert audit(client, "conversation_escalation_cleared", resource_id=conversation_id)

    closed = client.patch(
        f"/api/v1/messages/conversations/{conversation_id}/status",
        headers=a.act(client, "doctor"),
        json={"status": "closed"},
    )
    assert closed.status_code == 200
    assert closed.json()["closed_at"] is not None
    assert client.post(
        f"/api/v1/messages/conversations/{conversation_id}/messages",
        headers=a.act(client, "patient"),
        json={"body": "Não deve enviar após fecho."},
    ).status_code == 409
    assert client.get(
        f"/api/v1/messages/conversations/{conversation_id}", headers=b.act(client, "doctor")
    ).status_code == 404
    assert audit(client, "conversation_status_changed", resource_id=conversation_id)
    assert audit(client, "conversation_escalated", resource_id=conversation_id)
    assert audit(client, "permission_denied", resource_id=conversation_id)


def test_clinical_messages_are_database_immutable(client: TestClient, tenants):
    a, _ = tenants
    created = start(client, a)
    message_id = created.json()["messages"][0]["id"]
    with client.session_factory() as db:  # type: ignore[attr-defined]
        message = db.get(ClinicalMessage, uuid.UUID(message_id))
        assert message is not None
        message.body = "Mensagem alterada"
        with pytest.raises(DBAPIError, match="clinical messages are immutable"):
            db.commit()
        db.rollback()


def test_staff_loses_conversation_access_when_patient_assignment_ends(client: TestClient, tenants):
    a, _ = tenants
    assigned = client.post(
        f"/api/v1/patients/{a.other_patient_id}/care-team",
        headers=a.act(client, "clinic_admin"),
        json={"staff_id": a.staff_ids["doctor"]},
    )
    assert assigned.status_code == 201
    created = start(client, a, "doctor", a.other_patient_id)
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    removed = client.delete(
        f"/api/v1/patients/{a.other_patient_id}/care-team/{a.staff_ids['doctor']}",
        headers=a.act(client, "clinic_admin"),
    )
    assert removed.status_code == 200
    assert client.get(
        f"/api/v1/messages/conversations/{conversation_id}", headers=a.act(client, "doctor")
    ).status_code == 403
    assert client.get(
        f"/api/v1/messages/conversations/{conversation_id}", headers=a.act(client, "other_patient")
    ).status_code == 200
    assert audit(client, "permission_denied", resource_id=conversation_id)
