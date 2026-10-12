"""Scheduling, step 3: configuration, weekly schedules, absences, free slots, database-level
double-booking protection (also under concurrency), automatic care-team assignment, tenant
isolation and audit. Synthetic data only."""

import threading
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    AppointmentType,
    AuditAction,
    AuditLog,
    BookingMode,
    ClinicalCareAssignment,
    ScheduleAbsence,
    ScheduleRule,
    ScheduleRuleType,
)
from app.modules.scheduling.availability import free_slots
from tests.clinical_support import Tenant, make_tenant
from tests.conftest import TEST_DATABASE_URL
from tests.scheduling_support import next_weekday, setup_booking

LISBON = ZoneInfo("Europe/Lisbon")


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"sched-{uuid.uuid4().hex[:8]}")


def _audit(client: TestClient, action: AuditAction) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(AuditLog).filter(AuditLog.action == action).all()


# --- configuration permissions ------------------------------------------------------------------


def test_only_schedulers_configure_and_everyone_in_the_clinic_reads(client: TestClient, tenant: Tenant):
    other = make_tenant(client, f"sched-other-{uuid.uuid4().hex[:8]}")
    for role in ("clinic_admin", "admin"):
        response = client.post("/api/v1/scheduling/specialties", headers=tenant.act(client, role), json={"name": f"Esp {role}"})
        assert response.status_code == 201, (role, response.text)
    for role in ("doctor", "nurse", "physiotherapist", "patient"):
        response = client.post("/api/v1/scheduling/specialties", headers=tenant.act(client, role), json={"name": f"X {role}"})
        assert response.status_code == 403, role
        assert client.patch(
            "/api/v1/scheduling/settings",
            headers=tenant.act(client, role),
            json={"cancellation_deadline_hours": 1, "waitlist_offer_minutes": 10, "reminder_hours_before": 2, "booking_horizon_days": 30},
        ).status_code == 403

    duplicate = client.post("/api/v1/scheduling/specialties", headers=tenant.act(client, "clinic_admin"), json={"name": "esp CLINIC_ADMIN"})
    assert duplicate.status_code == 409

    specialty_id = client.get("/api/v1/scheduling/specialties", headers=tenant.act(client, "patient")).json()[0]["id"]
    # Another clinic cannot see or change it.
    headers = other.act(client, "clinic_admin")
    assert client.patch(f"/api/v1/scheduling/specialties/{specialty_id}", headers=headers, json={"active": False}).status_code == 404
    assert all(row["id"] != specialty_id for row in client.get("/api/v1/scheduling/specialties").json())


def test_settings_have_defaults_and_are_per_clinic(client: TestClient, tenant: Tenant):
    tenant.act(client, "patient")
    defaults = client.get("/api/v1/scheduling/settings").json()
    assert defaults["cancellation_deadline_hours"] == 24 and defaults["waitlist_offer_minutes"] == 60
    body = {"cancellation_deadline_hours": 48, "waitlist_offer_minutes": 30, "reminder_hours_before": 24, "booking_horizon_days": 60}
    assert client.patch("/api/v1/scheduling/settings", headers=tenant.act(client, "admin"), json=body).status_code == 200
    tenant.act(client, "patient")
    assert client.get("/api/v1/scheduling/settings").json()["cancellation_deadline_hours"] == 48
    bad = client.patch("/api/v1/scheduling/settings", headers=tenant.act(client, "admin"), json={**body, "waitlist_offer_minutes": 1})
    assert bad.status_code == 422


def test_weekly_schedule_rules_are_validated(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    headers = tenant.act(client, "clinic_admin")
    url = f"/api/v1/scheduling/professionals/{tenant.staff_ids['doctor']}/schedule"
    overlapping = {"rules": [
        {"weekday": 0, "start_time": "09:00", "end_time": "12:00", "appointment_type_ids": [ids["type_id"]]},
        {"weekday": 0, "start_time": "11:00", "end_time": "13:00", "appointment_type_ids": [ids["type_id"]]},
    ]}
    assert client.post(url, headers=headers, json=overlapping).status_code == 422
    backwards = {"rules": [{"weekday": 0, "start_time": "12:00", "end_time": "09:00", "appointment_type_ids": [ids["type_id"]]}]}
    assert client.post(url, headers=headers, json=backwards).status_code == 422

    other_specialty = client.post("/api/v1/scheduling/specialties", headers=headers, json={"name": "Pediatria"}).json()["id"]
    foreign_type = client.post(
        "/api/v1/scheduling/appointment-types",
        headers=headers,
        json={"name": "Pediatria geral", "duration_minutes": 20, "specialty_id": other_specialty, "booking_mode": "request"},
    ).json()["id"]
    wrong = {"rules": [{"weekday": 1, "start_time": "09:00", "end_time": "10:00", "appointment_type_ids": [foreign_type]}]}
    assert client.post(url, headers=headers, json=wrong).status_code == 422

    # The doctor reads their own schedule; another professional and the patient may not.
    assert len(client.get(url, headers=tenant.act(client, "doctor")).json()) == 5
    assert client.get(url, headers=tenant.act(client, "nurse")).status_code == 403
    assert client.get(url, headers=tenant.act(client, "patient")).status_code == 403


# --- free slots ----------------------------------------------------------------------------------


def test_free_slots_follow_schedule_absences_and_appointments(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    monday = next_weekday(0)
    url = f"/api/v1/scheduling/slots?appointment_type_id={ids['type_id']}&from={monday}&to={monday}"
    headers = tenant.act(client, "clinic_admin")
    slots = client.get(url).json()
    assert [datetime.fromisoformat(s["starts_at"]).astimezone(LISBON).strftime("%H:%M") for s in slots] == [
        "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    ]
    booked = client.post(
        "/api/v1/appointments",
        headers=headers,
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": slots[1]["starts_at"], "duration_minutes": 30},
    )
    assert booked.status_code == 201, booked.text
    absence = client.post(
        "/api/v1/scheduling/absences",
        headers=tenant.act(client, "doctor"),
        json={"starts_at": slots[4]["starts_at"], "ends_at": slots[5]["ends_at"], "kind": "other"},
    )
    assert absence.status_code == 201 and absence.json()["conflicting_appointments"] == 0
    tenant.act(client, "clinic_admin")
    remaining = [datetime.fromisoformat(s["starts_at"]).astimezone(LISBON).strftime("%H:%M") for s in client.get(url).json()]
    assert remaining == ["09:00", "10:00", "10:30"]
    assert client.get(f"/api/v1/scheduling/slots?appointment_type_id={ids['type_id']}&from={monday}&to={monday + timedelta(days=40)}").status_code == 422


def test_slots_keep_wall_clock_hours_across_daylight_saving(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    # Portugal switches to summer time on the last Sunday of March; compare the Fridays around it.
    with client.session_factory() as db:  # type: ignore[attr-defined]
        appointment_type = db.get(AppointmentType, uuid.UUID(ids["type_id"]))
        assert appointment_type is not None
        winter, summer = date(2027, 3, 26), date(2027, 4, 2)
        slots = free_slots(
            db,
            clinic_id=uuid.UUID(tenant.clinic_id),
            appointment_type=appointment_type,
            staff_ids=[uuid.UUID(tenant.staff_ids["doctor"])],
            day_from=winter,
            day_to=summer,
            now=datetime(2027, 1, 1, tzinfo=UTC),
        )
    firsts = {slot.starts_at.astimezone(LISBON).date(): slot.starts_at for slot in slots if slot.starts_at.astimezone(LISBON).time() == time(9, 0)}
    assert firsts[winter].astimezone(UTC).hour == 9  # WET, UTC+0
    assert firsts[summer].astimezone(UTC).hour == 8  # WEST, UTC+1


def test_patients_do_not_see_professionals_closed_to_new_patients_unless_known(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    headers = tenant.act(client, "clinic_admin")
    assert client.patch(
        f"/api/v1/scheduling/professionals/{tenant.staff_ids['doctor']}", headers=headers, json={"accepts_new_patients": False}
    ).status_code == 200
    monday = next_weekday(0)
    url = f"/api/v1/scheduling/slots?appointment_type_id={ids['type_id']}&from={monday}&to={monday}"
    tenant.act(client, "other_patient")
    assert client.get(url).json() == []
    # The patient who already had an appointment with the doctor still sees the slots.
    client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "clinic_admin"),
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": f"{monday}T15:00:00+00:00"},
    )
    tenant.act(client, "patient")
    assert len(client.get(url).json()) == 6


# --- double booking in the database ---------------------------------------------------------------


def _insert(connection, tenant: Tenant, *, staff: str, patient: str, start: str, end: str, status: str = "scheduled") -> None:
    connection.execute(
        text(
            "INSERT INTO appointments (id, clinic_id, patient_id, staff_id, scheduled_at, ends_at, duration_minutes, status) "
            "VALUES (:id, :clinic, :patient, :staff, :start, :end, 30, :status)"
        ),
        {"id": uuid.uuid4(), "clinic": tenant.clinic_id, "patient": patient, "staff": staff, "start": start, "end": end, "status": status},
    )


def test_database_refuses_overlaps_for_a_professional_and_for_a_patient(client: TestClient, tenant: Tenant):
    engine = create_engine(TEST_DATABASE_URL, future=True)
    doctor, nurse = tenant.staff_ids["doctor"], tenant.staff_ids["nurse"]
    try:
        with engine.begin() as connection:
            _insert(connection, tenant, staff=doctor, patient=tenant.patient_id, start="2030-01-07T10:00Z", end="2030-01-07T10:30Z")
            # adjacent: allowed; cancelled overlap: allowed
            _insert(connection, tenant, staff=doctor, patient=tenant.other_patient_id, start="2030-01-07T10:30Z", end="2030-01-07T11:00Z")
            _insert(connection, tenant, staff=doctor, patient=tenant.other_patient_id, start="2030-01-07T10:10Z", end="2030-01-07T10:40Z", status="cancelled")
        for staff, patient, constraint in (
            (doctor, tenant.other_patient_id, "ex_appointments_staff_no_overlap"),
            (nurse, tenant.patient_id, "ex_appointments_patient_no_overlap"),
        ):
            with pytest.raises(IntegrityError) as excinfo:
                with engine.begin() as connection:
                    _insert(connection, tenant, staff=staff, patient=patient, start="2030-01-07T10:15Z", end="2030-01-07T10:45Z")
            assert excinfo.value.orig.sqlstate == "23P01"
            assert excinfo.value.orig.diag.constraint_name == constraint
    finally:
        engine.dispose()


def test_concurrent_transactions_cannot_both_book_the_same_slot(client: TestClient, tenant: Tenant):
    """Two transactions without any application lock: the second waits for the first and
    then fails on the exclusion constraint. One booking wins, never both."""
    engine = create_engine(TEST_DATABASE_URL, future=True)
    doctor = tenant.staff_ids["doctor"]
    first_inserted = threading.Event()
    results: dict[str, str] = {}

    def first() -> None:
        with engine.connect() as connection:
            transaction = connection.begin()
            _insert(connection, tenant, staff=doctor, patient=tenant.patient_id, start="2030-02-04T09:00Z", end="2030-02-04T09:30Z")
            first_inserted.set()
            threading.Event().wait(0.5)
            transaction.commit()
            results["first"] = "committed"

    def second() -> None:
        first_inserted.wait(5)
        try:
            with engine.begin() as connection:
                _insert(connection, tenant, staff=doctor, patient=tenant.other_patient_id, start="2030-02-04T09:15Z", end="2030-02-04T09:45Z")
            results["second"] = "committed"
        except IntegrityError as exc:
            results["second"] = exc.orig.sqlstate

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    engine.dispose()
    assert results == {"first": "committed", "second": "23P01"}


def test_api_reports_patient_overlap_and_database_conflicts_as_409(client: TestClient, tenant: Tenant, monkeypatch):
    headers = tenant.act(client, "clinic_admin")
    body = {"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": "2030-03-04T10:00:00Z"}
    assert client.post("/api/v1/appointments", headers=headers, json=body).status_code == 201
    with_nurse = client.post("/api/v1/appointments", headers=headers, json={**body, "staff_id": tenant.staff_ids["nurse"]})
    assert with_nurse.status_code == 409
    assert with_nurse.json()["detail"] == "O paciente já tem uma consulta a essa hora."

    # Even if the application checks were skipped, the database answers (no 500, no double booking).
    monkeypatch.setattr("app.modules.appointments.service._ensure_no_conflict", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.modules.appointments.service._ensure_patient_free", lambda *args, **kwargs: None)
    raced = client.post("/api/v1/appointments", headers=headers, json={**body, "patient_id": tenant.other_patient_id})
    assert raced.status_code == 409
    assert raced.json()["detail"] == "Este horário já não está disponível para este profissional."


# --- automatic care-team assignment -----------------------------------------------------------------


def test_booking_puts_the_professional_on_the_care_team_once_and_audits_it(client: TestClient, tenant: Tenant):
    headers = tenant.act(client, "admin")
    body = {"patient_id": tenant.other_patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": "2030-04-01T10:00:00Z"}
    assert client.post("/api/v1/appointments", headers=headers, json=body).status_code == 201
    assert client.post("/api/v1/appointments", headers=headers, json={**body, "scheduled_at": "2030-04-02T10:00:00Z"}).status_code == 201
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = db.query(ClinicalCareAssignment).filter_by(patient_id=uuid.UUID(tenant.other_patient_id), staff_id=uuid.UUID(tenant.staff_ids["doctor"]), active=True).all()
    assert len(rows) == 1
    audits = [row for row in _audit(client, AuditAction.CARE_ASSIGNMENT_CREATED) if (row.event_metadata or {}).get("via") == "appointment"]
    assert len(audits) == 1
    assert audits[0].event_metadata["patient_id"] == tenant.other_patient_id
    assert audits[0].event_metadata["staff_id"] == tenant.staff_ids["doctor"]
    assert set(audits[0].event_metadata) <= {"patient_id", "staff_id", "appointment_id", "via", "actor_staff_role"}
    # The doctor now has clinical access to that patient.
    assert client.get(f"/api/v1/patients/{tenant.other_patient_id}", headers=tenant.act(client, "doctor")).status_code == 200

    # An administrative professional is never put on a care team.
    admin_staff = client.post(
        "/api/v1/appointments", headers=tenant.act(client, "clinic_admin"),
        json={**body, "staff_id": tenant.staff_ids["admin"], "scheduled_at": "2030-04-03T10:00:00Z"},
    )
    assert admin_staff.status_code == 201
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.query(ClinicalCareAssignment).filter_by(staff_id=uuid.UUID(tenant.staff_ids["admin"])).count() == 0


# --- absences and agenda ---------------------------------------------------------------------------


def test_absences_and_agenda_permissions(client: TestClient, tenant: Tenant):
    setup_booking(client, tenant)
    monday = next_weekday(0)
    client.post(
        "/api/v1/appointments", headers=tenant.act(client, "clinic_admin"),
        json={"patient_id": tenant.patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": f"{monday}T10:00:00+00:00"},
    )
    # The doctor blocks the morning: told about the appointment inside it (never cancelled automatically).
    created = client.post(
        "/api/v1/scheduling/absences",
        headers=tenant.act(client, "doctor"),
        json={"starts_at": f"{monday}T08:00:00+00:00", "ends_at": f"{monday}T13:00:00+00:00", "kind": "vacation"},
    )
    assert created.status_code == 201 and created.json()["conflicting_appointments"] == 1
    absence_id = created.json()["id"]

    agenda = client.get(f"/api/v1/scheduling/agenda?from={monday}&to={monday + timedelta(days=6)}").json()
    assert agenda["appointments"][0]["appointment_type"] == "Consulta"
    assert agenda["appointments"][0]["patient_name"]
    assert len(agenda["absences"]) == 1 and len(agenda["rules"]) == 5

    for role in ("nurse", "patient"):
        assert client.post(f"/api/v1/scheduling/absences/{absence_id}/delete", headers=tenant.act(client, role)).status_code == 403
        assert client.get(f"/api/v1/scheduling/agenda?from={monday}&to={monday}&staff_id={tenant.staff_ids['doctor']}").status_code == 403
    assert client.get(f"/api/v1/scheduling/agenda?from={monday}&to={monday}", headers=tenant.act(client, "patient")).status_code == 403
    tenant.act(client, "admin")
    assert client.get(f"/api/v1/scheduling/agenda?from={monday}&to={monday}&staff_id={tenant.staff_ids['doctor']}").status_code == 200
    assert client.post(f"/api/v1/scheduling/absences/{absence_id}/delete", headers=tenant.act(client, "doctor")).status_code == 204
    other = make_tenant(client, f"sched-iso-{uuid.uuid4().hex[:8]}")
    assert client.get(f"/api/v1/scheduling/agenda?from={monday}&to={monday}&staff_id={tenant.staff_ids['doctor']}", headers=other.act(client, "clinic_admin")).status_code == 404


def test_configuration_changes_are_audited_by_identifier_only(client: TestClient, tenant: Tenant):
    setup_booking(client, tenant)
    for action in (
        AuditAction.SPECIALTY_CREATED,
        AuditAction.APPOINTMENT_TYPE_CREATED,
        AuditAction.STAFF_BOOKING_PROFILE_UPDATED,
        AuditAction.SCHEDULE_UPDATED,
    ):
        (row,) = _audit(client, action)
        assert row.resource_id is not None
        assert "Medicina Geral" not in str(row.event_metadata) and "Consulta de rotina" not in str(row.event_metadata)


def test_rules_cascade_their_type_links_and_types_keep_bookings(client: TestClient, tenant: Tenant):
    ids = setup_booking(client, tenant)
    headers = tenant.act(client, "clinic_admin")
    assert client.post(f"/api/v1/scheduling/professionals/{tenant.staff_ids['doctor']}/schedule", headers=headers, json={"rules": []}).status_code == 200
    with client.session_factory() as db:  # type: ignore[attr-defined]
        assert db.query(ScheduleRule).count() == 0 and db.query(ScheduleRuleType).count() == 0
        assert db.query(ScheduleAbsence).count() == 0
        assert db.get(AppointmentType, uuid.UUID(ids["type_id"])).booking_mode == BookingMode.DIRECT
