from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture()
def client():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    test_session = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def _identity(response) -> dict[str, str]:
    session = response.cookies.get(settings.COOKIE_NAME)
    csrf = response.cookies.get(settings.CSRF_COOKIE_NAME)
    assert session and csrf
    return {"session": session, "csrf": csrf}


def _use(client: TestClient, identity: dict[str, str]) -> dict[str, str]:
    client.cookies.set(settings.COOKIE_NAME, identity["session"])
    client.cookies.set(settings.CSRF_COOKIE_NAME, identity["csrf"])
    return {settings.CSRF_HEADER_NAME: identity["csrf"]}


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "SenhaForte123!"})
    assert response.status_code == 200
    return _identity(response)


def _tenant(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": f"P4.1 Clinic {suffix}",
            "admin_full_name": f"Clinic Admin {suffix}",
            "admin_email": f"clinic-admin-{suffix}@example.pt",
            "admin_password": "SenhaForte123!",
        },
    )
    assert response.status_code == 201
    clinic_id = response.json()["id"]
    identities = {"clinic_admin": _identity(response)}
    staff_ids = {}
    for role in ("doctor", "nurse", "admin"):
        email = f"{role}-{suffix}@example.pt"
        created = client.post(
            "/api/v1/staff",
            headers=_use(client, identities["clinic_admin"]),
            json={
                "full_name": f"{role.title()} {suffix}",
                "email": email,
                "password": "SenhaForte123!",
                "staff_role": role,
                "require_password_change": False,
            },
        )
        assert created.status_code == 201
        staff_ids[role] = created.json()["id"]
        identities[role] = _login(client, email)

    patient_response = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": f"Patient {suffix}",
            "email": f"patient-{suffix}@example.pt",
            "password": "SenhaForte123!",
            "birth_date": "1990-01-02",
            "phone": "910000000",
        },
    )
    assert patient_response.status_code == 201
    identities["patient"] = _identity(patient_response)
    for role in ("doctor", "nurse"):
        assigned = client.post(
            f"/api/v1/patients/{patient_response.json()['id']}/care-team",
            headers=_use(client, identities["clinic_admin"]),
            json={"staff_id": staff_ids[role]},
        )
        assert assigned.status_code == 201, assigned.text
    return {
        "clinic_id": clinic_id,
        "patient_id": patient_response.json()["id"],
        "identities": identities,
        "staff_ids": staff_ids,
    }


def _grant_own_consent(client: TestClient, tenant: dict) -> str:
    response = client.post(
        f"/api/v1/patients/{tenant['patient_id']}/consents",
        headers=_use(client, tenant["identities"]["patient"]),
        json={"consent_type": "treatment", "purpose": "Direct care"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_consent_matrix_rejects_administrative_and_clinician_mutations(client: TestClient):
    tenant = _tenant(client, "consent")
    consent_id = _grant_own_consent(client, tenant)

    for role in ("doctor", "nurse"):
        headers = _use(client, tenant["identities"][role])
        assert client.get(f"/api/v1/patients/{tenant['patient_id']}/consents").status_code == 200
        assert client.get(f"/api/v1/consents/{consent_id}").status_code == 200
        assert (
            client.post(
                f"/api/v1/patients/{tenant['patient_id']}/consents",
                headers=headers,
                json={"consent_type": "research", "purpose": role},
            ).status_code
            == 403
        )
        assert client.post(f"/api/v1/consents/{consent_id}/revoke", headers=headers).status_code == 403

    for role in ("admin", "clinic_admin"):
        headers = _use(client, tenant["identities"][role])
        assert client.get(f"/api/v1/patients/{tenant['patient_id']}/consents").status_code == 403
        assert client.get(f"/api/v1/consents/{consent_id}").status_code == 403
        assert (
            client.post(
                f"/api/v1/patients/{tenant['patient_id']}/consents",
                headers=headers,
                json={"consent_type": "research", "purpose": role},
            ).status_code
            == 403
        )
        assert client.post(f"/api/v1/consents/{consent_id}/revoke", headers=headers).status_code == 403


def test_patient_demographic_summary_full_record_and_mass_assignment(client: TestClient):
    tenant = _tenant(client, "demographic")
    patient_url = f"/api/v1/patients/{tenant['patient_id']}"

    for role in ("admin", "clinic_admin"):
        headers = _use(client, tenant["identities"][role])
        listed = client.get("/api/v1/patients")
        assert listed.status_code == 200
        assert set(listed.json()[0]) == {"id", "clinic_id", "full_name", "is_active"}
        assert client.get(patient_url).status_code == 403
        assert client.patch(patient_url, headers=headers, json={"phone": "919999999"}).status_code == 403

    for role in ("doctor", "nurse"):
        headers = _use(client, tenant["identities"][role])
        assert client.get(patient_url).status_code == 200
        changed = client.patch(patient_url, headers=headers, json={"national_health_number": role})
        assert changed.status_code == 200

    patient_headers = _use(client, tenant["identities"]["patient"])
    assert client.patch(patient_url, headers=patient_headers, json={"phone": "911111111"}).status_code == 200
    assert (
        client.patch(patient_url, headers=patient_headers, json={"birth_date": "2000-01-01"}).status_code
        == 403
    )
    for payload in (
        {"clinic_id": tenant["clinic_id"]},
        {"user_id": "00000000-0000-0000-0000-000000000000"},
        {"unknown": True},
    ):
        assert client.patch(patient_url, headers=patient_headers, json=payload).status_code == 422


def test_appointment_reason_is_clinical_but_operational_scheduling_remains_available(client: TestClient):
    tenant = _tenant(client, "reason")
    start = datetime.now(UTC) + timedelta(days=3)
    created = client.post(
        "/api/v1/appointments",
        headers=_use(client, tenant["identities"]["doctor"]),
        json={
            "patient_id": tenant["patient_id"],
            "staff_id": tenant["staff_ids"]["doctor"],
            "scheduled_at": start.isoformat(),
            "reason": "Sensitive clinical reason",
        },
    )
    assert created.status_code == 201
    appointment_id = created.json()["id"]

    for role in ("admin", "clinic_admin"):
        headers = _use(client, tenant["identities"][role])
        assert client.get("/api/v1/appointments").json()[0]["reason"] is None
        assert client.get(f"/api/v1/appointments/{appointment_id}").json()["reason"] is None
        assert (
            client.patch(
                f"/api/v1/appointments/{appointment_id}", headers=headers, json={"reason": "Probe"}
            ).status_code
            == 403
        )
        operational = client.patch(
            f"/api/v1/appointments/{appointment_id}", headers=headers, json={"duration_minutes": 35}
        )
        assert operational.status_code == 200
        assert operational.json()["reason"] is None

    _use(client, tenant["identities"]["patient"])
    assert (
        client.get(f"/api/v1/appointments/{appointment_id}").json()["reason"] == "Sensitive clinical reason"
    )
    _use(client, tenant["identities"]["nurse"])
    assert (
        client.get(f"/api/v1/appointments/{appointment_id}").json()["reason"] == "Sensitive clinical reason"
    )


def test_cross_tenant_resources_remain_hidden_for_every_hardened_area(client: TestClient):
    first = _tenant(client, "tenant-a")
    second = _tenant(client, "tenant-b")
    consent_id = _grant_own_consent(client, first)
    appointment = client.post(
        "/api/v1/appointments",
        headers=_use(client, first["identities"]["doctor"]),
        json={
            "patient_id": first["patient_id"],
            "staff_id": first["staff_ids"]["doctor"],
            "scheduled_at": (datetime.now(UTC) + timedelta(days=4)).isoformat(),
            "reason": "Private",
        },
    )
    appointment_id = appointment.json()["id"]

    for role in ("patient", "doctor", "nurse", "admin", "clinic_admin"):
        headers = _use(client, second["identities"][role])
        assert client.get(f"/api/v1/patients/{first['patient_id']}").status_code == 404
        assert client.get(f"/api/v1/patients/{first['patient_id']}/consents").status_code == 404
        assert client.get(f"/api/v1/consents/{consent_id}").status_code == 404
        assert client.get(f"/api/v1/appointments/{appointment_id}").status_code == 404
        if role != "patient":
            assert (
                client.patch(
                    f"/api/v1/appointments/{appointment_id}", headers=headers, json={"reason": "Probe"}
                ).status_code
                == 404
            )
