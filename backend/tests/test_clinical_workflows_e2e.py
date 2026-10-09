"""
End-to-end clinical workflows driven as real logged-in users, against the
real migrated PostgreSQL schema (no mocked services or dependencies).
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.account_support import PASSWORD
from tests.clinical_support import (
    audit,
    book,
    identity,
    make_tenant,
    notify,
    prescribe,
    raw_headers,
    slot,
    use,
    write_record,
)


@pytest.fixture()
def tenant(client: TestClient):
    return make_tenant(client, "e2e")


def _fresh_login(client: TestClient, tenant, role: str) -> dict[str, str]:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login", json={"email": tenant.emails[role], "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    tenant.who[role] = identity(response)
    return tenant.who[role]


def _audit_actor_and_clinic(rows, tenant, role: str) -> None:
    assert len(rows) == 1
    assert str(rows[0].clinic_id) == tenant.clinic_id
    assert str(rows[0].actor_user_id) == tenant.user_ids[role]
    assert rows[0].actor_email == tenant.emails[role]


# --- FLOW A: appointments -------------------------------------------------


def test_flow_a_appointment_lifecycle(client: TestClient, tenant):
    doctor = _fresh_login(client, tenant, "doctor")
    assert client.get("/api/v1/auth/me").json()["staff_role"] == "doctor"

    created = client.post(
        "/api/v1/appointments",
        headers=use(client, doctor),
        json={
            "patient_id": tenant.patient_id,
            "staff_id": tenant.staff_ids["doctor"],
            "scheduled_at": slot(),
            "duration_minutes": 30,
            "reason": "Check-up",
        },
    )
    assert created.status_code == 201, created.text
    appointment = created.json()
    appointment_id = appointment["id"]
    assert appointment["status"] == "scheduled"
    assert appointment["clinic_id"] == tenant.clinic_id
    assert appointment["patient_id"] == tenant.patient_id
    assert appointment["staff_id"] == tenant.staff_ids["doctor"]
    _audit_actor_and_clinic(audit(client, "appointment_created", resource_id=appointment_id), tenant, "doctor")

    detail = client.get(f"/api/v1/appointments/{appointment_id}")
    assert detail.status_code == 200
    assert detail.json()["reason"] == "Check-up"
    assert [row["id"] for row in client.get("/api/v1/appointments").json()] == [appointment_id]

    tenant.act(client, "patient")
    own = client.get(f"/api/v1/appointments/{appointment_id}")
    assert own.status_code == 200
    assert [row["id"] for row in client.get("/api/v1/appointments").json()] == [appointment_id]
    own_view = audit(client, "patient_viewed_own_record", resource_id=appointment_id)
    assert len(own_view) == 1
    assert own_view[0].actor_user_id is not None
    assert str(own_view[0].actor_user_id) == tenant.user_ids["patient"]

    headers = use(client, doctor)
    updated = client.patch(
        f"/api/v1/appointments/{appointment_id}",
        headers=headers,
        json={"status": "confirmed", "duration_minutes": 45, "scheduled_at": slot(minutes=60)},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "confirmed"
    assert updated.json()["duration_minutes"] == 45
    _audit_actor_and_clinic(audit(client, "appointment_updated", resource_id=appointment_id), tenant, "doctor")

    cancelled = client.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    _audit_actor_and_clinic(audit(client, "appointment_cancelled", resource_id=appointment_id), tenant, "doctor")

    assert client.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=headers).status_code == 409
    assert (
        client.patch(
            f"/api/v1/appointments/{appointment_id}", headers=headers, json={"duration_minutes": 20}
        ).status_code
        == 409
    )
    assert client.get(f"/api/v1/appointments/{appointment_id}").json()["status"] == "cancelled"
    assert len(audit(client, "appointment_cancelled", resource_id=appointment_id)) == 1

    # A cancelled slot is bookable again.
    rebooked = client.post(
        "/api/v1/appointments",
        headers=headers,
        json={
            "patient_id": tenant.patient_id,
            "staff_id": tenant.staff_ids["doctor"],
            "scheduled_at": slot(minutes=60),
            "duration_minutes": 45,
        },
    )
    assert rebooked.status_code == 201


def test_appointment_validation_and_rejected_writes_leave_no_trace(client: TestClient, tenant):
    headers = tenant.act(client, "doctor")
    base = {
        "patient_id": tenant.patient_id,
        "staff_id": tenant.staff_ids["doctor"],
        "scheduled_at": slot(),
    }
    invalid_payloads = [
        {**base, "scheduled_at": "2026-12-01T10:00:00"},  # naive datetime
        {**base, "scheduled_at": "not-a-date"},
        {**base, "duration_minutes": 0},
        {**base, "duration_minutes": 481},
        {**base, "reason": "x" * 501},
        {**base, "clinic_id": tenant.clinic_id},  # tenant is never client-supplied
        {**base, "status": "completed"},
        {"patient_id": tenant.patient_id},
        {**base, "patient_id": "not-a-uuid"},
    ]
    for payload in invalid_payloads:
        assert client.post("/api/v1/appointments", headers=headers, json=payload).status_code == 422, payload

    first = book(client, tenant)
    overlap = client.post(
        "/api/v1/appointments", headers=headers, json={**base, "scheduled_at": slot(minutes=10)}
    )
    assert overlap.status_code == 409
    assert len(client.get("/api/v1/appointments").json()) == 1
    assert len(audit(client, "appointment_created")) == 1

    # Back-to-back is fine, and a failed move does not half-apply.
    second = book(client, tenant, scheduled_at=slot(minutes=30))
    clash = client.patch(
        f"/api/v1/appointments/{second['id']}",
        headers=headers,
        json={"scheduled_at": slot(minutes=15), "duration_minutes": 60, "reason": "Moved"},
    )
    assert clash.status_code == 409
    after = client.get(f"/api/v1/appointments/{second['id']}").json()
    assert datetime.fromisoformat(after["scheduled_at"]) == datetime.fromisoformat(slot(minutes=30))
    assert after["duration_minutes"] == 30
    assert after["reason"] is None
    assert first["id"] != second["id"]
    assert len(audit(client, "appointment_updated")) == 0


@pytest.mark.parametrize("field", ["patient_id", "staff_id", "scheduled_at", "duration_minutes", "status"])
def test_appointment_update_rejects_explicit_null_for_required_fields(client: TestClient, tenant, field):
    appointment = book(client, tenant)
    headers = tenant.act(client, "doctor")
    response = client.patch(f"/api/v1/appointments/{appointment['id']}", headers=headers, json={field: None})
    assert response.status_code == 422
    assert client.get(f"/api/v1/appointments/{appointment['id']}").json() == appointment


def test_appointment_reason_can_be_cleared_and_status_cannot_be_set_to_cancelled(client: TestClient, tenant):
    appointment = book(client, tenant, reason="Initial")
    headers = tenant.act(client, "doctor")
    cleared = client.patch(f"/api/v1/appointments/{appointment['id']}", headers=headers, json={"reason": None})
    assert cleared.status_code == 200
    assert cleared.json()["reason"] is None
    assert (
        client.patch(
            f"/api/v1/appointments/{appointment['id']}", headers=headers, json={"status": "cancelled"}
        ).status_code
        == 422
    )
    assert client.patch(f"/api/v1/appointments/{appointment['id']}", headers=headers, json={}).status_code == 422


def test_concurrent_bookings_of_the_same_slot_cannot_both_succeed(client: TestClient, tenant):
    headers = raw_headers(tenant.who["doctor"])
    payload = {
        "patient_id": tenant.patient_id,
        "staff_id": tenant.staff_ids["doctor"],
        "scheduled_at": slot(days=5),
        "duration_minutes": 30,
    }
    barrier = threading.Barrier(4)

    def attempt() -> int:
        barrier.wait()
        return TestClient(app).post("/api/v1/appointments", headers=headers, json=payload).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = sorted(pool.map(lambda _: attempt(), range(4)))

    assert results == [201, 409, 409, 409]
    tenant.act(client, "doctor")
    assert len(client.get("/api/v1/appointments").json()) == 1


# --- FLOW B: medical records ---------------------------------------------


def test_flow_b_medical_record_lifecycle(client: TestClient, tenant):
    doctor = _fresh_login(client, tenant, "doctor")
    headers = use(client, doctor)

    created = client.post(
        f"/api/v1/patients/{tenant.patient_id}/medical-records",
        headers=headers,
        json={"title": "  Assessment  ", "content": "Initial findings"},
    )
    assert created.status_code == 201, created.text
    record = created.json()
    record_id = record["id"]
    assert record["version"] == 1
    assert record["title"] == "Assessment"
    assert record["clinic_id"] == tenant.clinic_id
    assert record["patient_id"] == tenant.patient_id
    assert record["author_staff_id"] == tenant.staff_ids["doctor"]
    _audit_actor_and_clinic(audit(client, "medical_record_created", resource_id=record_id), tenant, "doctor")

    assert client.get(f"/api/v1/medical-records/{record_id}").json()["content"] == "Initial findings"
    assert len(audit(client, "medical_record_viewed", resource_id=record_id)) == 1
    listed = client.get(f"/api/v1/patients/{tenant.patient_id}/medical-records")
    assert [row["id"] for row in listed.json()] == [record_id]
    assert len(audit(client, "medical_record_viewed", resource_id=tenant.patient_id)) == 1

    updated = client.patch(
        f"/api/v1/medical-records/{record_id}",
        headers=headers,
        json={"title": "Assessment", "content": "Revised findings", "expected_version": 1},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["content"] == "Revised findings"
    _audit_actor_and_clinic(audit(client, "medical_record_updated", resource_id=record_id), tenant, "doctor")

    revisions = client.get(f"/api/v1/medical-records/{record_id}/revisions").json()
    assert [(row["version"], row["content"]) for row in revisions] == [
        (1, "Initial findings"),
        (2, "Revised findings"),
    ]

    # The nurse sees the same record; the patient reads it but can never edit it.
    tenant.act(client, "nurse")
    assert client.get(f"/api/v1/medical-records/{record_id}").status_code == 200
    tenant.act(client, "patient")
    assert client.get(f"/api/v1/medical-records/{record_id}").status_code == 200
    denied = client.patch(
        f"/api/v1/medical-records/{record_id}",
        headers=use(client, tenant.who["patient"]),
        json={"title": "Edited", "content": "By patient", "expected_version": 2},
    )
    assert denied.status_code in {403, 404}
    tenant.act(client, "doctor")
    assert client.get(f"/api/v1/medical-records/{record_id}").json()["version"] == 2


def test_medical_record_validation(client: TestClient, tenant):
    headers = tenant.act(client, "doctor")
    url = f"/api/v1/patients/{tenant.patient_id}/medical-records"
    for payload in (
        {"title": "", "content": "x"},
        {"title": "x", "content": "   "},
        {"title": "x" * 201, "content": "x"},
        {"title": "x", "content": "x" * 20_001},
        {"title": "x"},
        {"title": "x", "content": "y", "patient_id": tenant.other_patient_id},
        {"title": "x", "content": "y", "clinic_id": tenant.clinic_id},
        {"title": "x", "content": "y", "version": 99},
    ):
        assert client.post(url, headers=headers, json=payload).status_code == 422, payload
    assert client.get(url).json() == []
    assert len(audit(client, "medical_record_created")) == 0


def test_concurrent_record_updates_get_distinct_gapless_versions(client: TestClient, tenant):
    """Five clinicians edit version 1 at once: the row lock serialises them and the
    optimistic check lets exactly one through; the other four are told to reload
    (409) instead of silently overwriting each other. Versions stay gapless."""
    record = write_record(client, tenant)
    headers = raw_headers(tenant.who["doctor"])
    barrier = threading.Barrier(5)

    def edit(index: int) -> int:
        barrier.wait()
        response = TestClient(app).patch(
            f"/api/v1/medical-records/{record['id']}",
            headers=headers,
            json={"title": "Assessment", "content": f"Edit {index}", "expected_version": 1},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        statuses = list(pool.map(edit, range(5)))

    assert sorted(statuses) == [200, 409, 409, 409, 409]
    tenant.act(client, "doctor")
    revisions = client.get(f"/api/v1/medical-records/{record['id']}/revisions").json()
    assert [row["version"] for row in revisions] == [1, 2]
    assert client.get(f"/api/v1/medical-records/{record['id']}").json()["version"] == 2

    # Sequential edits that each reload first still produce gapless versions.
    for expected in (2, 3, 4):
        response = client.patch(
            f"/api/v1/medical-records/{record['id']}",
            headers=headers,
            json={"title": "Assessment", "content": f"Sequential {expected}", "expected_version": expected},
        )
        assert response.status_code == 200 and response.json()["version"] == expected + 1
    revisions = client.get(f"/api/v1/medical-records/{record['id']}/revisions").json()
    assert [row["version"] for row in revisions] == [1, 2, 3, 4, 5]


# --- FLOW C: medications --------------------------------------------------


def test_flow_c_medication_lifecycle(client: TestClient, tenant):
    doctor = _fresh_login(client, tenant, "doctor")
    headers = use(client, doctor)
    created = client.post(
        f"/api/v1/patients/{tenant.patient_id}/medications",
        headers=headers,
        json={
            "name": "Amoxicillin",
            "dosage": "500 mg",
            "route": "oral",
            "frequency": "8/8h",
            "start_date": "2026-01-10",
        },
    )
    assert created.status_code == 201, created.text
    medication = created.json()
    medication_id = medication["id"]
    assert medication["status"] == "active"
    assert medication["end_date"] is None
    assert medication["clinic_id"] == tenant.clinic_id
    assert medication["patient_id"] == tenant.patient_id
    assert medication["prescribed_by_staff_id"] == tenant.staff_ids["doctor"]
    _audit_actor_and_clinic(audit(client, "medication_created", resource_id=medication_id), tenant, "doctor")

    assert client.get(f"/api/v1/medications/{medication_id}").json()["dosage"] == "500 mg"
    listed = client.get(f"/api/v1/patients/{tenant.patient_id}/medications")
    assert [row["id"] for row in listed.json()] == [medication_id]
    assert listed.headers["x-total-count"] == "1"

    changed = client.patch(
        f"/api/v1/medications/{medication_id}", headers=headers, json={"dosage": "250 mg", "route": None}
    )
    assert changed.status_code == 200
    assert changed.json()["dosage"] == "250 mg"
    assert changed.json()["route"] is None
    assert changed.json()["status"] == "active"
    _audit_actor_and_clinic(audit(client, "medication_updated", resource_id=medication_id), tenant, "doctor")

    ended = client.patch(
        f"/api/v1/medications/{medication_id}", headers=headers, json={"status": "completed"}
    )
    assert ended.status_code == 200
    assert ended.json()["status"] == "completed"
    assert ended.json()["end_date"] == date.today().isoformat()
    _audit_actor_and_clinic(
        audit(client, "medication_deactivated", resource_id=medication_id), tenant, "doctor"
    )

    assert (
        client.patch(
            f"/api/v1/medications/{medication_id}", headers=headers, json={"dosage": "1 mg"}
        ).status_code
        == 409
    )
    assert client.post(f"/api/v1/medications/{medication_id}/deactivate", headers=headers).status_code == 409
    base = f"/api/v1/patients/{tenant.patient_id}/medications"
    assert client.get(f"{base}?status=active").json() == []
    assert [row["id"] for row in client.get(f"{base}?status=completed").json()] == [medication_id]

    # Dedicated termination endpoint, with and without an explicit end date.
    second = prescribe(client, tenant, "Drug B")
    deactivated = client.post(
        f"/api/v1/medications/{second['id']}/deactivate", headers=headers, json={"end_date": "2026-06-30"}
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "discontinued"
    assert deactivated.json()["end_date"] == "2026-06-30"
    third = prescribe(client, tenant, "Drug C")
    assert client.post(f"/api/v1/medications/{third['id']}/deactivate", headers=headers).json()["end_date"] == (
        date.today().isoformat()
    )
    assert len(audit(client, "medication_deactivated")) == 3


@pytest.mark.parametrize("field", ["name", "dosage", "status", "start_date"])
def test_medication_update_rejects_explicit_null_for_required_fields(client: TestClient, tenant, field):
    medication = prescribe(client, tenant)
    headers = tenant.act(client, "doctor")
    response = client.patch(f"/api/v1/medications/{medication['id']}", headers=headers, json={field: None})
    assert response.status_code == 422
    assert client.get(f"/api/v1/medications/{medication['id']}").json() == medication


def test_medication_invalid_end_date_is_rejected_without_partial_update(client: TestClient, tenant):
    medication = prescribe(client, tenant)
    headers = tenant.act(client, "doctor")
    url = f"/api/v1/medications/{medication['id']}"
    assert (
        client.patch(url, headers=headers, json={"dosage": "99 mg", "end_date": "2025-12-31"}).status_code
        == 422
    )
    assert client.post(f"{url}/deactivate", headers=headers, json={"end_date": "2025-12-31"}).status_code == 422
    assert client.get(url).json() == medication
    assert (
        client.post(
            f"/api/v1/patients/{tenant.patient_id}/medications",
            headers=headers,
            json={"name": "X", "dosage": "1", "start_date": "2026-02-01", "end_date": "2026-01-01"},
        ).status_code
        == 422
    )
    assert (
        client.patch(url, headers=headers, json={"status": "completed", "end_date": None}).json()["end_date"]
        == date.today().isoformat()
    )


# --- FLOW D: consent ------------------------------------------------------


def test_flow_d_consent_lifecycle(client: TestClient, tenant):
    patient = _fresh_login(client, tenant, "patient")
    headers = use(client, patient)
    created = client.post(
        f"/api/v1/patients/{tenant.patient_id}/consents",
        headers=headers,
        json={"consent_type": "data_processing", "purpose": "  Care coordination  "},
    )
    assert created.status_code == 201, created.text
    consent = created.json()
    consent_id = consent["id"]
    assert consent["status"] == "granted"
    assert consent["revoked_at"] is None
    assert consent["purpose"] == "Care coordination"
    assert consent["clinic_id"] == tenant.clinic_id
    assert consent["patient_id"] == tenant.patient_id
    assert consent["recorded_by_user_id"] == tenant.user_ids["patient"]
    granted_at = datetime.fromisoformat(consent["granted_at"])
    assert abs(datetime.now(UTC) - granted_at) < timedelta(minutes=1)
    _audit_actor_and_clinic(audit(client, "consent_granted", resource_id=consent_id), tenant, "patient")

    duplicate = client.post(
        f"/api/v1/patients/{tenant.patient_id}/consents",
        headers=headers,
        json={"consent_type": "data_processing", "purpose": "Care coordination"},
    )
    assert duplicate.status_code == 409

    assert client.get(f"/api/v1/consents/{consent_id}").json()["status"] == "granted"
    assert [row["id"] for row in client.get(f"/api/v1/patients/{tenant.patient_id}/consents").json()] == [
        consent_id
    ]
    assert len(audit(client, "consent_viewed", resource_id=consent_id)) == 1

    tenant.act(client, "doctor")
    assert client.get(f"/api/v1/consents/{consent_id}").json()["status"] == "granted"

    revoked = client.post(f"/api/v1/consents/{consent_id}/revoke", headers=use(client, patient))
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert datetime.fromisoformat(revoked.json()["revoked_at"]) >= granted_at
    _audit_actor_and_clinic(audit(client, "consent_revoked", resource_id=consent_id), tenant, "patient")

    final = client.get(f"/api/v1/consents/{consent_id}").json()
    assert final["status"] == "revoked"
    assert final["revoked_at"] == revoked.json()["revoked_at"]
    assert final["granted_at"] == consent["granted_at"]
    headers = use(client, patient)
    assert client.post(f"/api/v1/consents/{consent_id}/revoke", headers=headers).status_code == 409
    assert len(audit(client, "consent_revoked", resource_id=consent_id)) == 1

    # Revocation keeps the history row; granting again creates a new one.
    regrant = client.post(
        f"/api/v1/patients/{tenant.patient_id}/consents",
        headers=headers,
        json={"consent_type": "data_processing", "purpose": "Care coordination"},
    )
    assert regrant.status_code == 201
    history = client.get(f"/api/v1/patients/{tenant.patient_id}/consents").json()
    assert [row["status"] for row in history] == ["granted", "revoked"]


def test_consent_validation_and_server_derived_fields(client: TestClient, tenant):
    headers = tenant.act(client, "patient")
    url = f"/api/v1/patients/{tenant.patient_id}/consents"
    for payload in (
        {"consent_type": "treatment", "purpose": "   "},
        {"consent_type": "treatment", "purpose": "x" * 501},
        {"consent_type": "unknown", "purpose": "x"},
        {"consent_type": "treatment"},
        {"consent_type": "treatment", "purpose": "x", "status": "revoked"},
        {"consent_type": "treatment", "purpose": "x", "clinic_id": tenant.clinic_id},
        {"consent_type": "treatment", "purpose": "x", "granted_at": "2020-01-01T00:00:00Z"},
    ):
        assert client.post(url, headers=headers, json=payload).status_code == 422, payload
    assert client.get(url).json() == []


# --- notifications --------------------------------------------------------


def test_notification_inbox_lifecycle(client: TestClient, tenant):
    first = notify(client, tenant, "patient", "Primeira")
    second = notify(client, tenant, "patient", "Segunda")
    doctor_note = notify(client, tenant, "doctor", "Interna")

    headers = tenant.act(client, "patient")
    listed = client.get("/api/v1/notifications")
    assert listed.status_code == 200
    assert {row["id"] for row in listed.json()} == {first, second}
    assert listed.headers["x-total-count"] == "2"
    assert all(row["is_read"] is False for row in listed.json())
    page = client.get("/api/v1/notifications?page=2&page_size=1")
    assert len(page.json()) == 1
    assert page.headers["x-total-count"] == "2"
    assert client.get("/api/v1/notifications?page=0").status_code == 422
    assert client.get("/api/v1/notifications?page_size=101").status_code == 422

    read = client.post(f"/api/v1/notifications/{first}/read", headers=headers)
    assert read.status_code == 200
    assert read.json()["is_read"] is True
    read_at = read.json()["read_at"]
    assert read_at is not None
    _audit_actor_and_clinic(audit(client, "notification_read", resource_id=first), tenant, "patient")

    again = client.post(f"/api/v1/notifications/{first}/read", headers=headers)
    assert again.status_code == 200
    assert again.json()["read_at"] == read_at
    unread = [row for row in client.get("/api/v1/notifications").json() if not row["is_read"]]
    assert [row["id"] for row in unread] == [second]

    # Another user in the same clinic never sees or touches it.
    headers = tenant.act(client, "other_patient")
    assert client.get("/api/v1/notifications").json() == []
    assert client.post(f"/api/v1/notifications/{second}/read", headers=headers).status_code == 404
    headers = tenant.act(client, "doctor")
    assert [row["id"] for row in client.get("/api/v1/notifications").json()] == [doctor_note]
    assert client.post(f"/api/v1/notifications/{second}/read", headers=headers).status_code == 404
    tenant.act(client, "patient")
    still_unread = [row for row in client.get("/api/v1/notifications").json() if row["id"] == second]
    assert still_unread[0]["is_read"] is False
