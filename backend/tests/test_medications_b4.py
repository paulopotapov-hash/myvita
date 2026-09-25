"""B4 medication management: lifecycle, validation, RBAC, tenant isolation, and audit."""

# ruff: noqa: F401, F811
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import AuditAction, AuditLog, Medication, MedicationStatus
from tests.conftest import TEST_DATABASE_URL
from tests.test_clinical_contracts_b6 import _tenant, _use, client


@pytest.fixture(scope="module", autouse=True)
def _restore_schema_after_module():
    """The shared B6 client drops all tables; restore them for later test modules."""
    yield
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()


def _payload() -> dict:
    return {
        "name": " Amoxicilina ",
        "dosage": "500 mg",
        "route": "oral",
        "frequency": "8/8 horas",
        "instructions": "Tomar após refeição",
        "start_date": date.today().isoformat(),
    }


def test_clinical_staff_can_manage_and_deactivate_medication(client):
    tenant = _tenant(client, "b4-flow")
    headers = _use(client, tenant["doctor"])
    created = client.post(
        f"/api/v1/patients/{tenant['patient_id']}/medications",
        headers=headers,
        json=_payload(),
    )
    assert created.status_code == 201, created.text
    medication_id = created.json()["id"]
    assert created.json()["name"] == "Amoxicilina"
    assert created.json()["frequency"] == "8/8 horas"

    detail = client.get(f"/api/v1/medications/{medication_id}")
    assert detail.status_code == 200
    listed = client.get(
        f"/api/v1/patients/{tenant['patient_id']}/medications?status=active&page=1&page_size=1"
    )
    assert listed.status_code == 200
    assert listed.headers["x-total-count"] == "1"
    assert [item["id"] for item in listed.json()] == [medication_id]

    updated = client.patch(
        f"/api/v1/medications/{medication_id}",
        headers=headers,
        json={"frequency": "12/12 horas", "route": "sublingual"},
    )
    assert updated.status_code == 200
    assert updated.json()["frequency"] == "12/12 horas"
    stopped = client.post(f"/api/v1/medications/{medication_id}/deactivate", headers=headers)
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "discontinued"
    assert stopped.json()["end_date"] is not None
    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 200
    assert client.get(
        f"/api/v1/patients/{tenant['patient_id']}/medications?status=active"
    ).json() == []


def test_patient_and_admin_are_read_only_for_medications(client):
    tenant = _tenant(client, "b4-rbac")
    created = client.post(
        f"/api/v1/patients/{tenant['patient_id']}/medications",
        headers=_use(client, tenant["doctor"]),
        json=_payload(),
    )
    medication_id = created.json()["id"]

    patient_headers = _use(client, tenant["patient"])
    assert client.get(f"/api/v1/patients/{tenant['patient_id']}/medications").status_code == 200
    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 200
    assert client.post(
        f"/api/v1/patients/{tenant['patient_id']}/medications",
        headers=patient_headers,
        json=_payload(),
    ).status_code in {403, 404}
    assert client.patch(
        f"/api/v1/medications/{medication_id}",
        headers=patient_headers,
        json={"dosage": "1 g"},
    ).status_code in {403, 404}
    assert client.post(
        f"/api/v1/medications/{medication_id}/deactivate", headers=patient_headers
    ).status_code in {403, 404}

    assert client.post(
        f"/api/v1/patients/{tenant['patient_id']}/medications",
        headers=_use(client, tenant["admin"]),
        json=_payload(),
    ).status_code == 403


def test_tenant_isolation_validation_history_and_safe_audit(client):
    first = _tenant(client, "b4-tenant-a")
    second = _tenant(client, "b4-tenant-b")
    created = client.post(
        f"/api/v1/patients/{first['patient_id']}/medications",
        headers=_use(client, first["doctor"]),
        json=_payload(),
    )
    medication_id = created.json()["id"]
    second_headers = _use(client, second["doctor"])
    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 404
    assert client.post(
        f"/api/v1/patients/{first['patient_id']}/medications",
        headers=second_headers,
        json=_payload(),
    ).status_code == 404
    assert client.patch(
        f"/api/v1/medications/{medication_id}",
        headers=second_headers,
        json={"dosage": "1 g"},
    ).status_code == 404

    first_headers = _use(client, first["doctor"])
    assert client.patch(
        f"/api/v1/medications/{medication_id}", headers=first_headers, json={}
    ).status_code == 422
    assert client.patch(
        f"/api/v1/medications/{medication_id}",
        headers=first_headers,
        json={"patient_id": second["patient_id"]},
    ).status_code == 422
    invalid = _payload() | {"end_date": (date.today() - timedelta(days=1)).isoformat()}
    assert client.post(
        f"/api/v1/patients/{first['patient_id']}/medications",
        headers=first_headers,
        json=invalid,
    ).status_code == 422
    assert client.get("/api/v1/medications/not-a-uuid").status_code == 422

    db: Session = client.test_session()
    try:
        medication = db.get(Medication, medication_id)
        assert medication is not None
        assert medication.patient_id.hex == first["patient_id"].replace("-", "")
        assert medication.status == MedicationStatus.ACTIVE
        events = db.query(AuditLog).filter(AuditLog.resource_id == medication.id).all()
        assert {event.action for event in events} >= {
            AuditAction.MEDICATION_CREATED,
            AuditAction.PERMISSION_DENIED,
        }
        assert all(
            not event.event_metadata or "Tomar após refeição" not in str(event.event_metadata)
            for event in events
        )
    finally:
        db.close()
