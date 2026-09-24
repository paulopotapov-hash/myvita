# ruff: noqa: F401, F811
"""Regression tests for the Phase B production-hardening policy."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import User
from app.modules.clinical.service import create_notification
from tests.conftest import TEST_DATABASE_URL
from tests.test_appointments_integration import (
    _capture_identity,
    _future_iso,
    _new_clinic_with_staff_and_patient,
    _use_identity,
    client,
)


def _create_staff(client, clinic, suffix: str, role: str) -> dict:
    headers = _use_identity(client, clinic["admin"])
    email = f"staff-{role}{suffix}@x.pt"
    response = client.post(
        "/api/v1/staff",
        json={
            "full_name": f"{role.title()} {suffix}",
            "email": email,
            "password": "SenhaForte123!",
            "staff_role": role,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "SenhaForte123!"})
    return {"id": response.json()["id"], "identity": _capture_identity(login)}


def test_explicit_clinical_rbac_separates_doctor_nurse_and_admin(client):
    clinic = _new_clinic_with_staff_and_patient(client, "Roles")
    nurse = _create_staff(client, clinic, "Roles", "nurse")
    admin_staff = _create_staff(client, clinic, "Roles", "admin")
    record_payload = {"patient_id": clinic["patient_id"], "title": "Nota", "content": "Conteúdo"}
    medication_payload = {
        "patient_id": clinic["patient_id"], "name": "Med", "dose": "1",
        "frequency": "daily", "start_date": "2030-01-01",
    }

    assert client.post("/api/v1/medical-records", json=record_payload, headers=_use_identity(client, nurse["identity"])).status_code == 201
    assert client.post("/api/v1/medications", json=medication_payload, headers=_use_identity(client, nurse["identity"])).status_code == 403
    assert client.get(f"/api/v1/patients/{clinic['patient_id']}/medical-records").status_code == 200
    assert client.post("/api/v1/medical-records", json=record_payload, headers=_use_identity(client, admin_staff["identity"])).status_code == 403
    assert client.get(f"/api/v1/patients/{clinic['patient_id']}/medical-records").status_code == 403
    assert client.post("/api/v1/medical-records", json=record_payload, headers=_use_identity(client, clinic["admin"])).status_code == 403


def test_record_updates_preserve_version_history_and_validate_payload(client):
    clinic = _new_clinic_with_staff_and_patient(client, "History")
    headers = _use_identity(client, clinic["staff"])
    response = client.post(
        "/api/v1/medical-records",
        json={"patient_id": clinic["patient_id"], "title": " Primeira ", "content": " Versão um "},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Primeira"
    record_id = response.json()["id"]
    updated = client.patch(
        f"/api/v1/medical-records/{record_id}", json={"content": "Versão dois"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    revisions = client.get(f"/api/v1/medical-records/{record_id}/revisions").json()
    assert [(item["version"], item["content"]) for item in revisions] == [(1, "Versão um")]
    assert client.post(
        "/api/v1/medical-records",
        json={"patient_id": clinic["patient_id"], "title": "   ", "content": "x"},
        headers=headers,
    ).status_code == 422
    assert client.patch(
        f"/api/v1/medical-records/{record_id}", json={"content": "x" * 20_001}, headers=headers
    ).status_code == 422


def test_staff_lifecycle_revokes_sessions_and_supports_reactivation(client):
    clinic = _new_clinic_with_staff_and_patient(client, "Lifecycle")
    admin_headers = _use_identity(client, clinic["admin"])
    renamed = client.patch(
        f"/api/v1/staff/{clinic['staff_id']}",
        json={"full_name": "Dra. Atualizada", "staff_role": "nurse"},
        headers=admin_headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["full_name"] == "Dra. Atualizada"
    assert renamed.json()["staff_role"] == "nurse"
    deactivated = client.post(
        f"/api/v1/staff/{clinic['staff_id']}/deactivate", headers=admin_headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    _use_identity(client, clinic["staff"])
    assert client.get("/api/v1/appointments").status_code == 401
    reactivated = client.post(
        f"/api/v1/staff/{clinic['staff_id']}/reactivate",
        headers=_use_identity(client, clinic["admin"]),
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True
    directory = client.get("/api/v1/staff?include_inactive=true")
    assert any(item["id"] == clinic["staff_id"] for item in directory.json())


def test_appointment_events_notify_patient_and_staff_and_lists_paginate(client):
    clinic = _new_clinic_with_staff_and_patient(client, "Events")
    created = client.post(
        "/api/v1/appointments",
        json={"patient_id": clinic["patient_id"], "staff_id": clinic["staff_id"], "scheduled_at": _future_iso()},
        headers=_use_identity(client, clinic["admin"]),
    )
    assert created.status_code == 201, created.text
    appointment_id = created.json()["id"]
    assert client.patch(
        f"/api/v1/appointments/{appointment_id}",
        json={"reason": "Alterada"},
        headers=_use_identity(client, clinic["admin"]),
    ).status_code == 200
    assert client.post(
        f"/api/v1/appointments/{appointment_id}/cancel",
        headers=_use_identity(client, clinic["admin"]),
    ).status_code == 200
    _use_identity(client, clinic["patient"])
    notifications = client.get("/api/v1/notifications?limit=3&offset=0")
    assert notifications.status_code == 200
    assert [item["kind"] for item in notifications.json()] == [
        "appointment_cancelled", "appointment_updated", "appointment_created"
    ]
    assert client.get("/api/v1/notifications?limit=101").status_code == 422
    _use_identity(client, clinic["admin"])
    assert client.get("/api/v1/patients?limit=1&offset=0").status_code == 200
    assert client.get("/api/v1/appointments?offset=-1").status_code == 422


def test_notification_content_limits_and_consent_has_no_mutation_routes(client):
    clinic = _new_clinic_with_staff_and_patient(client, "Limits")
    engine = create_engine(TEST_DATABASE_URL)
    with Session(engine) as db:
        recipient = db.query(User).filter(User.clinic_id == clinic["clinic_id"], User.role == "patient").one()
        with pytest.raises(ValueError, match="2000"):
            create_notification(db, recipient, "Aviso", "x" * 2_001, "clinical")
    engine.dispose()
    consent = client.post(
        "/api/v1/consents",
        json={
            "patient_id": clinic["patient_id"], "consent_type": "care", "status": "granted",
            "version": "1", "effective_at": _future_iso(),
        },
        headers=_use_identity(client, clinic["patient"]),
    )
    assert consent.status_code == 201
    consent_id = consent.json()["id"]
    assert client.patch(
        f"/api/v1/consents/{consent_id}", json={"status": "withdrawn"},
        headers=_use_identity(client, clinic["patient"]),
    ).status_code in {404, 405}
    assert client.delete(
        f"/api/v1/consents/{consent_id}", headers=_use_identity(client, clinic["patient"]),
    ).status_code in {404, 405}
