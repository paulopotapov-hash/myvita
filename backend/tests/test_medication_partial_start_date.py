"""Declared medication: optional, partial start date (step 1 after commit 3).

- The patient may omit the start date or give "2020", "2020-03" or "2020-03-12",
  and it comes back exactly so (never as a fabricated 01/01/2020).
- A professional must give a complete start date; on confirmation they may
  complete the patient's partial one.
- The database refuses incoherent rows; the migration keeps existing dates.
Synthetic data only.
"""

import uuid

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.clinical_support import Tenant, make_tenant
from tests.conftest import TEST_DATABASE_URL, alembic_config

PREVIOUS = "a0b1c2d3e4f5"


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"med-start-{uuid.uuid4().hex[:8]}")


def _url(tenant: Tenant) -> str:
    return f"/api/v1/patients/{tenant.patient_id}/medications"


@pytest.mark.parametrize("start", ["2020", "2020-03", "2020-03-12", None])
def test_patient_declares_with_an_optional_partial_start_date(client: TestClient, tenant: Tenant, start):
    body = {"name": "Declarada", **({"start_date": start} if start else {})}
    created = client.post(_url(tenant), headers=tenant.act(client, "patient"), json=body)
    assert created.status_code == 201, created.text
    assert created.json()["start_date"] == start
    listed = client.get(_url(tenant)).json()[0]
    assert listed["start_date"] == start
    tenant.act(client, "doctor")
    assert client.get(_url(tenant)).json()[0]["start_date"] == start


@pytest.mark.parametrize("start", ["2020-13", "2020-02-30", "1899", "20-03-2020", "abcd"])
def test_impossible_or_malformed_start_dates_are_refused(client: TestClient, tenant: Tenant, start: str):
    response = client.post(_url(tenant), headers=tenant.act(client, "patient"), json={"name": "X", "start_date": start})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "start_date"


def test_professionals_must_give_a_complete_start_date(client: TestClient, tenant: Tenant):
    headers = tenant.act(client, "doctor")
    for body in ({"name": "X", "dosage": "1 mg"}, {"name": "X", "dosage": "1 mg", "start_date": "2020-03"}):
        response = client.post(_url(tenant), headers=headers, json=body)
        assert response.status_code == 422, body
        assert response.json()["detail"][0]["loc"][-1] == "start_date"
    ok = client.post(_url(tenant), headers=headers, json={"name": "X", "dosage": "1 mg", "start_date": "2026-01-15"})
    assert ok.status_code == 201 and ok.json()["start_date"] == "2026-01-15"
    edit = client.patch(f"/api/v1/medications/{ok.json()['id']}", headers=headers, json={"start_date": "2026"})
    assert edit.status_code == 422


def test_patient_edits_own_declaration_date_and_the_professional_completes_it(client: TestClient, tenant: Tenant):
    declared = client.post(_url(tenant), headers=tenant.act(client, "patient"), json={"name": "Declarada", "start_date": "2020"}).json()
    headers = tenant.act(client, "patient")
    assert client.patch(f"/api/v1/medications/{declared['id']}", headers=headers, json={"start_date": "2020-03"}).json()["start_date"] == "2020-03"
    assert client.patch(f"/api/v1/medications/{declared['id']}", headers=headers, json={"start_date": None}).json()["start_date"] is None
    assert client.patch(f"/api/v1/medications/{declared['id']}", headers=headers, json={"start_date": "2020-03"}).status_code == 200

    confirmed = client.post(
        f"/api/v1/medications/{declared['id']}/confirm", headers=tenant.act(client, "doctor"), json={"start_date": "2020-03-12"}
    )
    assert confirmed.status_code == 200
    assert (confirmed.json()["start_date"], confirmed.json()["confirmed"]) == ("2020-03-12", True)


def test_confirmation_without_a_date_keeps_the_declared_precision(client: TestClient, tenant: Tenant):
    declared = client.post(_url(tenant), headers=tenant.act(client, "patient"), json={"name": "Declarada", "start_date": "2019"}).json()
    confirmed = client.post(f"/api/v1/medications/{declared['id']}/confirm", headers=tenant.act(client, "doctor"))
    assert confirmed.json()["start_date"] == "2019"
    # A finished declared medication with a partial start keeps working.
    finished = client.post(f"/api/v1/medications/{declared['id']}/deactivate", headers=tenant.act(client, "doctor"))
    assert finished.status_code == 200 and finished.json()["start_date"] == "2019"


def test_database_refuses_incoherent_start_dates(client: TestClient, tenant: Tenant):
    base = {"clinic": tenant.clinic_id, "patient": tenant.patient_id, "user": tenant.user_ids["patient"], "staff": tenant.staff_ids["doctor"]}
    statements = [
        # a year precision that is not the first day of the year
        "INSERT INTO medications (id, clinic_id, patient_id, name, status, start_date, start_precision, origin, declared_by_user_id) "
        "VALUES (:id, :clinic, :patient, 'X', 'active', '2020-03-12', 'year', 'patient_declared', :user)",
        # a date without precision
        "INSERT INTO medications (id, clinic_id, patient_id, name, status, start_date, origin, declared_by_user_id) "
        "VALUES (:id, :clinic, :patient, 'X', 'active', '2020-03-12', 'patient_declared', :user)",
        # a professional's medication with a partial start
        "INSERT INTO medications (id, clinic_id, patient_id, name, dosage, status, start_date, start_precision, origin, "
        "prescribed_by_staff_id, confirmed_by_staff_id, confirmed_at) VALUES (:id, :clinic, :patient, 'X', '1 mg', 'active', "
        "'2020-03-01', 'month', 'professional', :staff, :staff, now())",
    ]
    for statement in statements:
        with client.session_factory() as db:  # type: ignore[attr-defined]
            with pytest.raises(IntegrityError):
                db.execute(text(statement), {"id": uuid.uuid4(), **base})
                db.flush()


@pytest.fixture()
def engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    config = alembic_config()
    try:
        yield engine
    finally:
        command.upgrade(config, "head")
        engine.dispose()


def test_migration_keeps_existing_start_dates_and_downgrade_refuses_partial_ones(client: TestClient, engine, tenant: Tenant):
    prescribed = client.post(
        _url(tenant), headers=tenant.act(client, "doctor"), json={"name": "X", "dosage": "1 mg", "start_date": "2025-06-07"}
    ).json()
    command.downgrade(alembic_config(), PREVIOUS)
    command.upgrade(alembic_config(), "head")
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT start_date::text, start_precision::text FROM medications WHERE id = :id"), {"id": prescribed["id"]}
        ).one()
    assert tuple(row) == ("2025-06-07", "day")

    client.post(_url(tenant), headers=tenant.act(client, "patient"), json={"name": "Declarada", "start_date": "2020"})
    with pytest.raises(RuntimeError, match="Refusing to downgrade"):
        command.downgrade(alembic_config(), PREVIOUS)
    with engine.connect() as connection:
        (head,) = ScriptDirectory.from_config(alembic_config()).get_heads()
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == head
