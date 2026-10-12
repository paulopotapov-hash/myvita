"""Scheduling, step 4: a patient books a free slot ("Marcação direta").

The server re-checks type, time, horizon, eligibility and availability under the clinic
lock; the appointment is confirmed at once, the professional joins the care team, and a
slot taken in the meantime answers 409. Synthetic data only.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import Appointment, AuditAction, AuditLog, BookingSource, ClinicalCareAssignment
from tests.clinical_support import Tenant, make_tenant, raw_headers
from tests.scheduling_support import next_weekday, setup_booking


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"book-{uuid.uuid4().hex[:8]}")


def _slots(client: TestClient, tenant: Tenant, type_id: str, day, staff_id: str | None = None) -> list[dict]:
    url = f"/api/v1/scheduling/slots?appointment_type_id={type_id}&from={day}&to={day}"
    if staff_id:
        url += f"&staff_id={staff_id}"
    return client.get(url).json()


def test_patient_books_a_free_slot_confirmed_at_once(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(1)
    headers = tenant.act(client, "other_patient")  # not on the doctor's care team yet
    professionals = client.get(f"/api/v1/scheduling/bookable-professionals?appointment_type_id={ids['type_id']}").json()
    assert [row["id"] for row in professionals] == [tenant.staff_ids["doctor"]]
    slot = _slots(client, tenant, ids["type_id"], day)[0]
    booked = client.post(
        "/api/v1/scheduling/bookings",
        headers=headers,
        json={"appointment_type_id": ids["type_id"], "staff_id": tenant.staff_ids["doctor"], "starts_at": slot["starts_at"], "reason": "Rotina"},
    )
    assert booked.status_code == 201, booked.text
    body = booked.json()
    assert body["view"] == "patient" and body["status"] == "confirmed"
    assert (body["appointment_type"], body["specialty"]) == ("Consulta de rotina", "Medicina Geral")
    assert "staff_id" not in body and "patient_id" not in body
    with client.session_factory() as db:  # type: ignore[attr-defined]
        appointment = db.get(Appointment, uuid.UUID(body["id"]))
        assert appointment.booked_via == BookingSource.PATIENT
        link = db.query(ClinicalCareAssignment).filter_by(
            patient_id=uuid.UUID(tenant.other_patient_id), staff_id=uuid.UUID(tenant.staff_ids["doctor"]), active=True
        ).one()
        assert link.origin_appointment_id == appointment.id
        audit = db.query(AuditLog).filter(AuditLog.action == AuditAction.APPOINTMENT_CREATED).all()
        assert audit[-1].event_metadata["via"] == "patient"
        assert "Rotina" not in str(audit[-1].event_metadata)
    # The slot is gone for everyone.
    assert all(row["starts_at"] != slot["starts_at"] for row in _slots(client, tenant, ids["type_id"], day))


def test_any_available_picks_a_free_professional(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(2)
    tenant.act(client, "patient")
    slot = _slots(client, tenant, ids["type_id"], day)[0]
    booked = client.post(
        "/api/v1/scheduling/bookings", headers=tenant.act(client, "patient"), json={"appointment_type_id": ids["type_id"], "starts_at": slot["starts_at"]}
    )
    assert booked.status_code == 201, booked.text


def test_a_slot_taken_meanwhile_or_not_offered_is_refused(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(3)
    tenant.act(client, "patient")
    slot = _slots(client, tenant, ids["type_id"], day)[0]
    body = {"appointment_type_id": ids["type_id"], "staff_id": tenant.staff_ids["doctor"], "starts_at": slot["starts_at"]}
    assert client.post("/api/v1/scheduling/bookings", headers=tenant.act(client, "patient"), json=body).status_code == 201
    taken = client.post("/api/v1/scheduling/bookings", headers=tenant.act(client, "other_patient"), json=body)
    assert taken.status_code == 409
    assert taken.json()["detail"] == "Este horário já não está disponível. Escolhe outro."
    # A time that is not one of the offered slots (off-grid, outside the schedule, in the past).
    start = datetime.fromisoformat(slot["starts_at"])
    for when in (start + timedelta(minutes=10), start + timedelta(hours=8), datetime.now(UTC) - timedelta(days=1)):
        refused = client.post("/api/v1/scheduling/bookings", headers=tenant.act(client, "other_patient"), json={**body, "starts_at": when.isoformat()})
        assert refused.status_code == 409, when
    # The same patient cannot be in two places at once.
    nurse_specialty = ids["specialty_id"]
    headers = tenant.act(client, "clinic_admin")
    client.patch(f"/api/v1/scheduling/professionals/{tenant.staff_ids['nurse']}", headers=headers, json={"specialty_id": nurse_specialty})
    client.post(
        f"/api/v1/scheduling/professionals/{tenant.staff_ids['nurse']}/schedule",
        headers=headers,
        json={"rules": [{"weekday": day.weekday(), "start_time": "09:00", "end_time": "12:00", "appointment_type_ids": [ids["type_id"]]}]},
    )
    own = client.post(
        "/api/v1/scheduling/bookings", headers=tenant.act(client, "patient"), json={**body, "staff_id": tenant.staff_ids["nurse"]}
    )
    assert own.status_code == 409 and own.json()["detail"] == "Já tens uma consulta a essa hora."


def test_concurrent_patients_cannot_both_book_the_same_slot(client: TestClient, second_client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(4)
    tenant.act(client, "patient")
    slot = _slots(client, tenant, ids["type_id"], day)[0]
    body = {"appointment_type_id": ids["type_id"], "staff_id": tenant.staff_ids["doctor"], "starts_at": slot["starts_at"]}
    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def book(test_client: TestClient, who: str) -> None:
        barrier.wait()
        statuses.append(test_client.post("/api/v1/scheduling/bookings", headers=raw_headers(tenant.who[who]), json=body).status_code)

    client.cookies.clear()
    threads = [threading.Thread(target=book, args=(client, "patient")), threading.Thread(target=book, args=(second_client, "other_patient"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert sorted(statuses) == [201, 409]


def test_request_only_types_new_patient_rule_and_staff_cannot_use_patient_booking(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant, mode="request")
    day = next_weekday(1)
    tenant.act(client, "patient")
    slot = _slots(client, tenant, ids["type_id"], day)[0]
    body = {"appointment_type_id": ids["type_id"], "starts_at": slot["starts_at"]}
    assert client.post("/api/v1/scheduling/bookings", headers=tenant.act(client, "patient"), json=body).status_code == 422
    assert client.post("/api/v1/scheduling/bookings", headers=tenant.act(client, "doctor"), json=body).status_code == 403

    headers = tenant.act(client, "clinic_admin")
    client.patch(f"/api/v1/scheduling/appointment-types/{ids['type_id']}", headers=headers, json={"booking_mode": "direct"})
    client.patch(f"/api/v1/scheduling/professionals/{tenant.staff_ids['doctor']}", headers=headers, json={"accepts_new_patients": False})
    tenant.act(client, "other_patient")
    assert client.get(f"/api/v1/scheduling/bookable-professionals?appointment_type_id={ids['type_id']}").json() == []
    refused = client.post(
        "/api/v1/scheduling/bookings", headers=tenant.act(client, "other_patient"), json={**body, "staff_id": tenant.staff_ids["doctor"]}
    )
    assert refused.status_code == 404

    other = make_tenant(client, f"book-other-{uuid.uuid4().hex[:6]}")
    assert client.post("/api/v1/scheduling/bookings", headers=other.act(client, "patient"), json=body).status_code == 404


def test_slots_never_offer_a_time_the_patient_is_already_booked_at(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(1)
    tenant.act(client, "patient")
    first = _slots(client, tenant, ids["type_id"], day)[0]
    # The patient already has an appointment (with the nurse) at the doctor's first slot.
    created = client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "clinic_admin"),
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["nurse"], "scheduled_at": first["starts_at"]},
    )
    assert created.status_code == 201, created.text
    tenant.act(client, "patient")
    assert all(slot["starts_at"] != first["starts_at"] for slot in _slots(client, tenant, ids["type_id"], day))
    # Staff still see the doctor's slot as free (it is free for another patient).
    tenant.act(client, "clinic_admin")
    assert any(slot["starts_at"] == first["starts_at"] for slot in _slots(client, tenant, ids["type_id"], day))
