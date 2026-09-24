"""B4 medication-management API, authorization, isolation, and audit tests."""
# ruff: noqa: F401, F811

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import AuditAction, AuditLog, Medication
from tests.conftest import TEST_DATABASE_URL
from tests.test_appointments_integration import (
    _new_clinic_with_staff_and_patient,
    _use_identity,
    client,
)


def _payload() -> dict:
    return {
        "name": " Amoxicilina ",
        "dosage": "500 mg",
        "route": "oral",
        "frequency": "8/8 horas",
        "instructions": "Tomar após refeição",
        "start_date": date.today().isoformat(),
    }


def test_doctor_can_create_read_update_filter_and_deactivate(client):
    clinic = _new_clinic_with_staff_and_patient(client, "MedicationFlow")
    headers = _use_identity(client, clinic["staff"])
    created = client.post(
        f"/api/v1/patients/{clinic['patient_id']}/medications",
        json=_payload(),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    medication_id = body["id"]
    assert body["name"] == "Amoxicilina"
    assert body["created_by_user_id"] is not None
    assert "clinic_id" not in body

    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 200
    assert len(client.get(f"/api/v1/patients/{clinic['patient_id']}/medications?is_active=true").json()) == 1
    updated = client.patch(
        f"/api/v1/medications/{medication_id}",
        json={"frequency": "12/12 horas", "route": "sublingual"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["frequency"] == "12/12 horas"
    stopped = client.post(f"/api/v1/medications/{medication_id}/deactivate", headers=headers)
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["is_active"] is False
    assert stopped.json()["end_date"] is not None
    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 200
    assert client.get(f"/api/v1/patients/{clinic['patient_id']}/medications?is_active=true").json() == []
    assert len(client.get(f"/api/v1/patients/{clinic['patient_id']}/medications?is_active=false").json()) == 1


def test_patient_is_read_only_and_cannot_view_another_patient(client):
    a = _new_clinic_with_staff_and_patient(client, "MedicationPatientA")
    b = _new_clinic_with_staff_and_patient(client, "MedicationPatientB")
    created = client.post(
        f"/api/v1/patients/{a['patient_id']}/medications",
        json=_payload(),
        headers=_use_identity(client, a["staff"]),
    )
    medication_id = created.json()["id"]
    patient_headers = _use_identity(client, a["patient"])
    assert client.get(f"/api/v1/patients/{a['patient_id']}/medications").status_code == 200
    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 200
    assert client.get(f"/api/v1/patients/{b['patient_id']}/medications").status_code == 404
    assert client.post(
        f"/api/v1/patients/{a['patient_id']}/medications", json=_payload(), headers=patient_headers
    ).status_code == 403
    assert client.patch(
        f"/api/v1/medications/{medication_id}", json={"frequency": "daily"}, headers=patient_headers
    ).status_code == 403
    assert client.post(
        f"/api/v1/medications/{medication_id}/deactivate", headers=patient_headers
    ).status_code == 403


def test_tenant_guards_validation_immutability_and_safe_audit(client):
    a = _new_clinic_with_staff_and_patient(client, "MedicationTenantA")
    b = _new_clinic_with_staff_and_patient(client, "MedicationTenantB")
    created = client.post(
        f"/api/v1/patients/{a['patient_id']}/medications",
        json=_payload(),
        headers=_use_identity(client, a["staff"]),
    )
    medication_id = created.json()["id"]
    b_headers = _use_identity(client, b["staff"])
    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 404
    assert client.post(
        f"/api/v1/patients/{a['patient_id']}/medications", json=_payload(), headers=b_headers
    ).status_code == 404
    assert client.patch(
        f"/api/v1/medications/{medication_id}", json={"frequency": "daily"}, headers=b_headers
    ).status_code == 404

    a_headers = _use_identity(client, a["staff"])
    assert client.patch(f"/api/v1/medications/{medication_id}", json={}, headers=a_headers).status_code == 422
    assert client.patch(
        f"/api/v1/medications/{medication_id}", json={"patient_id": b["patient_id"]}, headers=a_headers
    ).status_code == 422
    invalid = _payload() | {"end_date": (date.today() - timedelta(days=1)).isoformat()}
    assert client.post(
        f"/api/v1/patients/{a['patient_id']}/medications", json=invalid, headers=a_headers
    ).status_code == 422
    assert client.get("/api/v1/medications/not-a-uuid").status_code == 422

    engine = create_engine(TEST_DATABASE_URL)
    with Session(engine) as db:
        item = db.get(Medication, medication_id)
        assert item is not None and item.patient_id.hex == a["patient_id"].replace("-", "")
        events = db.query(AuditLog).filter(AuditLog.resource_id == item.id).all()
        assert {event.action for event in events} >= {
            AuditAction.MEDICATION_CREATED,
            AuditAction.PERMISSION_DENIED,
        }
        assert all(
            not event.event_metadata
            or "Tomar após refeição" not in str(event.event_metadata)
            for event in events
        )
    engine.dispose()
