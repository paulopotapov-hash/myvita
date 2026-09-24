from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models import Notification, User
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture()
def client():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.test_session = test_session
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
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


def _tenant(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": f"B6 Clinic {suffix}",
            "admin_full_name": f"Admin {suffix}",
            "admin_email": f"b6-admin-{suffix}@example.pt",
            "admin_password": "SenhaForte123!",
        },
    )
    assert response.status_code == 201
    admin = _identity(response)
    clinic_id = response.json()["id"]
    response = client.post(
        "/api/v1/staff",
        headers=_use(client, admin),
        json={
            "full_name": f"Doctor {suffix}",
            "email": f"b6-doctor-{suffix}@example.pt",
            "password": "SenhaForte123!",
            "staff_role": "doctor",
        },
    )
    assert response.status_code == 201
    staff_id = response.json()["id"]
    response = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": f"Patient {suffix}",
            "email": f"b6-patient-{suffix}@example.pt",
            "password": "SenhaForte123!",
        },
    )
    assert response.status_code == 201
    patient = _identity(response)
    patient_id = response.json()["id"]
    response = client.post(
        "/api/v1/auth/login",
        json={"email": f"b6-doctor-{suffix}@example.pt", "password": "SenhaForte123!"},
    )
    assert response.status_code == 200
    doctor = _identity(response)
    return {
        "clinic_id": clinic_id,
        "admin": admin,
        "doctor": doctor,
        "doctor_email": f"b6-doctor-{suffix}@example.pt",
        "staff_id": staff_id,
        "patient": patient,
        "patient_email": f"b6-patient-{suffix}@example.pt",
        "patient_id": patient_id,
    }


def test_auth_me_exposes_only_the_authenticated_profile_identity(client: TestClient):
    tenant = _tenant(client, "identity")
    _use(client, tenant["doctor"])
    staff_me = client.get("/api/v1/auth/me")
    assert staff_me.status_code == 200
    assert staff_me.json()["staff_role"] == "doctor"
    assert staff_me.json()["patient_id"] is None

    _use(client, tenant["patient"])
    patient_me = client.get("/api/v1/auth/me")
    assert patient_me.status_code == 200
    assert patient_me.json()["patient_id"] == tenant["patient_id"]
    assert patient_me.json()["staff_role"] is None


def test_patient_pagination_detail_update_and_cross_tenant_isolation(client: TestClient):
    first = _tenant(client, "patient-a")
    second = _tenant(client, "patient-b")
    headers = _use(client, first["admin"])
    listed = client.get("/api/v1/patients?page=1&page_size=1")
    assert listed.status_code == 200
    assert listed.headers["x-total-count"] == "1"
    assert len(listed.json()) == 1

    detail = client.get(f"/api/v1/patients/{first['patient_id']}")
    assert detail.status_code == 200
    updated = client.patch(
        f"/api/v1/patients/{first['patient_id']}",
        headers=headers,
        json={"phone": "912345678", "national_health_number": "123456789"},
    )
    assert updated.status_code == 200
    assert updated.json()["national_health_number"] == "123456789"
    assert client.patch(f"/api/v1/patients/{first['patient_id']}", headers=headers, json={}).status_code == 422
    assert client.get(f"/api/v1/patients/{second['patient_id']}").status_code == 404

    _use(client, first["patient"])
    assert client.get(f"/api/v1/patients/{second['patient_id']}").status_code == 404


def test_appointment_update_conflict_cancel_and_lifecycle(client: TestClient):
    tenant = _tenant(client, "appointments")
    headers = _use(client, tenant["admin"])
    start = datetime.now(UTC) + timedelta(days=2)
    payload = {
        "patient_id": tenant["patient_id"],
        "staff_id": tenant["staff_id"],
        "scheduled_at": start.isoformat(),
        "duration_minutes": 30,
    }
    first = client.post("/api/v1/appointments", headers=headers, json=payload)
    assert first.status_code == 201
    conflict = client.post(
        "/api/v1/appointments",
        headers=headers,
        json={**payload, "scheduled_at": (start + timedelta(minutes=15)).isoformat()},
    )
    assert conflict.status_code == 409

    appointment_id = first.json()["id"]
    updated = client.patch(
        f"/api/v1/appointments/{appointment_id}", headers=headers, json={"duration_minutes": 45}
    )
    assert updated.status_code == 200
    assert updated.json()["duration_minutes"] == 45
    cancelled = client.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/v1/appointments/{appointment_id}/cancel", headers=headers).status_code == 409
    assert client.patch(
        f"/api/v1/appointments/{appointment_id}",
        headers=_use(client, tenant["patient"]),
        json={"duration_minutes": 60},
    ).status_code == 403


def test_medical_record_and_medication_are_versioned_and_patient_readable(client: TestClient):
    tenant = _tenant(client, "clinical")
    headers = _use(client, tenant["doctor"])
    record = client.post(
        f"/api/v1/patients/{tenant['patient_id']}/medical-records",
        headers=headers,
        json={"title": "Avaliação", "content": "Conteúdo clínico inicial"},
    )
    assert record.status_code == 201
    record_id = record.json()["id"]
    updated = client.patch(
        f"/api/v1/medical-records/{record_id}",
        headers=headers,
        json={"title": "Avaliação", "content": "Conteúdo clínico revisto"},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    revisions = client.get(f"/api/v1/medical-records/{record_id}/revisions")
    assert [revision["version"] for revision in revisions.json()] == [1, 2]

    medication = client.post(
        f"/api/v1/patients/{tenant['patient_id']}/medications",
        headers=headers,
        json={"name": "Medicamento A", "dosage": "10 mg", "start_date": "2026-09-24"},
    )
    assert medication.status_code == 201
    medication_id = medication.json()["id"]

    _use(client, tenant["patient"])
    assert client.get(f"/api/v1/patients/{tenant['patient_id']}/medical-records").status_code == 200
    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 200
    assert client.patch(
        f"/api/v1/medical-records/{record_id}",
        headers=_use(client, tenant["patient"]),
        json={"title": "Ataque", "content": "Não autorizado"},
    ).status_code in {403, 404}


def test_clinical_cross_tenant_idor_and_notification_ownership(client: TestClient):
    first = _tenant(client, "idor-a")
    second = _tenant(client, "idor-b")
    headers = _use(client, first["doctor"])
    record = client.post(
        f"/api/v1/patients/{first['patient_id']}/medical-records",
        headers=headers,
        json={"title": "Privado", "content": "Dados privados"},
    )
    record_id = record.json()["id"]
    medication = client.post(
        f"/api/v1/patients/{first['patient_id']}/medications",
        headers=headers,
        json={"name": "Privado", "dosage": "5 mg", "start_date": "2026-09-24"},
    )
    medication_id = medication.json()["id"]
    _use(client, second["doctor"])
    assert client.get(f"/api/v1/medical-records/{record_id}").status_code == 404
    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 404
    assert client.post(
        f"/api/v1/patients/{first['patient_id']}/medical-records",
        headers=_use(client, first["admin"]),
        json={"title": "Admin", "content": "Não permitido"},
    ).status_code == 403

    db = client.test_session()
    try:
        first_user = db.query(User).filter(User.email == first["patient_email"]).one()
        second_user = db.query(User).filter(User.email == second["patient_email"]).one()
        notification = Notification(
            clinic_id=first["clinic_id"], user_id=first_user.id, title="Consulta", message="Nova data"
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        notification_id = notification.id
        assert second_user.id != first_user.id
    finally:
        db.close()

    _use(client, second["patient"])
    assert client.get("/api/v1/notifications").json() == []
    assert (
        client.post(
            f"/api/v1/notifications/{notification_id}/read", headers=_use(client, second["patient"])
        ).status_code
        == 404
    )
    _use(client, first["patient"])
    listed = client.get("/api/v1/notifications")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    read = client.post(
        f"/api/v1/notifications/{notification_id}/read", headers=_use(client, first["patient"])
    )
    assert read.status_code == 200
    assert read.json()["is_read"] is True
