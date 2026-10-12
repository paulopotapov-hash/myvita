"""Scheduling, step 5: a patient cancels or reschedules their own appointment.

- Allowed while active and before the clinic's deadline (real hours, also across the
  daylight-saving change); after it, 409 and the app points to the clinic.
- Cancelling frees the slot at once and ends the care link the booking created.
- Rescheduling cancels and books in one transaction: a slot taken meanwhile changes
  nothing; the care link moves with the appointment.
- Only the patient's own appointments; direct types only (request types ask the clinic).
Synthetic data only.
"""

import threading
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.models import (
    Appointment,
    AppointmentStatus,
    AuditAction,
    AuditLog,
    ClinicalCareAssignment,
    Notification,
)
from app.modules.scheduling.changes import DEADLINE_PASSED, NOT_ACTIVE, REQUEST_ONLY
from tests.clinical_support import Tenant, make_tenant, raw_headers
from tests.scheduling_support import next_weekday, setup_booking


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"change-{uuid.uuid4().hex[:8]}")


def _slots(client: TestClient, type_id: str, day, staff_id: str | None = None) -> list[dict]:
    url = f"/api/v1/scheduling/slots?appointment_type_id={type_id}&from={day}&to={day}"
    return client.get(url + (f"&staff_id={staff_id}" if staff_id else "")).json()


def _book(client: TestClient, tenant: Tenant, who: str, type_id: str, starts_at: str, staff: str = "doctor") -> dict:
    response = client.post(
        "/api/v1/scheduling/bookings",
        headers=tenant.act(client, who),
        json={"appointment_type_id": type_id, "staff_id": tenant.staff_ids[staff], "starts_at": starts_at},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _at(day, hour: int, minute: int = 0) -> str:
    """A slot start in Lisbon wall-clock time, as the API returns it (UTC)."""
    from zoneinfo import ZoneInfo

    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo("Europe/Lisbon")).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _same(a: str, b: str) -> bool:
    return datetime.fromisoformat(a.replace("Z", "+00:00")) == datetime.fromisoformat(b.replace("Z", "+00:00"))


def _audit(client: TestClient, action: AuditAction) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(AuditLog).filter(AuditLog.action == action).order_by(AuditLog.timestamp).all()


def _add_nurse(client: TestClient, tenant: Tenant, ids: dict) -> None:
    headers = tenant.act(client, "clinic_admin")
    assert client.patch(
        f"/api/v1/scheduling/professionals/{tenant.staff_ids['nurse']}", headers=headers, json={"specialty_id": ids["specialty_id"]}
    ).status_code == 200
    assert client.post(
        f"/api/v1/scheduling/professionals/{tenant.staff_ids['nurse']}/schedule",
        headers=headers,
        json={"rules": [{"weekday": d, "start_time": "09:00", "end_time": "12:00", "appointment_type_ids": [ids["type_id"]]} for d in range(5)]},
    ).status_code == 200


def test_patient_cancels_before_the_deadline_and_the_slot_is_free_again(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(1)
    booked = _book(client, tenant, "other_patient", ids["type_id"], _at(day, 9))
    assert booked["can_change"] is True and booked["booking_mode"] == "direct"
    deadline = datetime.fromisoformat(booked["change_until"].replace("Z", "+00:00"))
    assert (datetime.fromisoformat(booked["scheduled_at"].replace("Z", "+00:00")) - deadline).total_seconds() == 24 * 3600

    cancelled = client.post(f"/api/v1/scheduling/bookings/{booked['id']}/cancel", headers=tenant.act(client, "other_patient"))
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled" and cancelled.json()["can_change"] is False
    assert any(_same(row["starts_at"], booked["scheduled_at"]) for row in _slots(client, ids["type_id"], day))

    with client.session_factory() as db:  # type: ignore[attr-defined]
        appointment = db.get(Appointment, uuid.UUID(booked["id"]))
        assert appointment.cancelled_by_user_id == uuid.UUID(tenant.user_ids["other_patient"]) and appointment.cancelled_at
        link = db.query(ClinicalCareAssignment).filter_by(patient_id=uuid.UUID(tenant.other_patient_id)).one()
        assert not link.active
        doctor_titles = [n.title for n in db.query(Notification).filter_by(user_id=uuid.UUID(tenant.user_ids["doctor"]))]
    assert "Consulta cancelada" in doctor_titles
    [audit] = [row for row in _audit(client, AuditAction.APPOINTMENT_CANCELLED) if row.resource_id == uuid.UUID(booked["id"])]
    assert audit.event_metadata["via"] == "patient"
    assert len(_audit(client, AuditAction.CARE_ASSIGNMENT_ENDED)) == 1

    again = client.post(f"/api/v1/scheduling/bookings/{booked['id']}/cancel", headers=tenant.act(client, "other_patient"))
    assert again.status_code == 409 and again.json()["detail"] == NOT_ACTIVE


def test_the_deadline_counts_real_hours_across_the_clock_change(client: TestClient, tenant: Tenant, monkeypatch):
    # Sunday 2030-03-31 is when Lisbon moves to summer time (01:00 UTC). 10:00 WEST = 09:00 UTC.
    created = client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "admin"),
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": "2030-03-31T09:00:00Z"},
    )
    assert created.status_code == 201, created.text
    appointment_id = created.json()["id"]
    headers = tenant.act(client, "patient")
    view = client.get(f"/api/v1/appointments/{appointment_id}").json()
    # 24 real hours before: Saturday 09:00 UTC, which is 09:00 in Lisbon (winter time), not 10:00.
    assert _same(view["change_until"], "2030-03-30T09:00:00Z")

    monkeypatch.setattr("app.modules.scheduling.clock.now", lambda: datetime(2030, 3, 30, 9, 0, tzinfo=UTC))
    assert client.get(f"/api/v1/appointments/{appointment_id}").json()["can_change"] is False
    late = client.post(f"/api/v1/scheduling/bookings/{appointment_id}/cancel", headers=headers)
    assert late.status_code == 409 and late.json()["detail"] == DEADLINE_PASSED

    monkeypatch.setattr("app.modules.scheduling.clock.now", lambda: datetime(2030, 3, 30, 8, 59, 59, tzinfo=UTC))
    assert client.get(f"/api/v1/appointments/{appointment_id}").json()["can_change"] is True
    assert client.post(f"/api/v1/scheduling/bookings/{appointment_id}/cancel", headers=headers).status_code == 200


def test_the_deadline_follows_the_clinic_setting(client: TestClient, tenant: Tenant, monkeypatch):
    ids = setup_booking(client, tenant)
    day = next_weekday(2)
    booked = _book(client, tenant, "patient", ids["type_id"], _at(day, 10))
    start = datetime.fromisoformat(booked["scheduled_at"].replace("Z", "+00:00"))
    assert client.patch(
        "/api/v1/scheduling/settings", headers=tenant.act(client, "clinic_admin"), json={
            "cancellation_deadline_hours": 48, "waitlist_offer_minutes": 60, "reminder_hours_before": 24, "booking_horizon_days": 90,
        },
    ).status_code == 200
    from datetime import timedelta

    monkeypatch.setattr("app.modules.scheduling.clock.now", lambda: start - timedelta(hours=47))
    headers = tenant.act(client, "patient")
    assert client.get(f"/api/v1/appointments/{booked['id']}").json()["can_change"] is False
    refused = client.post(
        f"/api/v1/scheduling/bookings/{booked['id']}/reschedule", headers=headers, json={"starts_at": _at(day, 11)}
    )
    assert refused.status_code == 409 and refused.json()["detail"] == DEADLINE_PASSED


def test_reschedule_with_the_same_professional_moves_the_appointment_and_its_link(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(1)
    old = _book(client, tenant, "other_patient", ids["type_id"], _at(day, 9))
    headers = tenant.act(client, "other_patient")
    offered = client.get(f"/api/v1/scheduling/bookings/{old['id']}/slots?from={day}&to={day}&professional=same").json()
    assert offered and all(row["staff_id"] == tenant.staff_ids["doctor"] for row in offered)
    assert not any(_same(row["starts_at"], old["scheduled_at"]) for row in offered)

    moved = client.post(f"/api/v1/scheduling/bookings/{old['id']}/reschedule", headers=headers, json={"starts_at": _at(day, 10)})
    assert moved.status_code == 201, moved.text
    new = moved.json()
    assert new["id"] != old["id"] and new["status"] == "confirmed" and _same(new["scheduled_at"], _at(day, 10))
    assert client.get(f"/api/v1/appointments/{old['id']}").json()["status"] == "cancelled"
    assert any(_same(row["starts_at"], _at(day, 9)) for row in _slots(client, ids["type_id"], day))

    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.get(Appointment, uuid.UUID(new["id"])).rescheduled_from_id == uuid.UUID(old["id"])
        [link] = db.query(ClinicalCareAssignment).filter_by(patient_id=uuid.UUID(tenant.other_patient_id)).all()
        assert link.active and link.origin_appointment_id == uuid.UUID(new["id"])
    assert _audit(client, AuditAction.CARE_ASSIGNMENT_ENDED) == []
    [audit] = _audit(client, AuditAction.APPOINTMENT_RESCHEDULED)
    assert audit.resource_id == uuid.UUID(old["id"]) and audit.event_metadata == {"new_appointment_id": new["id"]}


def test_reschedule_to_another_professional_moves_the_care_link(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    _add_nurse(client, tenant, ids)
    day = next_weekday(2)
    old = _book(client, tenant, "other_patient", ids["type_id"], _at(day, 9))
    headers = tenant.act(client, "other_patient")
    any_slots = client.get(f"/api/v1/scheduling/bookings/{old['id']}/slots?from={day}&to={day}&professional=any").json()
    assert {row["staff_id"] for row in any_slots} == {tenant.staff_ids["doctor"], tenant.staff_ids["nurse"]}

    moved = client.post(
        f"/api/v1/scheduling/bookings/{old['id']}/reschedule",
        headers=headers,
        json={"starts_at": _at(day, 9), "staff_id": tenant.staff_ids["nurse"]},
    )
    assert moved.status_code == 201, moved.text
    with client.session_factory() as db:  # type: ignore[attr-defined]
        links = {
            str(row.staff_id): row
            for row in db.query(ClinicalCareAssignment).filter_by(patient_id=uuid.UUID(tenant.other_patient_id))
        }
    assert not links[tenant.staff_ids["doctor"]].active
    assert links[tenant.staff_ids["nurse"]].active
    assert links[tenant.staff_ids["nurse"]].origin_appointment_id == uuid.UUID(moved.json()["id"])
    [ended] = _audit(client, AuditAction.CARE_ASSIGNMENT_ENDED)
    assert ended.event_metadata["via"] == "appointment_moved"


def test_a_slot_taken_meanwhile_leaves_the_old_appointment_untouched(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(3)
    old = _book(client, tenant, "other_patient", ids["type_id"], _at(day, 9))
    _book(client, tenant, "patient", ids["type_id"], _at(day, 10))
    refused = client.post(
        f"/api/v1/scheduling/bookings/{old['id']}/reschedule", headers=tenant.act(client, "other_patient"), json={"starts_at": _at(day, 10)}
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == "Este horário já não está disponível. Escolhe outro."
    with client.session_factory() as db:  # type: ignore[attr-defined]
        appointment = db.get(Appointment, uuid.UUID(old["id"]))
        assert appointment.status == AppointmentStatus.CONFIRMED and appointment.cancelled_at is None
        assert db.query(Appointment).filter_by(rescheduled_from_id=appointment.id).count() == 0
        [link] = db.query(ClinicalCareAssignment).filter_by(patient_id=uuid.UUID(tenant.other_patient_id)).all()
        assert link.active and link.origin_appointment_id == appointment.id


def test_concurrent_reschedules_to_the_same_slot_book_it_once(client: TestClient, second_client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(4)
    first = _book(client, tenant, "patient", ids["type_id"], _at(day, 9))
    second = _book(client, tenant, "other_patient", ids["type_id"], _at(day, 9, 30))
    target = _at(day, 11)
    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def move(test_client: TestClient, who: str, appointment_id: str) -> None:
        barrier.wait()
        statuses.append(
            test_client.post(
                f"/api/v1/scheduling/bookings/{appointment_id}/reschedule", headers=raw_headers(tenant.who[who]), json={"starts_at": target}
            ).status_code
        )

    client.cookies.clear()
    threads = [
        threading.Thread(target=move, args=(client, "patient", first["id"])),
        threading.Thread(target=move, args=(second_client, "other_patient", second["id"])),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert sorted(statuses) == [201, 409]
    with client.session_factory() as db:  # type: ignore[attr-defined]
        active = db.query(Appointment).filter(
            Appointment.clinic_id == uuid.UUID(tenant.clinic_id),
            Appointment.status.in_((AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)),
        ).count()
    assert active == 2  # one moved, the other kept its time


def test_untyped_and_request_only_appointments_are_not_moved_directly(client: TestClient, tenant: Tenant):
    created = client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "admin"),
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": "2030-05-06T09:00:00Z"},
    )
    appointment_id = created.json()["id"]
    headers = tenant.act(client, "patient")
    assert client.get(f"/api/v1/appointments/{appointment_id}").json()["booking_mode"] is None
    moved = client.post(
        f"/api/v1/scheduling/bookings/{appointment_id}/reschedule", headers=headers, json={"starts_at": "2030-05-07T09:00:00Z"}
    )
    assert moved.status_code == 422 and moved.json()["detail"] == REQUEST_ONLY
    slots = client.get(f"/api/v1/scheduling/bookings/{appointment_id}/slots?from=2030-05-07&to=2030-05-07")
    assert slots.status_code == 422
    # Cancelling is still allowed.
    assert client.post(f"/api/v1/scheduling/bookings/{appointment_id}/cancel", headers=headers).status_code == 200


def test_only_the_patient_changes_their_own_appointment(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    day = next_weekday(1)
    booked = _book(client, tenant, "patient", ids["type_id"], _at(day, 9))
    other = make_tenant(client, f"change-other-{uuid.uuid4().hex[:6]}")
    paths = [
        ("post", f"/api/v1/scheduling/bookings/{booked['id']}/cancel", None),
        ("post", f"/api/v1/scheduling/bookings/{booked['id']}/reschedule", {"starts_at": _at(day, 10)}),
        ("get", f"/api/v1/scheduling/bookings/{booked['id']}/slots?from={day}&to={day}", None),
    ]
    for actor, expected in ((tenant, "other_patient"), (other, "patient")):
        headers = actor.act(client, expected)
        for method, path, body in paths:
            response = getattr(client, method)(path, headers=headers, **({"json": body} if body else {}))
            assert response.status_code == 404, (expected, path)
    for role in ("doctor", "clinic_admin"):
        headers = tenant.act(client, role)
        for method, path, body in paths:
            response = getattr(client, method)(path, headers=headers, **({"json": body} if body else {}))
            assert response.status_code == 403, (role, path)
    tenant.act(client, "patient")
    assert client.get(f"/api/v1/appointments/{booked['id']}").json()["status"] == "confirmed"
