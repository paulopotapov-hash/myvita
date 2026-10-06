"""
Covers the appointment-booking feature added in v0.2, including the
cross-clinic IDOR attack scenario found and blocked during manual testing:
a clinic admin must not be able to book an appointment using another
clinic's patient_id or staff_id.

Since v0.2.1, every state-changing authenticated request also requires a
valid CSRF token (see tests/test_csrf.py for the dedicated CSRF test
suite). These tests switch between several logged-in identities on the
SAME TestClient instance, so we must save/restore BOTH the session cookie
AND the matching CSRF cookie for each identity — the CSRF token is bound
to a specific user's session, not shared across identities.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture()
def client():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _capture_identity(response) -> dict:
    """Grabs both the session cookie and its matching CSRF cookie from a
    login/registration response, so we can restore this exact identity
    later even after the client has moved on to a different session."""
    return {
        "session": response.cookies.get(settings.COOKIE_NAME),
        "csrf": response.cookies.get(settings.CSRF_COOKIE_NAME),
    }


def _use_identity(client, identity: dict) -> dict:
    """Switches the shared TestClient to the given identity's session, and
    returns the header dict to pass on state-changing requests."""
    client.cookies.set(settings.COOKIE_NAME, identity["session"])
    client.cookies.set(settings.CSRF_COOKIE_NAME, identity["csrf"])
    return {settings.CSRF_HEADER_NAME: identity["csrf"]}


def _new_clinic_with_staff_and_patient(client, suffix: str):
    r = client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": f"Clínica {suffix}",
            "admin_full_name": f"Admin {suffix}",
            "admin_email": f"admin{suffix}@x.pt",
            "admin_password": "SenhaForte123!",
        },
    )
    admin = _capture_identity(r)
    clinic_id = r.json()["id"]

    admin_headers = _use_identity(client, admin)
    r = client.post(
        "/api/v1/staff",
        json={
            "full_name": f"Dr. {suffix}",
            "email": f"doctor{suffix}@x.pt",
            "password": "SenhaForte123!",
            "staff_role": "doctor",
        },
        headers=admin_headers,
    )
    staff_id = r.json()["id"]

    r = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": f"Paciente {suffix}",
            "email": f"patient{suffix}@x.pt",
            "password": "SenhaForte123!",
        },
    )
    patient_id = r.json()["id"]
    patient = _capture_identity(r)

    return {
        "clinic_id": clinic_id,
        "admin": admin,
        "staff_id": staff_id,
        "patient_id": patient_id,
        "patient": patient,
    }


def test_staff_can_book_appointment_for_their_clinic(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    headers = _use_identity(client, a["admin"])

    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": a["patient_id"],
            "staff_id": a["staff_id"],
            "scheduled_at": "2026-10-01T10:00:00Z",
            "reason": "Consulta geral",
        },
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["status"] == "scheduled"


def test_patient_sees_only_their_own_appointment(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    headers = _use_identity(client, a["admin"])
    client.post(
        "/api/v1/appointments",
        json={"patient_id": a["patient_id"], "staff_id": a["staff_id"], "scheduled_at": "2026-10-01T10:00:00Z"},
        headers=headers,
    )

    _use_identity(client, a["patient"])
    r = client.get("/api/v1/appointments")  # GET — no CSRF header needed
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["patient_id"] == a["patient_id"]


def test_patient_cannot_create_appointments_directly(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    headers = _use_identity(client, a["patient"])

    r = client.post(
        "/api/v1/appointments",
        json={"patient_id": a["patient_id"], "staff_id": a["staff_id"], "scheduled_at": "2026-10-01T10:00:00Z"},
        headers=headers,
    )
    assert r.status_code == 403


def test_cross_clinic_idor_using_another_clinics_patient_is_blocked(client):
    """
    The core regression test for the bug class found during manual testing:
    clinic B's admin must not be able to book an appointment against
    clinic A's patient, even though both IDs are individually valid.
    """
    a = _new_clinic_with_staff_and_patient(client, "A")
    b = _new_clinic_with_staff_and_patient(client, "B")

    headers = _use_identity(client, b["admin"])
    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": a["patient_id"],  # clinic A's patient
            "staff_id": b["staff_id"],  # clinic B's own staff
            "scheduled_at": "2026-10-02T10:00:00Z",
        },
        headers=headers,
    )
    assert r.status_code == 404


def test_cross_clinic_idor_using_another_clinics_staff_is_blocked(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    b = _new_clinic_with_staff_and_patient(client, "B")

    headers = _use_identity(client, b["admin"])
    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": b["patient_id"],  # clinic B's own patient
            "staff_id": a["staff_id"],  # clinic A's staff — not theirs to use
            "scheduled_at": "2026-10-02T10:00:00Z",
        },
        headers=headers,
    )
    assert r.status_code == 404


def test_staff_list_only_shows_own_clinic_appointments(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    b = _new_clinic_with_staff_and_patient(client, "B")

    headers = _use_identity(client, a["admin"])
    client.post(
        "/api/v1/appointments",
        json={"patient_id": a["patient_id"], "staff_id": a["staff_id"], "scheduled_at": "2026-10-01T10:00:00Z"},
        headers=headers,
    )

    headers = _use_identity(client, b["admin"])
    client.post(
        "/api/v1/appointments",
        json={"patient_id": b["patient_id"], "staff_id": b["staff_id"], "scheduled_at": "2026-10-01T11:00:00Z"},
        headers=headers,
    )

    r = client.get("/api/v1/appointments")  # still authenticated as clinic B's admin, GET needs no CSRF
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["clinic_id"] == b["clinic_id"]
