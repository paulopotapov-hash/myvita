"""
Tenant isolation and IDOR coverage for the Phase 2/3 modules (documents,
conversations, messages and their notifications), which the original
security matrix predates. Real HTTP, real PostgreSQL, real roles.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.models import AuditLog, Notification
from tests.clinical_support import ALL_ROLES, Tenant, make_tenant

SECRET = "PHASE4SECRET"
PDF = b"%PDF-1.4\n" + SECRET.encode() + b"-file-bytes\n%%EOF\n"
DENIED = {403, 404}


def _note(client: TestClient, tenant: Tenant, tag: str) -> dict:
    response = client.post(
        f"/api/v1/patients/{tenant.patient_id}/documents/notes",
        headers=tenant.act(client, "doctor"),
        json={"title": f"Nota {tag}", "content": f"{SECRET}-NOTE-{tag}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _pdf(client: TestClient, tenant: Tenant, tag: str) -> dict:
    response = client.post(
        f"/api/v1/patients/{tenant.patient_id}/documents/files",
        headers=tenant.act(client, "doctor"),
        data={"title": f"PDF {tag}"},
        files={"file": ("relatorio.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    second = client.post(
        f"/api/v1/documents/{response.json()['id']}/files/versions",
        headers=tenant.act(client, "doctor"),
        data={"title": f"PDF {tag}"},
        files={"file": ("relatorio-v2.pdf", PDF + b"v2", "application/pdf")},
    )
    assert second.status_code == 200, second.text
    return second.json()


def _conversation(client: TestClient, tenant: Tenant, tag: str) -> dict:
    response = client.post(
        f"/api/v1/messages/patients/{tenant.patient_id}/conversations",
        headers=tenant.act(client, "doctor"),
        json={"subject": f"Assunto {tag}", "body": f"{SECRET}-MSG-{tag}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def world(client: TestClient):
    a, b = make_tenant(client, "p4-a"), make_tenant(client, "p4-b")
    seeds = {}
    for tenant, tag in ((a, "A"), (b, "B")):
        seeds[tag] = {
            "note": _note(client, tenant, tag)["id"],
            "pdf": _pdf(client, tenant, tag)["id"],
            "conversation": _conversation(client, tenant, tag)["id"],
        }
    return a, b, seeds


def _targets(tenant: Tenant, seed: dict) -> list[tuple[str, str, str, dict | None]]:
    pid, note, pdf, conv = tenant.patient_id, seed["note"], seed["pdf"], seed["conversation"]
    return [
        ("document list", "GET", f"/api/v1/patients/{pid}/documents", None),
        ("note create", "POST", f"/api/v1/patients/{pid}/documents/notes", {"title": "INJ", "content": "INJ"}),
        ("document detail", "GET", f"/api/v1/documents/{note}", None),
        ("note update", "PATCH", f"/api/v1/documents/{note}/notes", {"title": "INJ", "content": "INJ"}),
        ("version history", "GET", f"/api/v1/documents/{pdf}/versions", None),
        ("old version", "GET", f"/api/v1/documents/{pdf}/versions/1", None),
        ("download current", "GET", f"/api/v1/documents/{pdf}/download", None),
        ("download old version", "GET", f"/api/v1/documents/{pdf}/versions/1/download", None),
        ("conversation create", "POST", f"/api/v1/messages/patients/{pid}/conversations", {"subject": "INJ", "body": "INJ"}),
        ("conversation detail", "GET", f"/api/v1/messages/conversations/{conv}", None),
        ("message reply", "POST", f"/api/v1/messages/conversations/{conv}/messages", {"body": "INJ"}),
        ("status change", "PATCH", f"/api/v1/messages/conversations/{conv}/status", {"status": "closed"}),
        ("escalation", "POST", f"/api/v1/messages/conversations/{conv}/escalation", None),
    ]


def _assert_unchanged(client: TestClient, tenant: Tenant, seed: dict) -> None:
    tenant.act(client, "doctor")
    note = client.get(f"/api/v1/documents/{seed['note']}").json()
    assert note["current_version"] == 1
    assert [d["title"] for d in client.get(f"/api/v1/patients/{tenant.patient_id}/documents").json()].count("INJ") == 0
    conversation = client.get(f"/api/v1/messages/conversations/{seed['conversation']}").json()
    assert [m["body"] for m in conversation["messages"]] == [f"{SECRET}-MSG-{'A' if 'p4-a' in tenant.emails['doctor'] else 'B'}"]
    assert conversation["status"] != "closed"
    assert conversation["needs_doctor_review"] is False


@pytest.mark.parametrize("attacker_is_b", [True, False], ids=["B-attacks-A", "A-attacks-B"])
@pytest.mark.parametrize("role", ALL_ROLES)
def test_documents_and_messaging_never_cross_clinics(client: TestClient, world, attacker_is_b: bool, role: str):
    a, b, seeds = world
    attacker, victim, seed = (b, a, seeds["A"]) if attacker_is_b else (a, b, seeds["B"])
    headers = attacker.act(client, role)
    for label, method, url, body in _targets(victim, seed):
        response = client.request(method, url, json=body, headers=headers)
        assert response.status_code in DENIED, f"{role}: {label} -> {response.status_code}"
        assert SECRET not in response.text, f"{role}: {label} leaked"
    _assert_unchanged(client, victim, seed)


@pytest.mark.parametrize("role", ["other_patient", "physiotherapist", "admin", "clinic_admin"])
def test_same_clinic_roles_without_clinical_access_are_denied(client: TestClient, world, role: str):
    a, _b, seeds = world
    headers = a.act(client, role)
    for label, method, url, body in _targets(a, seeds["A"]):
        response = client.request(method, url, json=body, headers=headers)
        assert response.status_code in DENIED, f"{role}: {label} -> {response.status_code}"
        assert SECRET not in response.text, f"{role}: {label} leaked"
    _assert_unchanged(client, a, seeds["A"])


def test_patient_reads_own_documents_and_replies_but_cannot_author(client: TestClient, world):
    a, _b, seeds = world
    headers = a.act(client, "patient")
    assert client.get(f"/api/v1/documents/{seeds['A']['pdf']}/download").content == PDF + b"v2"
    assert client.get(f"/api/v1/documents/{seeds['A']['pdf']}/versions/1/download").content == PDF
    for method, url, body in (
        ("POST", f"/api/v1/patients/{a.patient_id}/documents/notes", {"title": "X", "content": "Y"}),
        ("PATCH", f"/api/v1/documents/{seeds['A']['note']}/notes", {"title": "X", "content": "Y"}),
        ("POST", f"/api/v1/messages/patients/{a.patient_id}/conversations", {"subject": "X", "body": "Y"}),
        ("PATCH", f"/api/v1/messages/conversations/{seeds['A']['conversation']}/status", {"status": "closed"}),
        ("POST", f"/api/v1/messages/conversations/{seeds['A']['conversation']}/escalation", None),
    ):
        assert client.request(method, url, json=body, headers=headers).status_code in DENIED, url
    reply = client.post(
        f"/api/v1/messages/conversations/{seeds['A']['conversation']}/messages", headers=headers, json={"body": "Obrigado."}
    )
    assert reply.status_code == 200, reply.text
    # Messages are append-only: no edit or delete route exists at all.
    message_id = reply.json()["messages"][0]["id"]
    for method in ("PATCH", "PUT", "DELETE"):
        response = client.request(method, f"/api/v1/messages/conversations/{seeds['A']['conversation']}/messages/{message_id}", headers=headers)
        assert response.status_code in {404, 405}, method


def test_notifications_carry_no_clinical_content_and_targets_recheck_access(client: TestClient, world):
    a, b, seeds = world
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = db.query(Notification).all()
        for row in rows:
            db.expunge(row)
    assert rows
    for row in rows:
        assert SECRET not in f"{row.title} {row.message}", row.title

    # A notification id or target from clinic A is useless to clinic B's patient.
    a_patient_notes = [n for n in rows if str(n.user_id) == a.user_ids["patient"]]
    assert {str(n.clinic_id) for n in a_patient_notes} == {a.clinic_id}
    b_headers = b.act(client, "patient")
    for note in a_patient_notes:
        assert client.post(f"/api/v1/notifications/{note.id}/read", headers=b_headers).status_code == 404
        if note.target_id:
            assert client.get(f"/api/v1/documents/{note.target_id}").status_code in DENIED
        if note.conversation_target_id:
            assert client.get(f"/api/v1/messages/conversations/{note.conversation_target_id}").status_code in DENIED
    assert all(SECRET not in n["title"] + n["message"] for n in client.get("/api/v1/notifications").json())


def test_revoked_assignment_closes_documents_and_messaging(client: TestClient, world):
    a, _b, seeds = world
    removed = client.delete(
        f"/api/v1/patients/{a.patient_id}/care-team/{a.staff_ids['nurse']}", headers=a.act(client, "clinic_admin")
    )
    assert removed.status_code == 200, removed.text
    a.act(client, "nurse")
    for url in (
        f"/api/v1/documents/{seeds['A']['note']}",
        f"/api/v1/documents/{seeds['A']['pdf']}/download",
        f"/api/v1/messages/conversations/{seeds['A']['conversation']}",
    ):
        assert client.get(url).status_code == 403, url
    assert seeds["A"]["conversation"] not in client.get("/api/v1/messages/inbox").text


def test_audit_trail_records_identifiers_never_clinical_content(client: TestClient, world):
    a, b, seeds = world
    b.act(client, "doctor")
    client.get(f"/api/v1/documents/{seeds['A']['pdf']}/download")
    client.get(f"/api/v1/messages/conversations/{seeds['A']['conversation']}")
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = db.query(AuditLog).all()
        for row in rows:
            db.expunge(row)
    actions = {row.action.value for row in rows}
    assert {"conversation_created", "message_sent"} <= actions, actions
    assert any(row.resource_type == "document" for row in rows)
    for row in rows:
        blob = f"{row.event_metadata} {row.resource_type} {row.user_agent}"
        assert SECRET not in blob and "file-bytes" not in blob, row.action
    denied = [
        row
        for row in rows
        if row.action.value == "permission_denied" and str(row.resource_id) in {seeds["A"]["pdf"], seeds["A"]["conversation"]}
    ]
    assert len(denied) == 2
    assert {str(row.clinic_id) for row in denied} == {b.clinic_id}
    assert all(uuid.UUID(str(row.actor_user_id)) == uuid.UUID(b.user_ids["doctor"]) for row in denied)
