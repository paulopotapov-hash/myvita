"""Scheduling, step 6: the waiting list ("Fast Pass").

- A patient joins for one of their direct-type appointments (same professional or same
  specialty); one active entry per appointment.
- A freed slot is offered at once to every matching entry whose appointment is later and
  whose patient is free then; nothing is assigned automatically.
- The first acceptance wins: the slot is booked and the old appointment cancelled together;
  the other offers close; a late acceptance is refused and changes nothing.
- Entries close with their appointment; offers expire after the clinic's minutes.
Synthetic data only.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from fastapi.testclient import TestClient

from app.models import (
    Appointment,
    AppointmentStatus,
    AuditAction,
    AuditLog,
    BookingSource,
    ClinicalCareAssignment,
    Notification,
    WaitlistEntry,
    WaitlistOffer,
    WaitlistOfferStatus,
    WaitlistStatus,
)
from app.modules.scheduling.waitlist import ALREADY_LISTED, DIRECT_ONLY, OFFER_GONE, expire_offers
from tests.clinical_support import PASSWORD, Tenant, identity, make_tenant, raw_headers, use
from tests.conftest import alembic_config
from tests.scheduling_support import next_weekday, setup_booking

URL = "/api/v1/waitlist"


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"wait-{uuid.uuid4().hex[:8]}")


def _at(day, hour: int, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo("Europe/Lisbon")).astimezone(UTC).isoformat()


def _book(client: TestClient, headers: dict, type_id: str, starts_at: str, staff_id: str) -> dict:
    response = client.post(
        "/api/v1/scheduling/bookings", headers=headers, json={"appointment_type_id": type_id, "staff_id": staff_id, "starts_at": starts_at}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _third_patient(client: TestClient, tenant: Tenant) -> dict:
    client.cookies.clear()
    registered = client.post(
        "/api/v1/patients/register",
        json={"clinic_id": tenant.clinic_id, "full_name": "Patient 2 waitlist", "email": f"third-{uuid.uuid4().hex[:8]}@example.pt", "password": PASSWORD},
    )
    assert registered.status_code == 201, registered.text
    return {"who": identity(registered), "patient_id": registered.json()["id"]}


def _join(client: TestClient, headers: dict, appointment_id: str, scope: str = "professional") -> dict:
    response = client.post(URL, headers=headers, json={"appointment_id": appointment_id, "scope": scope})
    assert response.status_code == 201, response.text
    return response.json()


def _offers(client: TestClient, headers: dict) -> list[dict]:
    return [offer for entry in client.get(URL, headers=headers).json() for offer in entry["offers"]]


def _cancel(client: TestClient, headers: dict, appointment_id: str) -> None:
    response = client.post(f"/api/v1/scheduling/bookings/{appointment_id}/cancel", headers=headers)
    assert response.status_code == 200, response.text


def test_joining_is_for_the_patients_own_direct_appointments_once(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(1)
    headers = tenant.act(client, "other_patient")
    booked = _book(client, headers, ids["type_id"], _at(day, 11), tenant.staff_ids["doctor"])
    entry = _join(client, tenant.act(client, "other_patient"), booked["id"])
    assert (entry["status"], entry["scope"], entry["offers"]) == ("active", "professional", [])
    again = client.post(URL, headers=tenant.act(client, "other_patient"), json={"appointment_id": booked["id"]})
    assert again.status_code == 409 and again.json()["detail"] == ALREADY_LISTED

    assert client.post(URL, headers=tenant.act(client, "patient"), json={"appointment_id": booked["id"]}).status_code == 404
    assert client.post(URL, headers=tenant.act(client, "doctor"), json={"appointment_id": booked["id"]}).status_code == 403
    untyped = client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "admin"),
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": _at(day, 15)},
    ).json()
    refused = client.post(URL, headers=tenant.act(client, "patient"), json={"appointment_id": untyped["id"]})
    assert refused.status_code == 422 and refused.json()["detail"] == DIRECT_ONLY

    left = client.post(f"{URL}/{entry['id']}/leave", headers=tenant.act(client, "other_patient"))
    assert left.status_code == 200 and left.json()["status"] == "left"
    assert client.get(URL, headers=tenant.act(client, "other_patient")).json() == []
    assert _join(client, tenant.act(client, "other_patient"), booked["id"])["status"] == "active"  # may join again


def test_a_cancelled_slot_is_offered_and_accepting_moves_the_appointment(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(2)
    early = _book(client, tenant.act(client, "patient"), ids["type_id"], _at(day, 9), tenant.staff_ids["doctor"])
    late = _book(client, tenant.act(client, "other_patient"), ids["type_id"], _at(day, 11), tenant.staff_ids["doctor"])
    entry = _join(client, tenant.act(client, "other_patient"), late["id"])

    _cancel(client, tenant.act(client, "patient"), early["id"])
    [offer] = _offers(client, tenant.act(client, "other_patient"))
    assert datetime.fromisoformat(offer["starts_at"]) == datetime.fromisoformat(_at(day, 9))
    assert offer["staff_name"] and "staff_id" not in offer
    expires = datetime.fromisoformat(offer["expires_at"])
    assert timedelta(minutes=55) < expires - datetime.now(UTC) <= timedelta(minutes=60)  # the clinic's 60 minutes
    with client.session_factory() as db:  # type: ignore[attr-defined]
        titles = [row.title for row in db.query(Notification).filter_by(user_id=uuid.UUID(tenant.user_ids["other_patient"]))]
    assert "Vaga mais cedo disponível" in titles

    accepted = client.post(f"{URL}/offers/{offer['id']}/accept", headers=tenant.act(client, "other_patient"))
    assert accepted.status_code == 201, accepted.text
    new = accepted.json()
    assert datetime.fromisoformat(new["scheduled_at"]) == datetime.fromisoformat(_at(day, 9)) and new["status"] == "confirmed"
    with client.session_factory() as db:  # type: ignore[attr-defined]
        old = db.get(Appointment, uuid.UUID(late["id"]))
        moved = db.get(Appointment, uuid.UUID(new["id"]))
        assert old.status == AppointmentStatus.CANCELLED and moved.rescheduled_from_id == old.id
        assert moved.booked_via == BookingSource.WAITLIST
        assert db.get(WaitlistEntry, uuid.UUID(entry["id"])).status == WaitlistStatus.FULFILLED
        stored = db.get(WaitlistOffer, uuid.UUID(offer["id"]))
        assert stored.status == WaitlistOfferStatus.ACCEPTED and stored.new_appointment_id == moved.id
        [link] = db.query(ClinicalCareAssignment).filter_by(patient_id=uuid.UUID(tenant.other_patient_id), active=True).all()
        assert link.origin_appointment_id == moved.id
        actions = {row.action for row in db.query(AuditLog).filter(AuditLog.resource_id.in_([uuid.UUID(offer["id"]), old.id]))}
    assert {AuditAction.WAITLIST_OFFER_ACCEPTED, AuditAction.APPOINTMENT_RESCHEDULED} <= actions
    assert client.get(URL, headers=tenant.act(client, "other_patient")).json() == []
    again = client.post(f"{URL}/offers/{offer['id']}/accept", headers=tenant.act(client, "other_patient"))
    assert again.status_code == 409 and again.json()["detail"] == OFFER_GONE


def test_only_matching_entries_get_offers(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    headers = tenant.act(client, "clinic_admin")
    client.patch(f"/api/v1/scheduling/professionals/{tenant.staff_ids['nurse']}", headers=headers, json={"specialty_id": ids["specialty_id"]})
    client.post(
        f"/api/v1/scheduling/professionals/{tenant.staff_ids['nurse']}/schedule",
        headers=headers,
        json={"rules": [{"weekday": d, "start_time": "09:00", "end_time": "12:00", "appointment_type_ids": [ids["type_id"]]} for d in range(5)]},
    )
    day = next_weekday(3)
    third = _third_patient(client, tenant)
    # other_patient (specialty) and patient (same professional) both wait for later doctor appointments.
    specialty_late = _book(client, tenant.act(client, "other_patient"), ids["type_id"], _at(day, 11), tenant.staff_ids["doctor"])
    professional_late = _book(client, tenant.act(client, "patient"), ids["type_id"], _at(day, 11, 30), tenant.staff_ids["doctor"])
    _join(client, tenant.act(client, "other_patient"), specialty_late["id"], scope="specialty")
    _join(client, tenant.act(client, "patient"), professional_late["id"])

    # A nurse slot frees up: only the specialty entry matches.
    nurse_slot = _book(client, use(client, third["who"]), ids["type_id"], _at(day, 9), tenant.staff_ids["nurse"])
    _cancel(client, use(client, third["who"]), nurse_slot["id"])
    assert len(_offers(client, tenant.act(client, "other_patient"))) == 1
    assert _offers(client, tenant.act(client, "patient")) == []

    # A doctor slot that is LATER than both appointments is offered to nobody.
    after = _book(client, use(client, third["who"]), ids["type_id"], _at(day + timedelta(days=7), 9), tenant.staff_ids["doctor"])
    _cancel(client, use(client, third["who"]), after["id"])
    assert len(_offers(client, tenant.act(client, "other_patient"))) == 1
    assert _offers(client, tenant.act(client, "patient")) == []


def test_the_first_acceptance_wins_and_the_others_change_nothing(client: TestClient, second_client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(4)
    third = _third_patient(client, tenant)
    freed = _book(client, use(client, third["who"]), ids["type_id"], _at(day, 9), tenant.staff_ids["doctor"])
    first_late = _book(client, tenant.act(client, "patient"), ids["type_id"], _at(day, 10), tenant.staff_ids["doctor"])
    second_late = _book(client, tenant.act(client, "other_patient"), ids["type_id"], _at(day, 11), tenant.staff_ids["doctor"])
    _join(client, tenant.act(client, "patient"), first_late["id"])
    _join(client, tenant.act(client, "other_patient"), second_late["id"])
    _cancel(client, use(client, third["who"]), freed["id"])
    [offer_a] = _offers(client, tenant.act(client, "patient"))
    [offer_b] = _offers(client, tenant.act(client, "other_patient"))

    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def accept(test_client: TestClient, who: str, offer_id: str) -> None:
        barrier.wait()
        statuses.append(test_client.post(f"{URL}/offers/{offer_id}/accept", headers=raw_headers(tenant.who[who])).status_code)

    client.cookies.clear()
    threads = [
        threading.Thread(target=accept, args=(client, "patient", offer_a["id"])),
        threading.Thread(target=accept, args=(second_client, "other_patient", offer_b["id"])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert sorted(statuses) == [201, 409]
    with client.session_factory() as db:  # type: ignore[attr-defined]
        at_nine = db.query(Appointment).filter(
            Appointment.clinic_id == uuid.UUID(tenant.clinic_id),
            Appointment.scheduled_at == datetime.fromisoformat(_at(day, 9)),
            Appointment.status.in_((AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)),
        ).count()
        losers_old = [
            db.get(Appointment, uuid.UUID(appointment["id"])).status for appointment in (first_late, second_late)
        ]
    assert at_nine == 1
    assert sorted(status.value for status in losers_old) == ["cancelled", "confirmed"]  # the loser kept theirs


def test_offers_expire_and_entries_close_with_their_appointment(client: TestClient, tenant: Tenant, monkeypatch):
    ids = setup_booking(client, tenant)
    day = next_weekday(1)
    early = _book(client, tenant.act(client, "patient"), ids["type_id"], _at(day, 9), tenant.staff_ids["doctor"])
    late = _book(client, tenant.act(client, "other_patient"), ids["type_id"], _at(day, 11), tenant.staff_ids["doctor"])
    entry = _join(client, tenant.act(client, "other_patient"), late["id"])
    _cancel(client, tenant.act(client, "patient"), early["id"])
    [offer] = _offers(client, tenant.act(client, "other_patient"))

    later = datetime.now(UTC) + timedelta(minutes=61)
    monkeypatch.setattr("app.modules.scheduling.clock.now", lambda: later)
    assert _offers(client, tenant.act(client, "other_patient")) == []
    refused = client.post(f"{URL}/offers/{offer['id']}/accept", headers=tenant.act(client, "other_patient"))
    assert refused.status_code == 409 and refused.json()["detail"] == OFFER_GONE
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert expire_offers(db) >= 1
        assert db.get(WaitlistOffer, uuid.UUID(offer["id"])).status == WaitlistOfferStatus.EXPIRED
    monkeypatch.undo()

    _cancel(client, tenant.act(client, "other_patient"), late["id"])
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.get(WaitlistEntry, uuid.UUID(entry["id"])).status == WaitlistStatus.CLOSED


def test_declining_keeps_the_entry_and_others_cannot_answer(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(2)
    early = _book(client, tenant.act(client, "patient"), ids["type_id"], _at(day, 9), tenant.staff_ids["doctor"])
    late = _book(client, tenant.act(client, "other_patient"), ids["type_id"], _at(day, 11), tenant.staff_ids["doctor"])
    _join(client, tenant.act(client, "other_patient"), late["id"])
    _cancel(client, tenant.act(client, "patient"), early["id"])
    [offer] = _offers(client, tenant.act(client, "other_patient"))
    assert client.post(f"{URL}/offers/{offer['id']}/accept", headers=tenant.act(client, "patient")).status_code == 404
    assert client.post(f"{URL}/offers/{offer['id']}/decline", headers=tenant.act(client, "clinic_admin")).status_code == 403
    assert client.post(f"{URL}/offers/{offer['id']}/decline", headers=tenant.act(client, "other_patient")).status_code == 204
    [entry] = client.get(URL, headers=tenant.act(client, "other_patient")).json()
    assert entry["status"] == "active" and entry["offers"] == []


def test_downgrade_refuses_while_entries_exist(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    booked = _book(client, tenant.act(client, "patient"), ids["type_id"], _at(next_weekday(1), 10), tenant.staff_ids["doctor"])
    _join(client, tenant.act(client, "patient"), booked["id"])
    try:
        with pytest.raises(RuntimeError, match="Refusing to downgrade"):
            command.downgrade(alembic_config(), "9a4c6e8f0b2d")
    finally:
        command.upgrade(alembic_config(), "head")
