from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_public_registration_is_closed_when_deployment_switches_are_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_CLINIC_ONBOARDING", False)
    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", False)

    with TestClient(app, base_url="http://testserver") as client:
        clinic = client.post(
            "/api/v1/clinics",
            json={
                "clinic_name": "Clínica de teste",
                "admin_full_name": "Administrador de teste",
                "admin_email": "admin@example.com",
                "admin_password": "SenhaForte123!",
            },
        )
        patient = client.post(
            "/api/v1/patients/register",
            json={
                "clinic_id": "11111111-1111-1111-1111-111111111111",
                "full_name": "Paciente de teste",
                "email": "patient@example.com",
                "password": "SenhaForte123!",
            },
        )

    assert clinic.status_code == 403
    assert patient.status_code == 403
    assert settings.COOKIE_NAME not in clinic.cookies
    assert settings.COOKIE_NAME not in patient.cookies
