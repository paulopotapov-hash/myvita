"""Helpers for the scheduling suites: a clinic with a specialty, appointment types and a
weekly schedule for its doctor. Synthetic data only."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.clinical_support import Tenant


def next_weekday(weekday: int, *, at_least_days: int = 7, start: date | None = None) -> date:
    day = (start or date.today()) + timedelta(days=at_least_days)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def setup_booking(client: TestClient, tenant: Tenant, *, mode: str = "direct", duration: int = 30) -> dict:
    headers = tenant.act(client, "clinic_admin")
    specialty = client.post("/api/v1/scheduling/specialties", headers=headers, json={"name": "Medicina Geral"})
    assert specialty.status_code == 201, specialty.text
    specialty_id = specialty.json()["id"]
    appointment_type = client.post(
        "/api/v1/scheduling/appointment-types",
        headers=headers,
        json={"name": "Consulta de rotina", "duration_minutes": duration, "specialty_id": specialty_id, "booking_mode": mode},
    )
    assert appointment_type.status_code == 201, appointment_type.text
    type_id = appointment_type.json()["id"]
    profile = client.patch(
        f"/api/v1/scheduling/professionals/{tenant.staff_ids['doctor']}", headers=headers, json={"specialty_id": specialty_id}
    )
    assert profile.status_code == 200, profile.text
    schedule = client.post(
        f"/api/v1/scheduling/professionals/{tenant.staff_ids['doctor']}/schedule",
        headers=headers,
        json={"rules": [{"weekday": weekday, "start_time": "09:00", "end_time": "12:00", "appointment_type_ids": [type_id]} for weekday in range(5)]},
    )
    assert schedule.status_code == 200, schedule.text
    return {"specialty_id": specialty_id, "type_id": type_id}
