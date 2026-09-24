import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models import AuditAction, AuditLog
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture()
def client():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.test_session = test_session
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _identity(response) -> dict[str, str]:
    session = response.cookies.get(settings.COOKIE_NAME)
    csrf = response.cookies.get(settings.CSRF_COOKIE_NAME)
    assert session and csrf
    return {"session": session, "csrf": csrf}


def _use(client: TestClient, identity: dict[str, str]) -> dict[str, str]:
    client.cookies.set(settings.COOKIE_NAME, identity["session"])
    client.cookies.set(settings.CSRF_COOKIE_NAME, identity["csrf"])
    return {settings.CSRF_HEADER_NAME: identity["csrf"]}


def _tenant(client: TestClient, suffix: str) -> dict:
    response = client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": f"Clínica Consent {suffix}",
            "admin_full_name": f"Admin {suffix}",
            "admin_email": f"consent-admin-{suffix}@example.pt",
            "admin_password": "SenhaForte123!",
        },
    )
    assert response.status_code == 201
    admin = _identity(response)
    clinic_id = response.json()["id"]
    response = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": f"Patient {suffix}",
            "email": f"consent-patient-{suffix}@example.pt",
            "password": "SenhaForte123!",
        },
    )
    assert response.status_code == 201
    return {
        "clinic_id": clinic_id,
        "admin": admin,
        "patient": _identity(response),
        "patient_id": response.json()["id"],
    }


def _grant(client: TestClient, tenant: dict, purpose: str = "Provide clinical treatment"):
    headers = _use(client, tenant["admin"])
    return client.post(
        f"/api/v1/patients/{tenant['patient_id']}/consents",
        json={"consent_type": "treatment", "purpose": purpose},
        headers=headers,
    )


def test_authorized_creation_validation_and_audit(client: TestClient):
    tenant = _tenant(client, "create")
    response = _grant(client, tenant)
    assert response.status_code == 201
    body = response.json()
    assert body["clinic_id"] == tenant["clinic_id"]
    assert body["status"] == "granted"
    assert body["revoked_at"] is None

    duplicate = _grant(client, tenant)
    assert duplicate.status_code == 409
    invalid = client.post(
        f"/api/v1/patients/{tenant['patient_id']}/consents",
        json={"consent_type": "anything", "purpose": "   "},
        headers=_use(client, tenant["admin"]),
    )
    assert invalid.status_code == 422

    db = client.test_session()
    try:
        audit = db.query(AuditLog).filter(AuditLog.action == AuditAction.CONSENT_GRANTED).one()
        assert audit.event_metadata is None
    finally:
        db.close()


def test_patient_can_view_grant_and_revoke_own_consent(client: TestClient):
    tenant = _tenant(client, "self")
    consent_id = _grant(client, tenant).json()["id"]
    _use(client, tenant["patient"])
    listed = client.get(f"/api/v1/patients/{tenant['patient_id']}/consents")
    detail = client.get(f"/api/v1/consents/{consent_id}")
    assert listed.status_code == detail.status_code == 200
    assert [item["id"] for item in listed.json()] == [consent_id]

    revoked = client.post(
        f"/api/v1/consents/{consent_id}/revoke",
        headers=_use(client, tenant["patient"]),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["revoked_at"] is not None
    assert client.get(f"/api/v1/consents/{consent_id}").status_code == 200
    repeated = client.post(
        f"/api/v1/consents/{consent_id}/revoke",
        headers=_use(client, tenant["patient"]),
    )
    assert repeated.status_code == 409


def test_patient_cannot_access_another_patient_in_same_clinic(client: TestClient):
    tenant = _tenant(client, "owner")
    _use(client, tenant["patient"])
    response = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": tenant["clinic_id"],
            "full_name": "Second Patient",
            "email": "second-patient@example.pt",
            "password": "SenhaForte123!",
        },
    )
    other_id = response.json()["id"]
    assert (
        client.get(
            f"/api/v1/patients/{other_id}/consents",
            cookies={settings.COOKIE_NAME: tenant["patient"]["session"]},
        ).status_code
        == 404
    )


def test_cross_tenant_create_read_and_revoke_are_hidden(client: TestClient):
    first = _tenant(client, "tenant-a")
    second = _tenant(client, "tenant-b")
    consent_id = _grant(client, first).json()["id"]
    headers = _use(client, second["admin"])
    assert (
        client.post(
            f"/api/v1/patients/{first['patient_id']}/consents",
            json={"consent_type": "research", "purpose": "Research cohort"},
            headers=headers,
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/consents/{consent_id}").status_code == 404
    assert (
        client.post(f"/api/v1/consents/{consent_id}/revoke", headers=headers).status_code == 404
    )


def test_unknown_patient_and_invalid_uuid_are_rejected(client: TestClient):
    tenant = _tenant(client, "invalid")
    headers = _use(client, tenant["admin"])
    assert (
        client.post(
            f"/api/v1/patients/{uuid.uuid4()}/consents",
            json={"consent_type": "research", "purpose": "Approved study"},
            headers=headers,
        ).status_code
        == 404
    )
    assert client.get("/api/v1/consents/not-a-uuid").status_code == 422
