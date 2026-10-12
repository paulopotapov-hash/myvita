"""Hidden entries are hidden from the patient only (D4).

While a clinical history entry or a medication is hidden, every professional with access to
the patient (doctor and nurse, whoever hid it) still sees it, in the list and in the
detail, marked as hidden with its reason. For the patient it does not exist on any
endpoint: list, detail, revisions, edit, delete. Synthetic data only.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.clinical_support import Tenant, make_tenant

CLINICIANS = ("doctor", "nurse")


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"hidden-{uuid.uuid4().hex[:8]}")


def _history(tenant: Tenant) -> str:
    return f"/api/v1/patients/{tenant.patient_id}/clinical-history"


def _medications(tenant: Tenant) -> str:
    return f"/api/v1/patients/{tenant.patient_id}/medications"


@pytest.mark.parametrize("hidden_by", CLINICIANS)
def test_a_hidden_history_entry_stays_visible_to_every_clinician(client: TestClient, tenant: Tenant, hidden_by: str):
    declared = client.post(
        _history(tenant), headers=tenant.act(client, "patient"), json={"category": "allergy", "name": "Alergia sintética", "severity": "moderate"}
    )
    assert declared.status_code == 201, declared.text
    entry_id = declared.json()["id"]
    hidden = client.post(
        f"/api/v1/clinical-history/{entry_id}/hide",
        headers=tenant.act(client, hidden_by),
        json={"expected_version": 1, "reason": "Motivo sintético"},
    )
    assert hidden.status_code == 200, hidden.text

    for role in CLINICIANS:
        tenant.act(client, role)
        listed = [row for row in client.get(_history(tenant)).json() if row["id"] == entry_id]
        assert [(row["hidden"], row["hidden_reason"]) for row in listed] == [(True, "Motivo sintético")], role
        detail = client.get(f"/api/v1/clinical-history/{entry_id}")
        assert detail.status_code == 200 and detail.json()["hidden"] is True, role
        assert client.get(f"/api/v1/clinical-history/{entry_id}/revisions").status_code == 200, role

    headers = tenant.act(client, "patient")
    assert all(row["id"] != entry_id for row in client.get(_history(tenant)).json())
    assert client.get(f"/api/v1/clinical-history/{entry_id}").status_code == 404
    assert client.get(f"/api/v1/clinical-history/{entry_id}/revisions").status_code == 404
    # Even their own unconfirmed declaration: it cannot be edited or deleted while hidden.
    assert client.patch(
        f"/api/v1/clinical-history/{entry_id}", headers=headers, json={"name": "X", "expected_version": 2}
    ).status_code == 404
    assert client.post(
        f"/api/v1/clinical-history/{entry_id}/delete", headers=headers, json={"expected_version": 2}
    ).status_code == 404


@pytest.mark.parametrize("hidden_by", CLINICIANS)
def test_a_hidden_medication_stays_visible_to_every_clinician(client: TestClient, tenant: Tenant, hidden_by: str):
    declared = client.post(_medications(tenant), headers=tenant.act(client, "patient"), json={"name": "Medicação sintética"})
    assert declared.status_code == 201, declared.text
    medication_id = declared.json()["id"]
    hidden = client.post(
        f"/api/v1/medications/{medication_id}/hide", headers=tenant.act(client, hidden_by), json={"reason": "Motivo sintético"}
    )
    assert hidden.status_code == 200, hidden.text

    for role in CLINICIANS:
        tenant.act(client, role)
        listed = [row for row in client.get(_medications(tenant)).json() if row["id"] == medication_id]
        assert [(row["hidden"], row["hidden_reason"]) for row in listed] == [(True, "Motivo sintético")], role
        detail = client.get(f"/api/v1/medications/{medication_id}")
        assert detail.status_code == 200 and detail.json()["hidden"] is True, role

    headers = tenant.act(client, "patient")
    assert all(row["id"] != medication_id for row in client.get(_medications(tenant)).json())
    assert client.get(f"/api/v1/medications/{medication_id}").status_code == 404
    assert client.patch(f"/api/v1/medications/{medication_id}", headers=headers, json={"frequency": "SOS"}).status_code == 404
    assert client.post(f"/api/v1/medications/{medication_id}/delete", headers=headers).status_code == 404
