"""Migration a0b1c2d3e4f5 (commit 3, clinical history) on a database that holds data.

- Upgrade keeps every existing medication and marks it as confirmed by its
  prescriber at its creation time; nothing else changes.
- Downgrade refuses, changing nothing, while clinical history entries or
  patient-declared medications exist (it would have to delete clinical data).

Every test leaves the database at head.
"""

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.clinical_support import make_tenant
from tests.conftest import TEST_DATABASE_URL, alembic_config

PREVIOUS = "9e0f1a2b3c4d"
THIS = "a0b1c2d3e4f5"


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


def _prescribe(client: TestClient, tenant) -> str:
    response = client.post(
        f"/api/v1/patients/{tenant.patient_id}/medications",
        headers=tenant.act(client, "doctor"),
        json={"name": "Medicamento sintético", "dosage": "5 mg", "start_date": "2026-01-01"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_upgrade_keeps_existing_medication_as_confirmed_by_its_prescriber(client: TestClient, engine):
    tenant = make_tenant(client, "migration-history-up")
    medication_id = _prescribe(client, tenant)
    config = alembic_config()
    command.downgrade(config, PREVIOUS)
    with engine.connect() as connection:
        before = connection.execute(
            text("SELECT name, dosage, status, start_date, created_at, prescribed_by_staff_id FROM medications WHERE id = :id"),
            {"id": medication_id},
        ).one()
    command.upgrade(config, THIS)
    with engine.connect() as connection:
        after = connection.execute(
            text(
                "SELECT name, dosage, status, start_date, created_at, prescribed_by_staff_id, origin, "
                "confirmed_at, confirmed_by_staff_id, hidden_at, deleted_at FROM medications WHERE id = :id"
            ),
            {"id": medication_id},
        ).one()
    assert tuple(after[:6]) == tuple(before)
    assert after.origin == "professional"
    assert after.confirmed_at == before.created_at
    assert after.confirmed_by_staff_id == before.prescribed_by_staff_id
    assert after.hidden_at is None and after.deleted_at is None


@pytest.mark.parametrize("kind", ["history_entry", "declared_medication"])
def test_downgrade_refuses_while_new_clinical_data_exists(client: TestClient, engine, kind: str):
    tenant = make_tenant(client, f"migration-history-down-{kind}")
    if kind == "history_entry":
        url = f"/api/v1/patients/{tenant.patient_id}/clinical-history"
        body = {"category": "note", "note_text": "Nota clínica sintética"}
    else:
        url = f"/api/v1/patients/{tenant.patient_id}/medications"
        body = {"name": "Declarado", "start_date": "2026-01-01"}
    assert client.post(url, headers=tenant.act(client, "patient"), json=body).status_code == 201

    with pytest.raises(RuntimeError, match="Refusing to downgrade"):
        command.downgrade(alembic_config(), PREVIOUS)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == THIS
        assert connection.execute(text("SELECT count(*) FROM clinical_history_entries")).scalar() + connection.execute(
            text("SELECT count(*) FROM medications WHERE origin = 'patient_declared'")
        ).scalar() == 1
