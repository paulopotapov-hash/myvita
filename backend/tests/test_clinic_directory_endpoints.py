"""
Tests for the two directory endpoints added for the frontend
(GET /api/v1/patients, GET /api/v1/staff): role restrictions and, most
importantly, that they never leak another clinic's data.

Named to sort before test_data_integrity.py — see test_auth_hardening.py's
fixture docstring for why cross-file ordering matters here.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.rate_limit import limiter
from app.main import app
from tests.conftest import TEST_DATABASE_URL, csrf_headers


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
    limiter.reset()
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _onboard_clinic(client, name="Clínica A", email="admin@clinica-a.pt", password="SenhaForte123!"):
    r = client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": name,
            "admin_full_name": "Admin",
            "admin_email": email,
            "admin_password": password,
        },
    )
    return r.json()["id"]


def _register_patient(client, clinic_id, email="paciente@example.com", password="SenhaForte123!"):
    r = client.post(
        "/api/v1/patients/register",
        json={"clinic_id": clinic_id, "full_name": "Paciente Teste", "email": email, "password": password},
    )
    return r.json()["id"]


def _login(client, email, password="SenhaForte123!"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _create_staff(client, email="staff@clinica-a.pt", password="SenhaForte123!", full_name="Dr. Teste"):
    r = client.post(
        "/api/v1/staff",
        json={"full_name": full_name, "email": email, "password": password, "staff_role": "doctor"},
        headers=csrf_headers(client),
    )
    return r.json()["id"] if r.status_code == 201 else None


def test_staff_can_list_patients_in_own_clinic(client):
    clinic_id = _onboard_clinic(client)
    _register_patient(client, clinic_id)
    _login(client, "admin@clinica-a.pt")

    r = client.get("/api/v1/patients")
    assert r.status_code == 200
    names = [p["full_name"] for p in r.json()]
    assert "Paciente Teste" in names


def test_patient_role_cannot_list_patients(client):
    clinic_id = _onboard_clinic(client)
    _register_patient(client, clinic_id)  # auto-logs in as the patient

    r = client.get("/api/v1/patients")
    assert r.status_code == 403


def test_patient_list_never_crosses_clinics(client):
    clinic_a = _onboard_clinic(client, "Clínica A", "admin@a.pt")
    _register_patient(client, clinic_a, "paciente-a@example.com")

    clinic_b = _onboard_clinic(client, "Clínica B", "admin@b.pt")
    _register_patient(client, clinic_b, "paciente-b@example.com")

    _login(client, "admin@a.pt")
    r = client.get("/api/v1/patients")
    emails_seen_names = [p["full_name"] for p in r.json()]
    assert len(r.json()) == 1
    assert "Paciente Teste" in emails_seen_names  # only clinic A's patient


def test_staff_directory_visible_to_patients_too(client):
    clinic_id = _onboard_clinic(client)
    _create_staff(client)  # already logged in as admin right after onboarding

    _register_patient(client, clinic_id, "paciente2@example.com")  # switches session to the patient
    r = client.get("/api/v1/staff")
    assert r.status_code == 200
    assert any(s["staff_role"] == "doctor" for s in r.json())


def test_staff_directory_never_crosses_clinics(client):
    _onboard_clinic(client, "Clínica A", "admin@a.pt")
    _create_staff(client, "doc-a@example.com", full_name="Dr. Clínica A")

    _onboard_clinic(client, "Clínica B", "admin@b.pt")
    _create_staff(client, "doc-b@example.com", full_name="Dr. Clínica B")

    _login(client, "admin@a.pt")
    r = client.get("/api/v1/staff")
    names = {s["full_name"] for s in r.json()}
    assert "Dr. Clínica A" in names
    assert "Dr. Clínica B" not in names
