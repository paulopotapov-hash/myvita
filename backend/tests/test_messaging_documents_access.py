"""
Integration Phase 4: access, audit and notification rules for the live
documents API and one-to-one messaging (decisions M1-M6, D1-D4).

Ported from Parent A's tests/test_documents_messaging_isolation.py, which
targeted the removed clinical-documents and shared-inbox APIs. Real HTTP, real
PostgreSQL, real roles. Every denial asserts both the HTTP response and the
PERMISSION_DENIED audit row it leaves (actor's clinic, target resource id).
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.clinical_access import ROLE_ACTIONS, ClinicalAction
from app.core.config import settings
from app.models import AuditLog, Conversation, Message, Notification, StaffRole
from app.modules.messages.service import INACTIVE_CONVERSATION
from tests.clinical_support import ALL_ROLES, Tenant, make_tenant

SECRET = "PHASE4SECRET"
PDF = b"%PDF-1.4\n" + SECRET.encode() + b"-file-bytes\n%%EOF\n"
DENIED = {403, 404}


@pytest.fixture(autouse=True)
def _document_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path))


# --- helpers -----------------------------------------------------------------


def _rows(client: TestClient, **filters: Any) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = db.query(AuditLog).filter_by(**filters).order_by(AuditLog.timestamp).all()
        for row in rows:
            db.expunge(row)
        return rows


def _denial_ids(client: TestClient, actor_user_id: str) -> set[uuid.UUID]:
    return {
        row.id
        for row in _rows(client, actor_user_id=uuid.UUID(actor_user_id))
        if row.action.value == "permission_denied"
    }


def assert_denied(
    client: TestClient,
    tenant: Tenant,
    role: str,
    method: str,
    url: str,
    *,
    resource_id: str,
    expected: set[int] | None = None,
    **request: Any,
):
    """The request is refused AND exactly one PERMISSION_DENIED row records it."""
    actor = tenant.user_ids[role]
    before = _denial_ids(client, actor)
    headers = tenant.act(client, role)
    response = client.request(method, url, headers=headers, **request)
    assert response.status_code in (expected or DENIED), f"{role}: {method} {url} -> {response.status_code}"
    assert SECRET not in response.text, f"{role}: {method} {url} leaked"
    new = [
        row
        for row in _rows(client, actor_user_id=uuid.UUID(actor))
        if row.action.value == "permission_denied" and row.id not in before
    ]
    assert len(new) == 1, f"{role}: {method} {url} -> {len(new)} denial audit rows"
    row = new[0]
    assert row.result.value == "denied"
    assert str(row.clinic_id) == tenant.clinic_id, "denials are recorded under the ACTOR's clinic"
    assert str(row.resource_id) == str(resource_id)
    assert (row.event_metadata or {}).get("path") == url
    return response


def _upload(client: TestClient, tenant: Tenant, tag: str) -> dict:
    response = client.post(
        f"/api/v1/patients/{tenant.patient_id}/documents",
        headers=tenant.act(client, "doctor"),
        data={"title": f"Relatório {tag} {SECRET}"},
        files={"file": ("relatorio.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _open(client: TestClient, tenant: Tenant, role: str = "doctor", patient_id: str | None = None) -> str:
    response = client.post(
        "/api/v1/conversations",
        headers=tenant.act(client, role),
        json={"patient_id": patient_id or tenant.patient_id},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _send(client: TestClient, tenant: Tenant, role: str, conversation_id: str, body: str):
    return client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=tenant.act(client, role),
        json={"body": body},
    )


def _conversation_row(client: TestClient, tenant: Tenant, role: str, conversation_id: str) -> dict | None:
    tenant.act(client, role)
    listed = client.get("/api/v1/conversations")
    assert listed.status_code == 200, listed.text
    return next((c for c in listed.json() if c["id"] == conversation_id), None)


def _count(client: TestClient, model: Any, **filters: Any) -> int:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(model).filter_by(**filters).count()


@pytest.fixture()
def world(client: TestClient):
    a, b = make_tenant(client, "p4-a"), make_tenant(client, "p4-b")
    seeds = {}
    for tenant, tag in ((a, "A"), (b, "B")):
        document = _upload(client, tenant, tag)
        conversation = _open(client, tenant)
        assert _send(client, tenant, "doctor", conversation, f"{SECRET}-MSG-{tag}").status_code == 201
        seeds[tag] = {"document": document["id"], "conversation": conversation}
    return a, b, seeds


def _targets(victim: Tenant, seed: dict) -> list[tuple[str, str, str, dict]]:
    pid, doc, conv = victim.patient_id, seed["document"], seed["conversation"]
    upload = {
        "data": {"title": "INJ"},
        "files": {"file": ("inj.pdf", b"%PDF-1.4 INJ", "application/pdf")},
    }
    return [
        ("GET", f"/api/v1/patients/{pid}/documents", pid, {}),
        ("POST", f"/api/v1/patients/{pid}/documents", pid, upload),
        ("GET", f"/api/v1/documents/{doc}/download", doc, {}),
        ("POST", "/api/v1/conversations", pid, {"json": {"patient_id": pid}}),
        ("GET", f"/api/v1/conversations/{conv}", conv, {}),
        ("POST", f"/api/v1/conversations/{conv}/messages", conv, {"json": {"body": "INJ"}}),
        ("POST", f"/api/v1/conversations/{conv}/read", conv, {}),
    ]


def _assert_unchanged(client: TestClient, tenant: Tenant, seed: dict, tag: str) -> None:
    tenant.act(client, "doctor")
    documents = client.get(f"/api/v1/patients/{tenant.patient_id}/documents").json()
    assert [d["id"] for d in documents] == [seed["document"]]
    detail = client.get(f"/api/v1/conversations/{seed['conversation']}").json()
    assert [m["body"] for m in detail["messages"]] == [f"{SECRET}-MSG-{tag}"]
    assert detail["unread_count"] == 0
    # The read marker was not touched by the intruder either.
    assert all(m["read_at"] is None for m in detail["messages"])
    assert _count(client, Conversation, patient_id=uuid.UUID(tenant.patient_id)) == 1


# --- tenant isolation and same-clinic roles ----------------------------------


@pytest.mark.parametrize("attacker_is_b", [True, False], ids=["B-attacks-A", "A-attacks-B"])
@pytest.mark.parametrize("role", ALL_ROLES)
def test_documents_and_messaging_never_cross_clinics(client: TestClient, world, attacker_is_b: bool, role: str):
    a, b, seeds = world
    attacker, victim, tag = (b, a, "A") if attacker_is_b else (a, b, "B")
    for method, url, resource_id, request in _targets(victim, seeds[tag]):
        assert_denied(client, attacker, role, method, url, resource_id=resource_id, **request)
    _assert_unchanged(client, victim, seeds[tag], tag)


@pytest.mark.parametrize("role", ["other_patient", "physiotherapist", "admin", "clinic_admin"])
def test_same_clinic_roles_without_clinical_access_are_denied(client: TestClient, world, role: str):
    a, _b, seeds = world
    for method, url, resource_id, request in _targets(a, seeds["A"]):
        assert_denied(client, a, role, method, url, resource_id=resource_id, **request)
    _assert_unchanged(client, a, seeds["A"], "A")


def test_threads_are_one_to_one_even_inside_the_care_team(client: TestClient, world):
    """B's model is kept: an assigned nurse does not see the doctor's thread (no shared inbox)."""
    a, _b, seeds = world
    conversation = seeds["A"]["conversation"]
    assert _conversation_row(client, a, "nurse", conversation) is None
    assert_denied(client, a, "nurse", "GET", f"/api/v1/conversations/{conversation}", resource_id=conversation)
    assert_denied(
        client,
        a,
        "nurse",
        "POST",
        f"/api/v1/conversations/{conversation}/messages",
        resource_id=conversation,
        json={"body": "INJ"},
    )


# --- patient: reads, replies, never authors ----------------------------------


def test_patient_reads_own_documents_and_replies_but_cannot_author(client: TestClient, world):
    a, _b, seeds = world
    a.act(client, "patient")
    assert client.get(f"/api/v1/documents/{seeds['A']['document']}/download").content == PDF

    assert_denied(
        client,
        a,
        "patient",
        "POST",
        f"/api/v1/patients/{a.patient_id}/documents",
        resource_id=a.patient_id,
        data={"title": "X"},
        files={"file": ("x.pdf", b"%PDF-1.4 X", "application/pdf")},
    )
    # M4: patients cannot start conversations, not even with their own care team.
    started = assert_denied(
        client,
        a,
        "patient",
        "POST",
        "/api/v1/conversations",
        resource_id=a.patient_id,
        expected={403},
        json={"patient_id": a.patient_id},
    )
    assert "não podem iniciar" in started.json()["detail"]
    assert _count(client, Conversation, patient_id=uuid.UUID(a.patient_id)) == 1

    reply = _send(client, a, "patient", seeds["A"]["conversation"], "Obrigado.")
    assert reply.status_code == 201, reply.text

    # Documents and messages are append-only: no edit or delete route exists.
    headers = a.act(client, "patient")
    message_id = reply.json()["id"]
    for method, url in (
        ("DELETE", f"/api/v1/documents/{seeds['A']['document']}"),
        ("PATCH", f"/api/v1/conversations/{seeds['A']['conversation']}/messages/{message_id}"),
        ("PUT", f"/api/v1/conversations/{seeds['A']['conversation']}/messages/{message_id}"),
        ("DELETE", f"/api/v1/conversations/{seeds['A']['conversation']}/messages/{message_id}"),
        ("DELETE", f"/api/v1/conversations/{seeds['A']['conversation']}"),
    ):
        assert client.request(method, url, headers=headers).status_code in {404, 405}, (method, url)


# --- notifications (M6, D4) ----------------------------------------------------


def test_notifications_are_generic_and_link_to_their_target(client: TestClient, world):
    a, b, seeds = world
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = db.query(Notification).filter(Notification.user_id == uuid.UUID(a.user_ids["patient"])).all()
        for row in rows:
            db.expunge(row)
    targets = {(row.target_type, str(row.target_id or row.conversation_target_id)) for row in rows}
    assert ("document", seeds["A"]["document"]) in targets
    assert ("conversation", seeds["A"]["conversation"]) in targets
    for row in rows:
        # No message body, title or filename: notifications live outside the access rules.
        assert SECRET not in f"{row.title} {row.message}"
        assert "Relatório" not in row.message and "relatorio" not in row.message
        assert str(row.clinic_id) == a.clinic_id

    a.act(client, "patient")
    api_rows = client.get("/api/v1/notifications").json()
    assert {(n["target_type"], n["target_id"] or n["conversation_target_id"]) for n in api_rows} >= {
        ("document", seeds["A"]["document"]),
        ("conversation", seeds["A"]["conversation"]),
    }
    assert all(SECRET not in n["title"] + n["message"] for n in api_rows)

    # A notification id or target from clinic A is useless to clinic B's patient.
    for row in rows:
        assert_denied(
            client, b, "patient", "POST", f"/api/v1/notifications/{row.id}/read", resource_id=str(row.id)
        )
    assert_denied(
        client,
        b,
        "patient",
        "GET",
        f"/api/v1/documents/{seeds['A']['document']}/download",
        resource_id=seeds["A"]["document"],
    )
    assert_denied(
        client,
        b,
        "patient",
        "GET",
        f"/api/v1/conversations/{seeds['A']['conversation']}",
        resource_id=seeds["A"]["conversation"],
    )


# --- M1 / M2: the care assignment is checked on every list, read and reply ----


def test_ended_assignment_hides_threads_from_the_professional_and_freezes_them_for_the_patient(
    client: TestClient, world
):
    a, _b, seeds = world
    conversation, document = seeds["A"]["conversation"], seeds["A"]["document"]
    removed = client.delete(
        f"/api/v1/patients/{a.patient_id}/care-team/{a.staff_ids['doctor']}", headers=a.act(client, "clinic_admin")
    )
    assert removed.status_code == 200, removed.text

    # M1: the professional gets exactly the not-found answer, on list, read and reply.
    assert _conversation_row(client, a, "doctor", conversation) is None
    unknown = str(uuid.uuid4())
    a.act(client, "doctor")
    not_found = client.get(f"/api/v1/conversations/{unknown}")
    ended = assert_denied(client, a, "doctor", "GET", f"/api/v1/conversations/{conversation}", resource_id=conversation)
    assert (ended.status_code, ended.json()) == (not_found.status_code, not_found.json()) == (404, not_found.json())
    for method, url, request in (
        ("POST", f"/api/v1/conversations/{conversation}/messages", {"json": {"body": "INJ"}}),
        ("POST", f"/api/v1/conversations/{conversation}/read", {}),
    ):
        assert_denied(client, a, "doctor", method, url, resource_id=conversation, expected={404}, **request)
    # Documents follow the same central policy.
    assert_denied(
        client, a, "doctor", "GET", f"/api/v1/patients/{a.patient_id}/documents", resource_id=a.patient_id
    )
    assert_denied(client, a, "doctor", "GET", f"/api/v1/documents/{document}/download", resource_id=document)

    # M2: the patient keeps the history but the thread is read-only, enforced by the backend.
    row = _conversation_row(client, a, "patient", conversation)
    assert row is not None and row["can_reply"] is False
    a.act(client, "patient")
    history = client.get(f"/api/v1/conversations/{conversation}")
    assert history.status_code == 200
    assert history.json()["can_reply"] is False
    assert [m["body"] for m in history.json()["messages"]] == [f"{SECRET}-MSG-A"]
    messages_before = _count(client, Message)
    doctor_notifications = _count(client, Notification, user_id=uuid.UUID(a.user_ids["doctor"]))
    refused = assert_denied(
        client,
        a,
        "patient",
        "POST",
        f"/api/v1/conversations/{conversation}/messages",
        resource_id=conversation,
        expected={403},
        json={"body": "Alguém está aí?"},
    )
    assert refused.json()["detail"] == INACTIVE_CONVERSATION
    # A patient message never lands in a thread nobody can read.
    assert _count(client, Message) == messages_before
    assert _count(client, Notification, user_id=uuid.UUID(a.user_ids["doctor"])) == doctor_notifications

    # Re-assigning the professional reactivates the same thread.
    again = client.post(
        f"/api/v1/patients/{a.patient_id}/care-team",
        headers=a.act(client, "clinic_admin"),
        json={"staff_id": a.staff_ids["doctor"]},
    )
    assert again.status_code == 201, again.text
    row = _conversation_row(client, a, "patient", conversation)
    assert row is not None and row["can_reply"] is True
    assert _send(client, a, "patient", conversation, "Obrigado.").status_code == 201
    assert _conversation_row(client, a, "doctor", conversation) is not None


def test_deactivated_professional_makes_the_thread_read_only_for_the_patient(client: TestClient, world):
    a, _b, seeds = world
    conversation = seeds["A"]["conversation"]
    deactivated = client.post(
        f"/api/v1/staff/{a.staff_ids['doctor']}/deactivate", headers=a.act(client, "clinic_admin")
    )
    assert deactivated.status_code == 200, deactivated.text
    row = _conversation_row(client, a, "patient", conversation)
    assert row is not None and row["can_reply"] is False
    refused = assert_denied(
        client,
        a,
        "patient",
        "POST",
        f"/api/v1/conversations/{conversation}/messages",
        resource_id=conversation,
        expected={403},
        json={"body": "Olá?"},
    )
    assert refused.json()["detail"] == INACTIVE_CONVERSATION


# --- M3: starting a conversation -----------------------------------------------


def test_staff_start_requires_an_active_assignment(client: TestClient, world):
    a, _b, _seeds = world
    # other_patient has no care team at all.
    assert_denied(
        client,
        a,
        "doctor",
        "POST",
        "/api/v1/conversations",
        resource_id=a.other_patient_id,
        expected={403},
        json={"patient_id": a.other_patient_id},
    )
    assert _count(client, Conversation, patient_id=uuid.UUID(a.other_patient_id)) == 0
    # An assigned nurse may open her own thread with the patient.
    assert _open(client, a, "nurse")


def test_staff_start_uses_the_messaging_permission_not_the_documents_one(
    client: TestClient, world, monkeypatch
):
    a, _b, _seeds = world
    without_create = ROLE_ACTIONS[StaffRole.NURSE] - {ClinicalAction.CREATE_CONVERSATIONS}
    assert ClinicalAction.VIEW_DOCUMENTS in without_create
    monkeypatch.setitem(ROLE_ACTIONS, StaffRole.NURSE, without_create)
    a.act(client, "nurse")
    # Still assigned and still allowed to read the patient's documents ...
    assert client.get(f"/api/v1/patients/{a.patient_id}/documents").status_code == 200
    # ... but without the messaging permission the start is refused.
    assert_denied(
        client,
        a,
        "nurse",
        "POST",
        "/api/v1/conversations",
        resource_id=a.patient_id,
        expected={403},
        json={"patient_id": a.patient_id},
    )
    assert _count(client, Conversation, staff_id=uuid.UUID(a.staff_ids["nurse"])) == 0


# --- M5: inbox views and refusals are audited ----------------------------------


def test_inbox_views_are_audited_per_conversation(client: TestClient, world):
    a, _b, seeds = world
    conversation = seeds["A"]["conversation"]
    a.act(client, "doctor")
    assert client.get("/api/v1/conversations").status_code == 200
    viewed = [
        row
        for row in _rows(client, actor_user_id=uuid.UUID(a.user_ids["doctor"]), resource_type="conversation")
        if row.action.value == "conversation_viewed" and (row.event_metadata or {}).get("operation") == "list"
    ]
    assert [str(row.resource_id) for row in viewed] == [conversation]
    assert str(viewed[0].clinic_id) == a.clinic_id


@pytest.mark.parametrize("role", ["clinic_admin", "admin", "physiotherapist"])
def test_roles_without_messaging_are_refused_the_inbox(client: TestClient, world, role: str):
    a, _b, _seeds = world
    assert_denied(
        client, a, role, "GET", "/api/v1/conversations", resource_id=a.user_ids[role], expected={403}
    )


# --- D1: document list views are audited ---------------------------------------


def test_document_list_view_is_audited_against_the_patient(client: TestClient, world):
    a, _b, _seeds = world
    a.act(client, "nurse")
    assert client.get(f"/api/v1/patients/{a.patient_id}/documents").status_code == 200
    viewed = [
        row
        for row in _rows(client, actor_user_id=uuid.UUID(a.user_ids["nurse"]))
        if row.action.value == "document_viewed"
    ]
    assert len(viewed) == 1
    assert str(viewed[0].resource_id) == a.patient_id
    assert viewed[0].event_metadata["patient_id"] == a.patient_id
    assert viewed[0].event_metadata["operation"] == "list"
    assert viewed[0].event_metadata["count"] == 1


# --- audit never carries clinical content --------------------------------------


def test_audit_trail_records_identifiers_never_clinical_content(client: TestClient, world):
    a, _b, seeds = world
    rows = _rows(client)
    actions = {row.action.value for row in rows}
    assert {"conversation_created", "message_sent", "document_uploaded"} <= actions, actions
    for row in rows:
        blob = f"{row.event_metadata} {row.resource_type} {row.user_agent} {row.actor_email}"
        assert SECRET not in blob and "file-bytes" not in blob and "Relatório" not in blob, row.action
    uploaded = [r for r in rows if r.action.value == "document_uploaded" and str(r.resource_id) == seeds["A"]["document"]]
    assert len(uploaded) == 1 and str(uploaded[0].clinic_id) == a.clinic_id
