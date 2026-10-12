"""Migration 8e3f5a7c9b1d on a database that holds data: a link a booking created gets that
appointment as its origin (from the audit trail); a link assigned by an admin stays without
one. Every test leaves the database at head."""

import uuid

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.clinical_support import make_tenant
from tests.conftest import TEST_DATABASE_URL, alembic_config

PREVIOUS = "7d2e4b9a1c3f"


@pytest.fixture()
def engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        yield engine
    finally:
        command.upgrade(alembic_config(), "head")
        engine.dispose()


def test_upgrade_backfills_the_origin_of_links_created_by_a_booking(client: TestClient, engine):
    tenant = make_tenant(client, f"mig-origin-{uuid.uuid4().hex[:6]}")
    booked = client.post(
        "/api/v1/appointments",
        headers=tenant.act(client, "admin"),
        json={"patient_id": tenant.other_patient_id, "staff_id": tenant.staff_ids["doctor"], "scheduled_at": "2030-05-06T10:00:00Z"},
    )
    assert booked.status_code == 201, booked.text

    command.downgrade(alembic_config(), PREVIOUS)
    command.upgrade(alembic_config(), "head")

    with engine.connect() as connection:
        rows = dict(
            connection.execute(
                text("SELECT patient_id::text, origin_appointment_id::text FROM clinical_care_assignments WHERE staff_id = :staff"),
                {"staff": tenant.staff_ids["doctor"]},
            ).all()
        )
    assert rows[tenant.other_patient_id] == booked.json()["id"]
    assert rows[tenant.patient_id] is None  # assigned by the clinic admin
