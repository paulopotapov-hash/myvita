"""Migration 9a4c6e8f0b2d (cancellation and rescheduling) on a database that holds data:
existing appointments and requests keep every value; downgrade refuses while a request
uses a preference window. Every test leaves the database at head."""

import uuid

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.clinical_support import make_tenant
from tests.conftest import TEST_DATABASE_URL, alembic_config

PREVIOUS = "8e3f5a7c9b1d"


@pytest.fixture()
def engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        yield engine
    finally:
        command.upgrade(alembic_config(), "head")
        engine.dispose()


def test_existing_requests_and_appointments_survive_and_downgrade_guards_new_data(client: TestClient, engine):
    tenant = make_tenant(client, f"mig-step5-{uuid.uuid4().hex[:6]}")
    old_request = client.post(
        "/api/v1/appointment-requests", headers=tenant.act(client, "patient"), json={"preferred_start": "2030-05-06T09:00:00Z", "reason": "X"}
    )
    assert old_request.status_code == 201, old_request.text
    command.downgrade(alembic_config(), PREVIOUS)
    command.upgrade(alembic_config(), "head")
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT preferred_start, reason, status::text, preferred_from FROM appointment_requests WHERE id = :id"),
            {"id": old_request.json()["id"]},
        ).one()
    assert (row.reason, row.status, row.preferred_from) == ("X", "pending", None)
    assert row.preferred_start.isoformat().startswith("2030-05-06T09:00:00")

    window = client.post(
        "/api/v1/appointment-requests", headers=tenant.act(client, "other_patient"), json={"preferred_from": "2030-01-01"}
    )
    # Beyond the booking horizon: refused by the API; insert it directly to test the guard.
    assert window.status_code == 422
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO appointment_requests (id, clinic_id, patient_id, preferred_from, status) "
                "VALUES (:id, :clinic, :patient, CURRENT_DATE + 1, 'pending')"
            ),
            {"id": uuid.uuid4(), "clinic": tenant.clinic_id, "patient": tenant.other_patient_id},
        )
    with pytest.raises(RuntimeError, match="Refusing to downgrade"):
        command.downgrade(alembic_config(), PREVIOUS)
