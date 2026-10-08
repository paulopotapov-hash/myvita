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


# --- Self-registration is limited to opted-in clinics (PUBLIC_CLINIC_IDS) ----------

def _register(world, clinic_id: str, label: str):
    import uuid

    from app.core.rate_limit import limiter
    from tests.phase1_world import Actor

    limiter.reset()
    return Actor(label).post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": f"Self {label}",
            "email": f"self-{label}-{uuid.uuid4().hex[:8]}@registration.example",
            "password": "SenhaForte123!",
        },
        csrf=False,
    )


def test_registration_into_a_non_public_clinic_is_indistinguishable_from_unknown(world, monkeypatch):
    import uuid

    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", True)
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [uuid.UUID(world.b.clinic_id)])

    unknown = _register(world, str(uuid.uuid4()), "unknown")
    existing_private = _register(world, world.a.clinic_id, "private")

    assert unknown.status_code == 404
    assert existing_private.status_code == 404
    assert existing_private.json() == unknown.json()
    assert settings.COOKIE_NAME not in existing_private.cookies


def test_registration_into_a_public_clinic_succeeds(world, monkeypatch):
    import uuid

    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", True)
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [uuid.UUID(world.a.clinic_id)])

    response = _register(world, world.a.clinic_id, "public")

    assert response.status_code == 201, response.text
    assert response.json()["clinic_id"] == world.a.clinic_id


def test_registration_flag_off_still_closes_registration_for_public_clinics(world, monkeypatch):
    import uuid

    monkeypatch.setattr(settings, "ALLOW_PUBLIC_PATIENT_REGISTRATION", False)
    monkeypatch.setattr(settings, "PUBLIC_CLINIC_IDS", [uuid.UUID(world.a.clinic_id)])

    assert _register(world, world.a.clinic_id, "flag-off").status_code == 403
