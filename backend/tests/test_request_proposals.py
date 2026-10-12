"""Scheduling, step 5: requests with preferences, the clinic's proposals and reschedule requests.

- A patient asks for a "request only" type with a preference window (dates, weekdays,
  morning/afternoon) and optionally a professional; everything is re-checked by the server.
- The clinic accepts (books) or proposes a time; the patient accepts (books now) or declines.
- A proposal does not hold the slot: if it was taken before the answer, the acceptance is
  refused, the proposal cleared and the request goes back to the clinic.
- A reschedule request moves one of the patient's appointments; accepting it cancels the
  old one in the same transaction.
Synthetic data only.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import (
    Appointment,
    AppointmentRequest,
    AppointmentStatus,
    AuditAction,
    AuditLog,
    BookingSource,
    ClinicalCareAssignment,
    Notification,
)
from app.modules.appointment_requests.service import PROPOSAL_TAKEN
from tests.clinical_support import Tenant, make_tenant
from tests.scheduling_support import setup_booking

URL = "/api/v1/appointment-requests"


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"proposal-{uuid.uuid4().hex[:8]}")


def _window(days: int = 3) -> dict:
    start = date.today() + timedelta(days=days)
    return {"preferred_from": str(start), "preferred_to": str(start + timedelta(days=7))}


def _ask(client: TestClient, tenant: Tenant, who: str = "other_patient", **body) -> dict:
    response = client.post(URL, headers=tenant.act(client, who), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _future(days: int = 10, hour: int = 9) -> str:
    day = datetime.now(UTC).date() + timedelta(days=days)
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC).isoformat()


def _propose(client: TestClient, tenant: Tenant, request_id: str, at: str, staff: str = "doctor"):
    return client.post(
        f"{URL}/{request_id}/propose", headers=tenant.act(client, "clinic_admin"), json={"staff_id": tenant.staff_ids[staff], "scheduled_at": at}
    )


def _titles(client: TestClient, user_id: str) -> list[str]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return [row.title for row in db.query(Notification).filter_by(user_id=uuid.UUID(user_id))]


def _audit(client: TestClient, action: AuditAction) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(AuditLog).filter(AuditLog.action == action).all()


def test_a_request_with_preferences_is_validated_by_the_server(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant, mode="request")
    body = {"appointment_type_id": ids["type_id"], **_window(), "preferred_weekdays": [2, 0, 2], "preferred_period": "morning"}
    created = _ask(client, tenant, reason="Dor lombar", staff_id=tenant.staff_ids["doctor"], **body)
    assert created["status"] == "pending"
    assert (created["appointment_type"], created["specialty"]) == ("Consulta de rotina", "Medicina Geral")
    assert created["preferred_weekdays"] == [0, 2] and created["preferred_period"] == "morning"
    assert created["staff_name"] and created["staff_id"] is None  # names only for the patient
    assert "Novo pedido de consulta" in _titles(client, tenant.user_ids["clinic_admin"])

    headers = tenant.act(client, "other_patient")
    today = date.today()
    invalid = [
        {**body, "preferred_from": str(today - timedelta(days=1))},
        {**body, "preferred_to": str(today)},  # before preferred_from
        {**body, "preferred_weekdays": [7]},
        {**body, "preferred_start": _future()},
        {**body, "preferred_from": str(today + timedelta(days=200)), "preferred_to": None},  # beyond the horizon
        {"preferred_from": str(today + timedelta(days=3)), "staff_id": tenant.staff_ids["doctor"]},  # professional without type
    ]
    for payload in invalid:
        assert client.post(URL, headers=headers, json=payload).status_code == 422, payload
    # The nurse has no specialty for this type: not a professional the patient may ask for.
    assert client.post(URL, headers=headers, json={**body, "staff_id": tenant.staff_ids["nurse"]}).status_code == 404
    # A direct type is booked on a free slot, not requested.
    client.patch(
        f"/api/v1/scheduling/appointment-types/{ids['type_id']}", headers=tenant.act(client, "clinic_admin"), json={"booking_mode": "direct"}
    )
    assert client.post(URL, headers=tenant.act(client, "other_patient"), json=body).status_code == 422


def test_the_patient_accepts_a_proposal_and_the_appointment_is_booked(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant, mode="request")
    created = _ask(client, tenant, appointment_type_id=ids["type_id"], reason="Controlo", **_window())
    at = _future()
    proposed = _propose(client, tenant, created["id"], at)
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["status"] == "proposed" and proposed.json()["proposed_staff_id"] == tenant.staff_ids["doctor"]
    assert proposed.json()["proposed_duration_minutes"] == 30  # the type's duration
    assert "Proposta de horário" in _titles(client, tenant.user_ids["other_patient"])

    tenant.act(client, "other_patient")
    [mine] = client.get(URL).json()
    assert mine["status"] == "proposed" and mine["proposed_staff_name"] and mine["proposed_staff_id"] is None
    accepted = client.post(f"{URL}/{created['id']}/accept-proposal", headers=tenant.act(client, "other_patient"))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted" and accepted.json()["appointment_id"]

    with client.session_factory() as db:  # type: ignore[attr-defined]
        appointment = db.get(Appointment, uuid.UUID(accepted.json()["appointment_id"]))
        assert appointment.booked_via == BookingSource.REQUEST
        assert str(appointment.appointment_type_id) == ids["type_id"] and appointment.reason == "Controlo"
        link = db.query(ClinicalCareAssignment).filter_by(patient_id=uuid.UUID(tenant.other_patient_id), active=True).one()
        assert link.origin_appointment_id == appointment.id
    assert "Resposta a uma proposta" in _titles(client, tenant.user_ids["clinic_admin"])
    [audit] = _audit(client, AuditAction.APPOINTMENT_REQUEST_PROPOSAL_ACCEPTED)
    assert "Controlo" not in str(audit.event_metadata)
    # Answered once only.
    assert client.post(f"{URL}/{created['id']}/accept-proposal", headers=tenant.act(client, "other_patient")).status_code == 409


def test_a_proposed_slot_taken_meanwhile_sends_the_request_back_to_the_clinic(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant, mode="request")
    created = _ask(client, tenant, appointment_type_id=ids["type_id"], **_window())
    at = _future(days=11)
    assert _propose(client, tenant, created["id"], at).status_code == 200
    # Proposing a time that is already taken is refused at once.
    taken = client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "admin"),
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": at},
    )
    assert taken.status_code == 201

    refused = client.post(f"{URL}/{created['id']}/accept-proposal", headers=tenant.act(client, "other_patient"))
    assert refused.status_code == 409 and refused.json()["detail"] == PROPOSAL_TAKEN
    with client.session_factory() as db:  # type: ignore[attr-defined]
        request = db.get(AppointmentRequest, uuid.UUID(created["id"]))
        assert request.status.value == "pending" and request.proposed_start is None and request.appointment_id is None
        assert db.query(Appointment).filter_by(patient_id=uuid.UUID(tenant.other_patient_id)).count() == 0
    assert "Pedido de consulta reaberto" in _titles(client, tenant.user_ids["clinic_admin"])
    again = _propose(client, tenant, created["id"], at)
    assert again.status_code == 409  # still taken


def test_the_patient_declines_or_withdraws_and_the_clinic_withdraws(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant, mode="request")
    first = _ask(client, tenant, appointment_type_id=ids["type_id"], **_window())
    assert _propose(client, tenant, first["id"], _future()).status_code == 200
    declined = client.post(f"{URL}/{first['id']}/decline-proposal", headers=tenant.act(client, "other_patient"))
    assert declined.status_code == 200 and declined.json()["status"] == "declined"
    assert client.post(f"{URL}/{first['id']}/accept-proposal", headers=tenant.act(client, "other_patient")).status_code == 409
    assert _propose(client, tenant, first["id"], _future()).status_code == 409

    second = _ask(client, tenant, appointment_type_id=ids["type_id"], **_window())
    assert _propose(client, tenant, second["id"], _future(hour=10)).status_code == 200
    withdrawn = client.post(f"{URL}/{second['id']}/reject", headers=tenant.act(client, "clinic_admin"))
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "rejected"

    third = _ask(client, tenant, appointment_type_id=ids["type_id"], **_window())
    assert _propose(client, tenant, third["id"], _future(hour=11)).status_code == 200
    cancelled = client.post(f"{URL}/{third['id']}/cancel", headers=tenant.act(client, "other_patient"))
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert len(_audit(client, AuditAction.APPOINTMENT_REQUEST_PROPOSAL_DECLINED)) == 1


def test_a_reschedule_request_moves_the_appointment_when_accepted(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant, mode="request")
    first = _ask(client, tenant, appointment_type_id=ids["type_id"], reason="Seguimento", **_window())
    old_start = datetime.fromisoformat(_future(days=12))
    booked = client.post(
        f"{URL}/{first['id']}/accept",
        headers=tenant.act(client, "clinic_admin"),
        json={"staff_id": tenant.staff_ids["doctor"], "scheduled_at": old_start.isoformat()},
    )
    assert booked.status_code == 200, booked.text
    old_id = booked.json()["appointment_id"]
    tenant.act(client, "other_patient")
    assert client.get(f"/api/v1/appointments/{old_id}").json()["booking_mode"] == "request"

    move = _ask(client, tenant, reschedule_of_id=old_id, **_window(days=5))
    assert move["reschedule_of_id"] == old_id and move["reschedule_of_start"]
    assert move["appointment_type"] == "Consulta de rotina" and move["reason"] == "Seguimento"
    duplicate = client.post(URL, headers=tenant.act(client, "other_patient"), json={"reschedule_of_id": old_id, **_window(days=6)})
    assert duplicate.status_code == 409
    with_type = client.post(
        URL, headers=tenant.act(client, "other_patient"),
        json={"reschedule_of_id": old_id, "appointment_type_id": ids["type_id"], **_window(days=6)},
    )
    assert with_type.status_code == 422

    # The new time overlaps the old one: allowed, the old one is freed first.
    accepted = client.post(
        f"{URL}/{move['id']}/accept",
        headers=tenant.act(client, "clinic_admin"),
        json={"staff_id": tenant.staff_ids["doctor"], "scheduled_at": (old_start + timedelta(minutes=15)).isoformat()},
    )
    assert accepted.status_code == 200, accepted.text
    with client.session_factory() as db:  # type: ignore[attr-defined]
        old = db.get(Appointment, uuid.UUID(old_id))
        new = db.get(Appointment, uuid.UUID(accepted.json()["appointment_id"]))
        assert old.status == AppointmentStatus.CANCELLED and old.cancelled_by_user_id == uuid.UUID(tenant.user_ids["clinic_admin"])
        assert new.rescheduled_from_id == old.id and str(new.appointment_type_id) == ids["type_id"]
        [link] = db.query(ClinicalCareAssignment).filter_by(patient_id=uuid.UUID(tenant.other_patient_id)).all()
        assert link.active and link.origin_appointment_id == new.id
    [audit] = _audit(client, AuditAction.APPOINTMENT_RESCHEDULED)
    assert audit.resource_id == uuid.UUID(old_id)


def test_reschedule_requests_respect_the_deadline_and_ownership(client: TestClient, tenant: Tenant, monkeypatch):
    created = client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "admin"),
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": _future(days=4)},
    )
    appointment_id = created.json()["id"]
    assert client.post(URL, headers=tenant.act(client, "other_patient"), json={"reschedule_of_id": appointment_id, **_window()}).status_code == 404
    start = datetime.fromisoformat(created.json()["scheduled_at"].replace("Z", "+00:00"))
    monkeypatch.setattr("app.modules.scheduling.clock.now", lambda: start - timedelta(hours=2))
    late = client.post(URL, headers=tenant.act(client, "patient"), json={"reschedule_of_id": appointment_id, **_window(days=1)})
    assert late.status_code == 409


def test_proposal_permissions(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant, mode="request")
    created = _ask(client, tenant, appointment_type_id=ids["type_id"], **_window())
    body = {"staff_id": tenant.staff_ids["doctor"], "scheduled_at": _future()}
    assert client.post(f"{URL}/{created['id']}/propose", headers=tenant.act(client, "other_patient"), json=body).status_code == 403
    # A clinician outside the patient's care team may not decide on it.
    assert client.post(f"{URL}/{created['id']}/propose", headers=tenant.act(client, "doctor"), json=body).status_code == 403
    other = make_tenant(client, f"proposal-other-{uuid.uuid4().hex[:6]}")
    assert client.post(f"{URL}/{created['id']}/propose", headers=other.act(client, "clinic_admin"), json=body).status_code == 404
    # A non-clinical professional is never proposed.
    admin_staff = client.post(
        f"{URL}/{created['id']}/propose", headers=tenant.act(client, "clinic_admin"), json={**body, "staff_id": tenant.staff_ids["admin"]}
    )
    assert admin_staff.status_code == 422

    assert _propose(client, tenant, created["id"], body["scheduled_at"]).status_code == 200
    for actor, role in ((tenant, "clinic_admin"), (tenant, "patient"), (other, "other_patient")):
        headers = actor.act(client, role)
        expected = 403 if role == "clinic_admin" else 404
        assert client.post(f"{URL}/{created['id']}/accept-proposal", headers=headers).status_code == expected, role
        assert client.post(f"{URL}/{created['id']}/decline-proposal", headers=headers).status_code == expected, role
