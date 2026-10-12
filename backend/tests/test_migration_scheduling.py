"""Migration 7d2e4b9a1c3f (scheduling) on a database that holds data.

- Existing free-text specialties become one specialty per name and clinic, linked to the staff.
- Existing appointments get ends_at = scheduled_at + duration, no type, booked_via "staff".
- If active appointments already overlap, the upgrade refuses and changes nothing.
- Downgrade refuses while scheduling configuration exists.
Every test leaves the database at head.
"""

import uuid

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.clinical_support import make_tenant
from tests.conftest import TEST_DATABASE_URL, alembic_config
from tests.scheduling_support import setup_booking

PREVIOUS = "5f3a9c1e7b2d"
THIS = "7d2e4b9a1c3f"


@pytest.fixture()
def engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        yield engine
    finally:
        command.upgrade(alembic_config(), "head")
        engine.dispose()


def _version(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _insert_old_appointment(connection, tenant, start: str, patient: str, status: str = "scheduled") -> uuid.UUID:
    appointment_id = uuid.uuid4()
    connection.execute(
        text(
            "INSERT INTO appointments (id, clinic_id, patient_id, staff_id, scheduled_at, duration_minutes, status) "
            "VALUES (:id, :clinic, :patient, :staff, :start, 45, :status)"
        ),
        {"id": appointment_id, "clinic": tenant.clinic_id, "patient": patient, "staff": tenant.staff_ids["doctor"], "start": start, "status": status},
    )
    return appointment_id


def test_upgrade_backfills_specialties_and_appointment_end_times(client: TestClient, engine):
    tenant = make_tenant(client, f"mig-sched-{uuid.uuid4().hex[:6]}")
    command.downgrade(alembic_config(), PREVIOUS)
    with engine.begin() as connection:
        connection.execute(text("UPDATE staff SET specialty = '  Cardiologia ' WHERE id IN (:doctor, :nurse)"),
                           {"doctor": tenant.staff_ids["doctor"], "nurse": tenant.staff_ids["nurse"]})
        appointment_id = _insert_old_appointment(connection, tenant, "2030-05-06T10:00:00Z", tenant.patient_id)
    command.upgrade(alembic_config(), "head")
    with engine.connect() as connection:
        specialties = connection.execute(text("SELECT id, name FROM specialties WHERE clinic_id = :clinic"), {"clinic": tenant.clinic_id}).all()
        assert [name for _id, name in specialties] == ["Cardiologia"]
        linked = connection.execute(
            text("SELECT count(*) FROM staff WHERE specialty_id = :id AND accepts_new_patients"), {"id": specialties[0][0]}
        ).scalar_one()
        assert linked == 2
        row = connection.execute(
            text("SELECT ends_at - scheduled_at, appointment_type_id, booked_via::text FROM appointments WHERE id = :id"),
            {"id": appointment_id},
        ).one()
    assert row[0].total_seconds() == 45 * 60 and row[1] is None and row[2] == "staff"


def test_upgrade_refuses_when_active_appointments_already_overlap(client: TestClient, engine):
    tenant = make_tenant(client, f"mig-sched-ovl-{uuid.uuid4().hex[:6]}")
    command.downgrade(alembic_config(), PREVIOUS)
    with engine.begin() as connection:
        _insert_old_appointment(connection, tenant, "2030-05-06T10:00:00Z", tenant.patient_id)
        _insert_old_appointment(connection, tenant, "2030-05-06T10:15:00Z", tenant.other_patient_id)
    with pytest.raises(RuntimeError, match="already overlap for the same professional"):
        command.upgrade(alembic_config(), THIS)
    assert _version(engine) == PREVIOUS
    with engine.begin() as connection:
        # Resolving it (cancelling one) lets the upgrade through; nothing was lost meanwhile.
        assert connection.execute(text("SELECT count(*) FROM appointments WHERE clinic_id = :c"), {"c": tenant.clinic_id}).scalar_one() == 2
        connection.execute(text("UPDATE appointments SET status = 'cancelled' WHERE clinic_id = :c AND scheduled_at = '2030-05-06T10:15:00Z'"), {"c": tenant.clinic_id})
    command.upgrade(alembic_config(), "head")


def test_downgrade_refuses_while_scheduling_configuration_exists(client: TestClient, engine):
    tenant = make_tenant(client, f"mig-sched-down-{uuid.uuid4().hex[:6]}")
    setup_booking(client, tenant)
    with pytest.raises(RuntimeError, match="Refusing to downgrade"):
        command.downgrade(alembic_config(), PREVIOUS)
    (head,) = ScriptDirectory.from_config(alembic_config()).get_heads()
    assert _version(engine) == head
