"""Scheduling, step 7: reminders, the patient's confirmation and the background job.

- One in-app reminder per appointment, inside the clinic's reminder window, linked to the
  appointment, with generic text only; running the job again sends nothing new.
- Only one runner works at a time (advisory lock); the job also expires waiting-list
  offers and closes entries whose appointment has passed.
- The patient confirms they will come; staff see it.
Synthetic data only.
"""

import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.jobs import LOCK_KEY, run_once
from app.models import (
    Notification,
    ReminderChannel,
    ReminderDelivery,
    WaitlistEntry,
    WaitlistOffer,
    WaitlistOfferStatus,
    WaitlistStatus,
)
from tests.clinical_support import Tenant, make_tenant
from tests.conftest import TEST_DATABASE_URL
from tests.scheduling_support import next_weekday, setup_booking


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"remind-{uuid.uuid4().hex[:8]}")


def _create(client: TestClient, tenant: Tenant, hours_ahead: float, patient: str | None = None, reason: str | None = None) -> str:
    at = (datetime.now(UTC) + timedelta(hours=hours_ahead)).replace(second=0, microsecond=0)
    body = {"patient_id": patient or tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": at.isoformat()}
    # Only clinicians may record a reason: the patient's doctor books those.
    headers = tenant.act(client, "doctor" if reason else "admin")
    response = client.post("/api/v1/appointments", headers=headers, json={**body, **({"reason": reason} if reason else {})})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _run(client: TestClient):
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return run_once(db)


def _reminders(client: TestClient, user_id: str) -> list[Notification]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(Notification).filter_by(user_id=uuid.UUID(user_id), title="Lembrete de consulta").all()


def test_one_reminder_per_appointment_inside_the_clinic_window(client: TestClient, tenant: Tenant):
    due = _create(client, tenant, 20, reason="Dor torácica")
    later = _create(client, tenant, 30)
    cancelled = _create(client, tenant, 10, patient=tenant.other_patient_id)
    assert client.post(f"/api/v1/appointments/{cancelled}/cancel", headers=tenant.act(client, "admin")).status_code == 200

    first = _run(client)
    assert first.ran and first.reminders == 1
    [reminder] = _reminders(client, tenant.user_ids["patient"])
    assert str(reminder.appointment_target_id) == due and reminder.target_type == "appointment"
    assert "Dor" not in reminder.message and "Dor" not in reminder.title  # generic text only
    assert _reminders(client, tenant.user_ids["other_patient"]) == []
    with client.session_factory() as db:  # type: ignore[attr-defined]
        [delivery] = db.query(ReminderDelivery).filter_by(appointment_id=uuid.UUID(due)).all()
        assert delivery.channel == ReminderChannel.IN_APP
        # Email and SMS are prepared but not active: nothing else is attempted or recorded.
        assert db.query(ReminderDelivery).filter(ReminderDelivery.channel != ReminderChannel.IN_APP).count() == 0

    assert _run(client).reminders == 0  # idempotent
    # The patient's notification links to the appointment.
    tenant.act(client, "patient")
    [listed] = [row for row in client.get("/api/v1/notifications").json() if row["title"] == "Lembrete de consulta"]
    assert listed["appointment_target_id"] == due

    # A clinic that reminds 48 hours ahead also reminds the later one.
    assert client.patch(
        "/api/v1/scheduling/settings",
        headers=tenant.act(client, "clinic_admin"),
        json={"cancellation_deadline_hours": 24, "waitlist_offer_minutes": 60, "reminder_hours_before": 48, "booking_horizon_days": 90},
    ).status_code == 200
    assert _run(client).reminders == 1
    assert {str(row.appointment_target_id) for row in _reminders(client, tenant.user_ids["patient"])} == {due, later}


def test_only_one_runner_works_at_a_time(client: TestClient, tenant: Tenant):
    _create(client, tenant, 5)
    holder = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with holder.connect() as connection:
            assert connection.execute(text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"), {"key": LOCK_KEY}).scalar_one()
            assert _run(client).ran is False
            assert _reminders(client, tenant.user_ids["patient"]) == []
            connection.execute(text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), {"key": LOCK_KEY})
        assert _run(client).reminders == 1
    finally:
        holder.dispose()


def test_the_job_expires_offers_and_closes_past_entries(client: TestClient, tenant: Tenant, monkeypatch):
    ids = setup_booking(client, tenant)
    day = next_weekday(1)
    tenant.act(client, "patient")
    slots = client.get(f"/api/v1/scheduling/slots?appointment_type_id={ids['type_id']}&from={day}&to={day}").json()
    def book(who: str, slot: dict) -> str:
        response = client.post(
            "/api/v1/scheduling/bookings",
            headers=tenant.act(client, who),
            json={"appointment_type_id": ids["type_id"], "staff_id": tenant.staff_ids["doctor"], "starts_at": slot["starts_at"]},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    early = book("patient", slots[0])
    late = book("other_patient", slots[3])
    entry = client.post("/api/v1/waitlist", headers=tenant.act(client, "other_patient"), json={"appointment_id": late}).json()
    assert client.post(f"/api/v1/scheduling/bookings/{early}/cancel", headers=tenant.act(client, "patient")).status_code == 200

    monkeypatch.setattr("app.modules.scheduling.clock.now", lambda: datetime.now(UTC) + timedelta(minutes=90))
    assert _run(client).expired_offers == 1
    start = datetime.fromisoformat(slots[3]["starts_at"])
    monkeypatch.setattr("app.modules.scheduling.clock.now", lambda: start + timedelta(minutes=1))
    assert _run(client).closed_entries == 1
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.get(WaitlistEntry, uuid.UUID(entry["id"])).status == WaitlistStatus.CLOSED
        assert db.query(WaitlistOffer).filter_by(entry_id=uuid.UUID(entry["id"])).one().status == WaitlistOfferStatus.EXPIRED


def test_the_patient_confirms_and_staff_see_it(client: TestClient, tenant: Tenant):
    appointment_id = _create(client, tenant, 20)
    tenant.act(client, "patient")
    view = client.get(f"/api/v1/appointments/{appointment_id}").json()
    assert (view["can_confirm"], view["patient_confirmed_at"]) == (True, None)
    assert client.post(f"/api/v1/scheduling/bookings/{appointment_id}/confirm", headers=tenant.act(client, "other_patient")).status_code == 404
    assert client.post(f"/api/v1/scheduling/bookings/{appointment_id}/confirm", headers=tenant.act(client, "doctor")).status_code == 403

    confirmed = client.post(f"/api/v1/scheduling/bookings/{appointment_id}/confirm", headers=tenant.act(client, "patient"))
    assert confirmed.status_code == 200 and confirmed.json()["patient_confirmed_at"] and confirmed.json()["can_confirm"] is False
    again = client.post(f"/api/v1/scheduling/bookings/{appointment_id}/confirm", headers=tenant.act(client, "patient"))
    assert again.status_code == 200 and again.json()["patient_confirmed_at"] == confirmed.json()["patient_confirmed_at"]

    tenant.act(client, "clinic_admin")
    assert client.get(f"/api/v1/appointments/{appointment_id}").json()["patient_confirmed_at"]
    day = datetime.fromisoformat(confirmed.json()["scheduled_at"].replace("Z", "+00:00")).date()
    agenda = client.get(f"/api/v1/scheduling/agenda?from={day - timedelta(days=1)}&to={day + timedelta(days=1)}&staff_id={tenant.staff_ids['doctor']}")
    assert any(row["id"] == appointment_id and row["patient_confirmed"] for row in agenda.json()["appointments"])

    assert client.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=tenant.act(client, "admin")).status_code == 200
    late = client.post(f"/api/v1/scheduling/bookings/{appointment_id}/confirm", headers=tenant.act(client, "patient"))
    assert late.status_code == 409


def test_the_command_runs_one_pass(client: TestClient, tenant: Tenant):
    _create(client, tenant, 3)
    backend = Path(__file__).resolve().parents[1]
    done = subprocess.run(
        [sys.executable, "-m", "app.jobs", "--once"],
        cwd=backend,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    assert "scheduling_jobs reminders=1" in done.stderr
    assert len(_reminders(client, tenant.user_ids["patient"])) == 1
