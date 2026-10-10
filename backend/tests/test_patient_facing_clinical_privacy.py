"""Patient-facing clinical responses carry no internal identifiers (P2.4-P2.6 review).

Each patient view is an explicit schema built field by field. These tests pin
the exact key sets, check that no internal clinic/staff identifier appears
anywhere in the patient's responses, and that the care team's views keep the
fields their workflows use.
"""

import pytest
from fastapi.testclient import TestClient

from tests.clinical_support import Tenant, book, grant, make_tenant, prescribe

PATIENT_MEDICATION_KEYS = {
    "view",
    "id",
    "name",
    "dosage",
    "route",
    "frequency",
    "instructions",
    "status",
    "start_date",
    "end_date",
    "created_at",
    "updated_at",
}
# Internal clinic/staff identifiers and staff-only workflow fields. (`patient_id`, the
# patient's own identifier, is still returned by the documents API; it is not staff data.)
PROHIBITED_PATIENT_KEYS = {
    "clinic_id",
    "prescribed_by_staff_id",
    "author_staff_id",
    "released_by_staff_id",
    "editor_staff_id",
    "visibility",
    "visibility_changed_by_name",
    "correction_reason",
    "uploaded_by_user_id",
}


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, "privacy")


def _internal_ids(tenant: Tenant) -> list[str]:
    return [tenant.clinic_id, *tenant.staff_ids.values(), *(tenant.user_ids[r] for r in ("doctor", "nurse"))]


def _walk_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _walk_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _walk_keys(item)}
    return set()


def test_patient_medication_responses_omit_internal_identifiers(client: TestClient, tenant: Tenant):
    medication = prescribe(client, tenant)
    tenant.act(client, "patient")
    listing = client.get(f"/api/v1/patients/{tenant.patient_id}/medications")
    detail = client.get(f"/api/v1/medications/{medication['id']}")
    assert listing.status_code == detail.status_code == 200
    (row,) = listing.json()
    assert set(row) == PATIENT_MEDICATION_KEYS
    assert set(detail.json()) == PATIENT_MEDICATION_KEYS
    assert row["view"] == "patient"
    # What the patient needs to take the medication is still there.
    assert (row["name"], row["dosage"], row["status"], row["start_date"]) == ("Drug A", "10 mg", "active", "2026-01-01")
    for response in (listing, detail):
        for internal in _internal_ids(tenant):
            assert internal not in response.text


def test_staff_medication_workflows_keep_their_fields(client: TestClient, tenant: Tenant):
    medication = prescribe(client, tenant)
    assert medication["view"] == "staff"
    assert medication["prescribed_by_staff_id"] == tenant.staff_ids["doctor"]
    assert medication["clinic_id"] == tenant.clinic_id
    tenant.act(client, "nurse")
    (row,) = client.get(f"/api/v1/patients/{tenant.patient_id}/medications").json()
    assert row["view"] == "staff" and row["prescribed_by_staff_id"] == tenant.staff_ids["doctor"]
    updated = client.patch(
        f"/api/v1/medications/{medication['id']}", headers=tenant.act(client, "doctor"), json={"dosage": "20 mg"}
    )
    assert updated.status_code == 200 and updated.json()["view"] == "staff"
    deactivated = client.post(f"/api/v1/medications/{medication['id']}/deactivate", headers=tenant.act(client, "doctor"))
    assert deactivated.status_code == 200 and deactivated.json()["status"] != "active"
    tenant.act(client, "patient")
    assert client.get(f"/api/v1/medications/{medication['id']}").json()["status"] == deactivated.json()["status"]


def test_no_patient_facing_clinical_api_leaks_internal_identifiers(client: TestClient, tenant: Tenant):
    headers = tenant.act(client, "doctor")
    prescribe(client, tenant)
    record = client.post(
        f"/api/v1/patients/{tenant.patient_id}/medical-records",
        headers=headers,
        json={"title": "Plano", "content": "Partilhado", "share_with_patient": True},
    ).json()
    upload = client.post(
        f"/api/v1/patients/{tenant.patient_id}/documents",
        headers=tenant.act(client, "doctor"),
        data={"title": "Relatório"},
        files={"file": ("r.pdf", b"%PDF-1.7\nreport", "application/pdf")},
    ).json()
    original = client.post(
        f"/api/v1/patients/{tenant.patient_id}/results",
        headers=tenant.act(client, "doctor"),
        json={"category": "laboratory", "title": "Hb", "value": "13", "result_date": "2026-01-01", "document_id": upload["id"], "release": True},
    ).json()
    correction = client.post(
        f"/api/v1/results/{original['id']}/corrections",
        headers=tenant.act(client, "nurse"),
        json={
            "category": "laboratory",
            "title": "Hb",
            "value": "12",
            "result_date": "2026-01-01",
            "correction_reason": "Interno: amostra hemolisada",
            "release": True,
        },
    ).json()

    tenant.act(client, "patient")
    responses = {
        path: client.get(path)
        for path in (
            f"/api/v1/patients/{tenant.patient_id}/medications",
            f"/api/v1/patients/{tenant.patient_id}/medical-records",
            f"/api/v1/medical-records/{record['id']}",
            f"/api/v1/patients/{tenant.patient_id}/results",
            f"/api/v1/results/{original['id']}",
            f"/api/v1/results/{correction['id']}",
            f"/api/v1/patients/{tenant.patient_id}/documents",
            "/api/v1/notifications",
        )
    }
    for path, response in responses.items():
        assert response.status_code == 200, path
        assert not (_walk_keys(response.json()) & PROHIBITED_PATIENT_KEYS), path
        for internal in _internal_ids(tenant):
            assert internal not in response.text, path
        assert "hemolisada" not in response.text, path


PATIENT_APPOINTMENT_KEYS = {"view", "id", "staff_name", "scheduled_at", "duration_minutes", "status", "reason"}
PATIENT_CONSENT_KEYS = {
    "view",
    "id",
    "consent_type",
    "purpose",
    "policy_version",
    "policy_text",
    "status",
    "granted_at",
    "revoked_at",
    "created_at",
    "updated_at",
}


def test_patient_appointments_show_the_professional_by_name_without_internal_ids(client: TestClient, tenant: Tenant):
    appointment = book(client, tenant, reason="Controlo")
    assert appointment["view"] == "staff" and appointment["staff_id"] == tenant.staff_ids["doctor"]

    tenant.act(client, "patient")
    (row,) = client.get("/api/v1/appointments").json()
    detail = client.get(f"/api/v1/appointments/{appointment['id']}")
    assert detail.status_code == 200
    for body in (row, detail.json()):
        assert set(body) == PATIENT_APPOINTMENT_KEYS
        assert body["view"] == "patient"
        # The name the patient needs; the roster endpoint (ids -> names) is closed to patients.
        assert body["staff_name"] == "Doctor privacy"
        assert body["reason"] == "Controlo"
    for internal in _internal_ids(tenant) + [tenant.patient_id]:
        assert internal not in detail.text
    # Another patient still cannot read it.
    tenant.act(client, "other_patient")
    assert client.get(f"/api/v1/appointments/{appointment['id']}").status_code == 404

    # Staff workflows keep their identifiers.
    tenant.act(client, "clinic_admin")
    (staff_row,) = client.get("/api/v1/appointments").json()
    assert staff_row["view"] == "staff" and staff_row["staff_id"] == tenant.staff_ids["doctor"]


def test_patient_consent_history_has_no_internal_ids(client: TestClient, tenant: Tenant):
    granted = grant(client, tenant)
    assert set(granted) == PATIENT_CONSENT_KEYS
    revoked = client.post(f"/api/v1/consents/{granted['id']}/revoke", headers=tenant.act(client, "patient"))
    assert revoked.status_code == 200 and set(revoked.json()) == PATIENT_CONSENT_KEYS
    assert revoked.json()["status"] == "revoked"
    listing = client.get(f"/api/v1/patients/{tenant.patient_id}/consents")
    detail = client.get(f"/api/v1/consents/{granted['id']}")
    for response in (listing, detail):
        assert response.status_code == 200
        assert not ({"clinic_id", "patient_id", "recorded_by_user_id"} & _walk_keys(response.json()))
        assert tenant.user_ids["patient"] not in response.text and tenant.clinic_id not in response.text
    # The assigned care team keeps the full view.
    tenant.act(client, "doctor")
    (row,) = client.get(f"/api/v1/patients/{tenant.patient_id}/consents").json()
    assert row["view"] == "staff" and row["recorded_by_user_id"] == tenant.user_ids["patient"]


def test_patient_conversations_carry_names_not_internal_ids(client: TestClient, tenant: Tenant):
    opened = client.post(
        "/api/v1/conversations", headers=tenant.act(client, "doctor"), json={"patient_id": tenant.patient_id}
    )
    conversation_id = opened.json()["id"]
    assert opened.json()["staff_id"] == tenant.staff_ids["doctor"]
    client.post(
        f"/api/v1/conversations/{conversation_id}/messages", headers=tenant.act(client, "doctor"), json={"body": "Olá"}
    )
    client.post(
        f"/api/v1/conversations/{conversation_id}/messages", headers=tenant.act(client, "patient"), json={"body": "Bom dia"}
    )
    tenant.act(client, "patient")
    (row,) = client.get("/api/v1/conversations").json()
    detail = client.get(f"/api/v1/conversations/{conversation_id}").json()
    for body in (row, detail):
        assert (body["clinic_id"], body["patient_id"], body["staff_id"]) == (None, None, None)
        assert body["staff_name"] == "Doctor privacy"
    # Sender identity is kept for display, and the patient's own messages are still recognised.
    assert [(m["sender_role"], m["is_mine"]) for m in detail["messages"]] == [("patient", True), ("doctor", False)]
    assert all("sender_user_id" not in m for m in detail["messages"])
    for internal in _internal_ids(tenant) + [tenant.patient_id, tenant.user_ids["patient"]]:
        assert internal not in str(detail)
