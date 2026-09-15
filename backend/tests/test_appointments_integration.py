"""
Covers the appointment-booking feature added in v0.2, including the
cross-clinic IDOR attack scenario found and blocked during manual testing:
a clinic admin must not be able to book an appointment using another
clinic's patient_id or staff_id.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
    admin_cookie = r.cookies.get("myvita_session")
    clinic_id = r.json()["id"]

    client.cookies.set("myvita_session", admin_cookie)
    r = client.post(
        "/api/v1/staff",
        json={
            "full_name": f"Dr. {suffix}",
            "email": f"doctor{suffix}@x.pt",
            "password": "SenhaForte123!",
            "staff_role": "doctor",
        },
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
    patient_cookie = r.cookies.get("myvita_session")

    return {
        "clinic_id": clinic_id,
        "admin_cookie": admin_cookie,
        "staff_id": staff_id,
        "patient_id": patient_id,
        "patient_cookie": patient_cookie,
    }


def test_staff_can_book_appointment_for_their_clinic(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    client.cookies.set("myvita_session", a["admin_cookie"])

    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": a["patient_id"],
            "staff_id": a["staff_id"],
            "scheduled_at": "2026-10-01T10:00:00Z",
            "reason": "Consulta geral",
        },
    )
    assert r.status_code == 201
    assert r.json()["status"] == "scheduled"


def test_patient_sees_only_their_own_appointment(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    client.cookies.set("myvita_session", a["admin_cookie"])
    client.post(
        "/api/v1/appointments",
        json={"patient_id": a["patient_id"], "staff_id": a["staff_id"], "scheduled_at": "2026-10-01T10:00:00Z"},
    )

    client.cookies.set("myvita_session", a["patient_cookie"])
    r = client.get("/api/v1/appointments")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["patient_id"] == a["patient_id"]


def test_patient_cannot_create_appointments_directly(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    client.cookies.set("myvita_session", a["patient_cookie"])

    r = client.post(
        "/api/v1/appointments",
        json={"patient_id": a["patient_id"], "staff_id": a["staff_id"], "scheduled_at": "2026-10-01T10:00:00Z"},
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

    client.cookies.set("myvita_session", b["admin_cookie"])
    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": a["patient_id"],  # clinic A's patient
            "staff_id": b["staff_id"],  # clinic B's own staff
            "scheduled_at": "2026-10-02T10:00:00Z",
        },
    )
    assert r.status_code == 404


def test_cross_clinic_idor_using_another_clinics_staff_is_blocked(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    b = _new_clinic_with_staff_and_patient(client, "B")

    client.cookies.set("myvita_session", b["admin_cookie"])
    r = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": b["patient_id"],  # clinic B's own patient
            "staff_id": a["staff_id"],  # clinic A's staff — not theirs to use
            "scheduled_at": "2026-10-02T10:00:00Z",
        },
    )
    assert r.status_code == 404


def test_staff_list_only_shows_own_clinic_appointments(client):
    a = _new_clinic_with_staff_and_patient(client, "A")
    b = _new_clinic_with_staff_and_patient(client, "B")

    client.cookies.set("myvita_session", a["admin_cookie"])
    client.post(
        "/api/v1/appointments",
        json={"patient_id": a["patient_id"], "staff_id": a["staff_id"], "scheduled_at": "2026-10-01T10:00:00Z"},
    )

    client.cookies.set("myvita_session", b["admin_cookie"])
    client.post(
        "/api/v1/appointments",
        json={"patient_id": b["patient_id"], "staff_id": b["staff_id"], "scheduled_at": "2026-10-01T11:00:00Z"},
    )

    r = client.get("/api/v1/appointments")  # still authenticated as clinic B's admin
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["clinic_id"] == b["clinic_id"]
