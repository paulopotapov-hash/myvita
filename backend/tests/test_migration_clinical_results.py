"""Migration 6b7c8d9e0f1a (P2.4-P2.6) on a database that holds data.

- Upgrade keeps every pre-existing record readable by its patient as
  `legacy_shared`, without inventing a sharing decision and without notifying.
- Downgrade refuses, changing nothing, when the previous schema would expose an
  internal record or revision to the patient or delete clinical results.
- Otherwise downgrade keeps every record, revision and notification.

Every test leaves the database at head.
"""

import uuid

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.clinical_support import Tenant, make_tenant
from tests.conftest import TEST_DATABASE_URL, alembic_config

PREVIOUS = "5a6b7c8d9e0f"
THIS = "6b7c8d9e0f1a"  # the migration under test; later revisions are stepped down first


@pytest.fixture()
def engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    config = alembic_config()
    try:
        yield engine
    finally:
        command.upgrade(config, "head")
        with engine.connect() as connection:
            (head,) = ScriptDirectory.from_config(config).get_heads()
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == head
        engine.dispose()


def _count(engine, sql: str) -> int:
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


def _version(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _create_record(client: TestClient, tenant: Tenant, **extra) -> dict:
    response = client.post(
        f"/api/v1/patients/{tenant.patient_id}/medical-records",
        headers=tenant.act(client, "doctor"),
        json={"title": "Nota", "content": "Conteúdo", **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upgrade_backfills_existing_records_as_legacy_access_without_notifying(client: TestClient, engine):
    tenant = make_tenant(client, "migration-up")
    config = alembic_config()
    command.downgrade(config, PREVIOUS)
    record_id = uuid.uuid4()
    with engine.begin() as connection:
        # A record as it existed before P2.5: readable by its patient, edited once.
        connection.execute(
            text(
                "INSERT INTO medical_records (id, clinic_id, patient_id, author_staff_id, title, content, version) "
                "VALUES (:id, :clinic, :patient, :staff, 'Antiga', 'Nota antiga', 2)"
            ),
            {"id": record_id, "clinic": tenant.clinic_id, "patient": tenant.patient_id, "staff": tenant.staff_ids["doctor"]},
        )
        for version in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO medical_record_revisions (id, record_id, editor_staff_id, version, title, content) "
                    "VALUES (:id, :record, :staff, :version, 'Antiga', 'Nota antiga')"
                ),
                {"id": uuid.uuid4(), "record": record_id, "staff": tenant.staff_ids["doctor"], "version": version},
            )
    notifications_before = _count(engine, "SELECT count(*) FROM notifications")

    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT patient_visibility, visibility_changed_at, visibility_changed_by_staff_id "
                "FROM medical_records WHERE id = :id"
            ),
            {"id": record_id},
        ).one()
    assert tuple(row) == ("legacy_shared", None, None)
    assert _count(engine, "SELECT count(*) FROM medical_record_revisions WHERE patient_visibility = 'legacy_shared'") == 2
    assert _count(engine, "SELECT count(*) FROM notifications") == notifications_before

    # The patient keeps reading it through the API; new records start internal.
    tenant.act(client, "patient")
    assert client.get(f"/api/v1/medical-records/{record_id}").status_code == 200
    assert _create_record(client, tenant)["visibility"] == "internal"


@pytest.mark.parametrize("blocker", ["internal_record", "internal_revision", "clinical_result"])
def test_downgrade_refuses_to_expose_or_delete_clinical_data(client: TestClient, engine, blocker: str):
    tenant = make_tenant(client, f"migration-{blocker.replace('_', '-')}")
    if blocker == "internal_record":
        _create_record(client, tenant)
    elif blocker == "internal_revision":
        # Shared now, but version 1 was an internal note the old revisions endpoint would expose.
        record = _create_record(client, tenant)
        shared = client.post(
            f"/api/v1/medical-records/{record['id']}/share",
            headers=tenant.act(client, "doctor"),
            json={"expected_version": 1},
        )
        assert shared.status_code == 200, shared.text
    else:
        released = client.post(
            f"/api/v1/patients/{tenant.patient_id}/results",
            headers=tenant.act(client, "doctor"),
            json={"category": "laboratory", "title": "Hb", "value": "13", "result_date": "2026-01-01", "release": True},
        )
        assert released.status_code == 201, released.text
    counts = {
        table: _count(engine, f"SELECT count(*) FROM {table}")
        for table in ("medical_records", "medical_record_revisions", "clinical_results", "notifications")
    }

    command.downgrade(alembic_config(), THIS)
    with pytest.raises(RuntimeError, match="Refusing to downgrade 6b7c8d9e0f1a"):
        command.downgrade(alembic_config(), PREVIOUS)

    assert _version(engine) == THIS
    for table, before in counts.items():
        assert _count(engine, f"SELECT count(*) FROM {table}") == before, table


def test_downgrade_without_blockers_keeps_records_revisions_and_notifications(client: TestClient, engine):
    tenant = make_tenant(client, "migration-down")
    _create_record(client, tenant, share_with_patient=True)
    notifications_before = _count(engine, "SELECT count(*) FROM notifications")
    assert _count(engine, "SELECT count(*) FROM notifications WHERE target_type = 'medical_record'") == 1

    config = alembic_config()
    command.downgrade(config, PREVIOUS)
    assert _version(engine) == PREVIOUS
    assert _count(engine, "SELECT count(*) FROM medical_records") == 1
    assert _count(engine, "SELECT count(*) FROM medical_record_revisions") == 1
    # The notification keeps its row and generic text; only its target is cleared.
    assert _count(engine, "SELECT count(*) FROM notifications") == notifications_before
    assert _count(
        engine,
        "SELECT count(*) FROM notifications WHERE title = 'Nova informação clínica partilhada' AND target_type IS NULL",
    ) == 1

    command.upgrade(config, "head")
    # After a round trip the record is readable as before, recorded as legacy access.
    assert _count(engine, "SELECT count(*) FROM medical_records WHERE patient_visibility = 'legacy_shared'") == 1
    assert _count(engine, "SELECT count(*) FROM notifications") == notifications_before
