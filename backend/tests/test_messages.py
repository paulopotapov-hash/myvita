"""
Patient <-> clinical staff messaging: authentication, participant
authorization, tenant isolation, IDOR, validation, notifications and audit.

Requires a real Postgres via TEST_DATABASE_URL (see conftest.py).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models import AuditAction, AuditLog, Message, Notification, User
from app.modules.messages.schemas import MESSAGE_MAX_LENGTH
from app.modules.messages.service import NEW_MESSAGE_NOTIFICATION_MESSAGE, NEW_MESSAGE_NOTIFICATION_TITLE
from tests.conftest import TEST_DATABASE_URL

PASSWORD = "SenhaForte123!"


@pytest.fixture()
def client():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.test_session = test_session
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _identity(response) -> dict[str, str]:
    session = response.cookies.get(settings.COOKIE_NAME)
    csrf = response.cookies.get(settings.CSRF_COOKIE_NAME)
    assert session and csrf
    return {"session": session, "csrf": csrf}


def _use(client: TestClient, identity: dict[str, str]) -> dict[str, str]:
    client.cookies.set(settings.COOKIE_NAME, identity["session"])
    client.cookies.set(settings.CSRF_COOKIE_NAME, identity["csrf"])
    return {settings.CSRF_HEADER_NAME: identity["csrf"]}


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return _identity(response)


def _staff(client: TestClient, admin: dict[str, str], suffix: str, name: str, role: str) -> dict:
    email = f"msg-{name}-{suffix}@example.pt"
    response = client.post(
        "/api/v1/staff",
        headers=_use(client, admin),
        json={"full_name": f"{name} {suffix}", "email": email, "password": PASSWORD, "staff_role": role},
    )
    assert response.status_code == 201
    return {"id": response.json()["id"], "email": email}


def _patient(client: TestClient, clinic_id: str, suffix: str, name: str) -> dict:
    email = f"msg-{name}-{suffix}@example.pt"
    client.cookies.clear()
    response = client.post(
        "/api/v1/patients/register",
        json={"clinic_id": clinic_id, "full_name": f"{name} {suffix}", "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201
    return {"id": response.json()["id"], "email": email, "identity": _identity(response)}


def _tenant(client: TestClient, suffix: str) -> dict:
    """Clinic with admin, two doctors, a nurse, an admin-role staff member and two patients."""
    client.cookies.clear()
    response = client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": f"Msg Clinic {suffix}",
            "admin_full_name": f"Admin {suffix}",
            "admin_email": f"msg-admin-{suffix}@example.pt",
            "admin_password": PASSWORD,
        },
    )
    assert response.status_code == 201
    admin = _identity(response)
    clinic_id = response.json()["id"]
    doctor = _staff(client, admin, suffix, "doctor", "doctor")
    doctor2 = _staff(client, admin, suffix, "doctortwo", "doctor")
    nurse = _staff(client, admin, suffix, "nurse", "nurse")
    office = _staff(client, admin, suffix, "office", "admin")
    patient = _patient(client, clinic_id, suffix, "patient")
    patient2 = _patient(client, clinic_id, suffix, "patienttwo")
    for member in (doctor, doctor2, nurse, office):
        member["identity"] = _login(client, member["email"])
    return {
        "clinic_id": clinic_id,
        "admin": admin,
        "doctor": doctor,
        "doctor2": doctor2,
        "nurse": nurse,
        "office": office,
        "patient": patient,
        "patient2": patient2,
    }


def _book(client: TestClient, tenant: dict, patient: dict, staff: dict) -> None:
    response = client.post(
        "/api/v1/appointments",
        headers=_use(client, tenant["admin"]),
        json={"patient_id": patient["id"], "staff_id": staff["id"], "scheduled_at": "2026-11-03T10:00:00Z"},
    )
    assert response.status_code == 201


def _open(client: TestClient, staff: dict, patient: dict) -> str:
    response = client.post(
        "/api/v1/conversations", headers=_use(client, staff["identity"]), json={"patient_id": patient["id"]}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _send(client: TestClient, actor: dict, conversation_id: str, body: str):
    return client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=_use(client, actor["identity"]),
        json={"body": body},
    )


def _user_id(client: TestClient, email: str) -> uuid.UUID:
    db = client.test_session()
    try:
        return db.query(User).filter(User.email == email).one().id
    finally:
        db.close()


# --- authentication ---------------------------------------------------------


def test_unauthenticated_requests_are_rejected(client):
    tenant = _tenant(client, "anon")
    conversation_id = _open(client, tenant["doctor"], tenant["patient"])
    client.cookies.clear()
    assert client.get("/api/v1/conversations").status_code == 401
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 401
    assert (
        client.post(f"/api/v1/conversations/{conversation_id}/messages", json={"body": "Olá"}).status_code
        == 401
    )
    assert client.post(f"/api/v1/conversations/{conversation_id}/read").status_code == 401
    assert (
        client.post("/api/v1/conversations", json={"patient_id": tenant["patient"]["id"]}).status_code == 401
    )


# --- messaging happy path ---------------------------------------------------


def test_staff_and_patient_exchange_messages(client):
    tenant = _tenant(client, "flow")
    doctor, patient = tenant["doctor"], tenant["patient"]

    created = client.post(
        "/api/v1/conversations", headers=_use(client, doctor["identity"]), json={"patient_id": patient["id"]}
    )
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["patient_id"] == patient["id"]
    assert conversation["staff_id"] == doctor["id"]
    assert conversation["clinic_id"] == tenant["clinic_id"]
    assert conversation["patient_name"] == "patient flow"
    assert conversation["staff_name"] == "doctor flow"
    assert conversation["unread_count"] == 0

    # Re-opening the same pair returns the existing conversation, not a duplicate.
    again = client.post(
        "/api/v1/conversations", headers=_use(client, doctor["identity"]), json={"patient_id": patient["id"]}
    )
    assert again.status_code == 200
    assert again.json()["id"] == conversation["id"]

    sent = _send(client, doctor, conversation["id"], "  Bom dia, como se sente?  ")
    assert sent.status_code == 201
    assert sent.json()["body"] == "Bom dia, como se sente?"
    assert sent.json()["read_at"] is None
    assert sent.json()["sender_user_id"] == str(_user_id(client, doctor["email"]))

    _use(client, patient["identity"])
    listed = client.get("/api/v1/conversations")
    assert listed.status_code == 200
    assert listed.headers["X-Total-Count"] == "1"
    assert listed.json()[0]["id"] == conversation["id"]
    assert listed.json()[0]["unread_count"] == 1

    reply = _send(client, patient, conversation["id"], "Melhor, obrigado.")
    assert reply.status_code == 201

    detail = client.get(f"/api/v1/conversations/{conversation['id']}")
    assert detail.status_code == 200
    assert detail.headers["X-Total-Count"] == "2"
    assert [m["body"] for m in detail.json()["messages"]] == ["Melhor, obrigado.", "Bom dia, como se sente?"]

    page = client.get(f"/api/v1/conversations/{conversation['id']}?page=2&page_size=1")
    assert [m["body"] for m in page.json()["messages"]] == ["Bom dia, como se sente?"]

    # Patient reads: only the doctor's message is marked, never the patient's own.
    read = client.post(
        f"/api/v1/conversations/{conversation['id']}/read", headers=_use(client, patient["identity"])
    )
    assert read.status_code == 200
    assert read.json() == {"updated_count": 1}
    assert client.post(
        f"/api/v1/conversations/{conversation['id']}/read", headers=_use(client, patient["identity"])
    ).json() == {"updated_count": 0}
    messages = {
        m["body"]: m for m in client.get(f"/api/v1/conversations/{conversation['id']}").json()["messages"]
    }
    assert messages["Bom dia, como se sente?"]["read_at"] is not None
    assert messages["Melhor, obrigado."]["read_at"] is None

    _use(client, doctor["identity"])
    assert client.get("/api/v1/conversations").json()[0]["unread_count"] == 1


def test_list_is_paginated_and_ordered_by_latest_activity(client):
    tenant = _tenant(client, "paging")
    doctor = tenant["doctor"]
    first = _open(client, doctor, tenant["patient"])
    second = _open(client, doctor, tenant["patient2"])
    assert _send(client, doctor, first, "Mais recente").status_code == 201

    _use(client, doctor["identity"])
    listed = client.get("/api/v1/conversations?page=1&page_size=1")
    assert listed.headers["X-Total-Count"] == "2"
    assert [c["id"] for c in listed.json()] == [first]
    assert [c["id"] for c in client.get("/api/v1/conversations?page=2&page_size=1").json()] == [second]
    assert client.get("/api/v1/conversations?page_size=101").status_code == 422


def test_patient_can_start_conversation_only_with_their_professionals(client):
    tenant = _tenant(client, "patient-start")
    patient = tenant["patient"]
    headers = _use(client, patient["identity"])

    no_relationship = client.post(
        "/api/v1/conversations", headers=headers, json={"staff_id": tenant["doctor"]["id"]}
    )
    assert no_relationship.status_code == 403

    _book(client, tenant, patient, tenant["doctor"])
    headers = _use(client, patient["identity"])
    created = client.post("/api/v1/conversations", headers=headers, json={"staff_id": tenant["doctor"]["id"]})
    assert created.status_code == 201
    assert created.json()["patient_id"] == patient["id"]

    # A patient cannot name a different patient, or both sides.
    assert (
        client.post(
            "/api/v1/conversations", headers=headers, json={"patient_id": tenant["patient2"]["id"]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/conversations",
            headers=headers,
            json={"staff_id": tenant["doctor"]["id"], "patient_id": tenant["patient2"]["id"]},
        ).status_code
        == 422
    )
    # Unknown fields are rejected, so clinic_id can't be smuggled in.
    assert (
        client.post(
            "/api/v1/conversations",
            headers=headers,
            json={"staff_id": tenant["doctor"]["id"], "clinic_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )


def test_non_clinical_users_cannot_message(client):
    tenant = _tenant(client, "roles")
    patient_id = tenant["patient"]["id"]
    _book(client, tenant, tenant["patient"], tenant["office"])
    for identity in (tenant["admin"], tenant["office"]["identity"]):
        response = client.post(
            "/api/v1/conversations", headers=_use(client, identity), json={"patient_id": patient_id}
        )
        assert response.status_code == 403
        assert client.get("/api/v1/conversations").json() == []

    # Patients can't reach admin-role staff even with an appointment.
    response = client.post(
        "/api/v1/conversations",
        headers=_use(client, tenant["patient"]["identity"]),
        json={"staff_id": tenant["office"]["id"]},
    )
    assert response.status_code == 404

    # Nurses are clinical staff and may message.
    assert _open(client, tenant["nurse"], tenant["patient"])


# --- validation -------------------------------------------------------------


@pytest.mark.parametrize("body", ["", "   ", "\n\t  ", "x" * (MESSAGE_MAX_LENGTH + 1)])
def test_invalid_message_bodies_are_rejected(client, body):
    tenant = _tenant(client, "validation")
    conversation_id = _open(client, tenant["doctor"], tenant["patient"])
    response = _send(client, tenant["doctor"], conversation_id, body)
    assert response.status_code == 422
    assert (
        client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_use(client, tenant["doctor"]["identity"]),
            json={"body": "ok", "sender_user_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )
    db = client.test_session()
    try:
        assert db.query(Message).count() == 0
        assert db.query(Notification).count() == 0
    finally:
        db.close()


def test_message_at_max_length_is_accepted(client):
    tenant = _tenant(client, "maxlen")
    conversation_id = _open(client, tenant["doctor"], tenant["patient"])
    assert _send(client, tenant["doctor"], conversation_id, "x" * MESSAGE_MAX_LENGTH).status_code == 201


# --- authorization / IDOR within one clinic --------------------------------


def test_non_participants_in_same_clinic_cannot_access_conversation(client):
    tenant = _tenant(client, "same-clinic")
    conversation_id = _open(client, tenant["doctor"], tenant["patient"])
    assert _send(client, tenant["doctor"], conversation_id, "Privado").status_code == 201

    outsiders = [
        tenant["doctor2"]["identity"],  # another doctor
        tenant["nurse"]["identity"],
        tenant["patient2"]["identity"],  # another patient
        tenant["admin"],
        tenant["office"]["identity"],
    ]
    for identity in outsiders:
        headers = _use(client, identity)
        assert client.get("/api/v1/conversations").json() == []
        assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
        assert _send(client, {"identity": identity}, conversation_id, "Intrusão").status_code == 404
        assert (
            client.post(f"/api/v1/conversations/{conversation_id}/read", headers=headers).status_code == 404
        )

    db = client.test_session()
    try:
        messages = db.query(Message).all()
        assert [m.body for m in messages] == ["Privado"]
        assert messages[0].read_at is None
    finally:
        db.close()


def test_unknown_and_malformed_ids_return_not_found_or_validation_error(client):
    tenant = _tenant(client, "ids")
    _use(client, tenant["doctor"]["identity"])
    missing = uuid.uuid4()
    assert client.get(f"/api/v1/conversations/{missing}").status_code == 404
    assert _send(client, tenant["doctor"], str(missing), "Olá").status_code == 404
    assert client.get("/api/v1/conversations/not-a-uuid").status_code == 422
    # A message id is never accepted where a conversation id is expected.
    conversation_id = _open(client, tenant["doctor"], tenant["patient"])
    message_id = _send(client, tenant["doctor"], conversation_id, "Olá").json()["id"]
    _use(client, tenant["doctor"]["identity"])
    assert client.get(f"/api/v1/conversations/{message_id}").status_code == 404
    # Nor can a user id or patient id be used as a conversation id.
    for other_id in (str(_user_id(client, tenant["patient"]["email"])), tenant["patient"]["id"]):
        assert client.get(f"/api/v1/conversations/{other_id}").status_code == 404


def test_recipient_read_never_modifies_senders_own_messages(client):
    tenant = _tenant(client, "own-read")
    conversation_id = _open(client, tenant["doctor"], tenant["patient"])
    assert _send(client, tenant["doctor"], conversation_id, "Do médico").status_code == 201
    # The sender "reading" their own conversation must not mark their outgoing message read.
    read = client.post(
        f"/api/v1/conversations/{conversation_id}/read", headers=_use(client, tenant["doctor"]["identity"])
    )
    assert read.json() == {"updated_count": 0}
    db = client.test_session()
    try:
        assert db.query(Message).one().read_at is None
    finally:
        db.close()


# --- tenant isolation -------------------------------------------------------


def test_clinic_b_cannot_reach_clinic_a_conversations(client):
    clinic_a = _tenant(client, "tenant-a")
    clinic_b = _tenant(client, "tenant-b")
    conversation_id = _open(client, clinic_a["doctor"], clinic_a["patient"])
    assert _send(client, clinic_a["patient"], conversation_id, "Dados da clínica A").status_code == 201

    for identity in (clinic_b["doctor"]["identity"], clinic_b["patient"]["identity"], clinic_b["admin"]):
        headers = _use(client, identity)
        assert client.get("/api/v1/conversations").json() == []
        assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
        assert _send(client, {"identity": identity}, conversation_id, "Intrusão").status_code == 404
        assert (
            client.post(f"/api/v1/conversations/{conversation_id}/read", headers=headers).status_code == 404
        )

    # Clinic B staff cannot open a conversation with a clinic A patient (patient_id IDOR) ...
    response = client.post(
        "/api/v1/conversations",
        headers=_use(client, clinic_b["doctor"]["identity"]),
        json={"patient_id": clinic_a["patient"]["id"]},
    )
    assert response.status_code == 404
    # ... and a clinic B patient cannot target a clinic A doctor (staff_id IDOR).
    response = client.post(
        "/api/v1/conversations",
        headers=_use(client, clinic_b["patient"]["identity"]),
        json={"staff_id": clinic_a["doctor"]["id"]},
    )
    assert response.status_code == 404

    db = client.test_session()
    try:
        messages = db.query(Message).all()
        assert len(messages) == 1
        assert messages[0].read_at is None
        assert str(messages[0].clinic_id) == clinic_a["clinic_id"]
    finally:
        db.close()


# --- notifications ----------------------------------------------------------


def test_sending_notifies_only_the_recipient_without_content(client):
    tenant = _tenant(client, "notify")
    doctor, patient = tenant["doctor"], tenant["patient"]
    conversation_id = _open(client, doctor, patient)
    secret = "Resultado da biópsia: confidencial"
    assert _send(client, doctor, conversation_id, secret).status_code == 201

    patient_user_id = _user_id(client, patient["email"])
    doctor_user_id = _user_id(client, doctor["email"])
    db = client.test_session()
    try:
        notifications = db.query(Notification).all()
        assert len(notifications) == 1
        notification = notifications[0]
        assert notification.user_id == patient_user_id
        assert str(notification.clinic_id) == tenant["clinic_id"]
        assert notification.title == NEW_MESSAGE_NOTIFICATION_TITLE
        assert notification.message == NEW_MESSAGE_NOTIFICATION_MESSAGE
        assert "biópsia" not in notification.title + notification.message
        assert db.query(Notification).filter(Notification.user_id == doctor_user_id).count() == 0
    finally:
        db.close()

    _use(client, patient["identity"])
    assert [n["title"] for n in client.get("/api/v1/notifications").json()] == [
        NEW_MESSAGE_NOTIFICATION_TITLE
    ]

    # The reply notifies the doctor, not the patient again.
    assert _send(client, patient, conversation_id, "Obrigado").status_code == 201
    db = client.test_session()
    try:
        assert db.query(Notification).filter(Notification.user_id == doctor_user_id).count() == 1
        assert db.query(Notification).filter(Notification.user_id == patient_user_id).count() == 1
    finally:
        db.close()


def test_notification_failure_rolls_back_message(client, monkeypatch):
    tenant = _tenant(client, "atomic")
    conversation_id = _open(client, tenant["doctor"], tenant["patient"])
    from app.modules.messages import service

    def broken_notification(**_kwargs):
        raise RuntimeError("synthetic notification failure")

    monkeypatch.setattr(service, "Notification", broken_notification)
    with pytest.raises(RuntimeError, match="synthetic notification failure"):
        _send(client, tenant["doctor"], conversation_id, "Não deve persistir")
    db = client.test_session()
    try:
        assert db.query(Message).count() == 0
    finally:
        db.close()


# --- audit ------------------------------------------------------------------


def test_audit_events_identify_resources_without_message_content(client):
    tenant = _tenant(client, "audit")
    doctor, patient = tenant["doctor"], tenant["patient"]
    conversation_id = _open(client, doctor, patient)
    body = "Conteúdo clínico sensível"
    message_id = _send(client, doctor, conversation_id, body).json()["id"]
    _use(client, patient["identity"])
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 200
    assert (
        client.post(
            f"/api/v1/conversations/{conversation_id}/read", headers=_use(client, patient["identity"])
        ).status_code
        == 200
    )
    # Reopening an existing conversation is not a second "created" event.
    _open_again = client.post(
        "/api/v1/conversations", headers=_use(client, doctor["identity"]), json={"patient_id": patient["id"]}
    )
    assert _open_again.status_code == 200

    db = client.test_session()
    try:

        def events(action):
            return db.query(AuditLog).filter(AuditLog.action == action).all()

        created = events(AuditAction.CONVERSATION_CREATED)
        assert len(created) == 1
        assert str(created[0].resource_id) == conversation_id
        assert created[0].actor_user_id == _user_id(client, doctor["email"])
        assert str(created[0].clinic_id) == tenant["clinic_id"]

        sent = events(AuditAction.MESSAGE_SENT)
        assert len(sent) == 1
        assert str(sent[0].resource_id) == message_id
        assert sent[0].event_metadata == {"conversation_id": conversation_id}

        viewed = events(AuditAction.CONVERSATION_VIEWED)
        assert len(viewed) == 1
        assert viewed[0].actor_user_id == _user_id(client, patient["email"])

        read = events(AuditAction.MESSAGE_READ)
        assert len(read) == 1
        assert read[0].event_metadata == {"updated_count": 1}

        for row in db.query(AuditLog).all():
            assert body not in repr(row.event_metadata)
    finally:
        db.close()
