"""Step 8: rate limits per user (not per IP), per account at login, and per module.

Every TestClient request comes from the same IP ("testclient"), so these tests are also
the "two users behind one clinic IP" case: one user reaching a limit never blocks another.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.rate_limit import ACCOUNT_LOCKED, TOO_MANY, limiter, user_or_ip
from app.models import AuditAction, AuditLog
from tests.clinical_support import PASSWORD, Tenant, make_tenant


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, f"limits-{uuid.uuid4().hex[:8]}")


def _limited_audits(client: TestClient) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(AuditLog).filter(AuditLog.action == AuditAction.RATE_LIMITED).all()


def test_the_key_is_the_session_user_and_the_ip_only_without_a_session(client: TestClient, tenant: Tenant):
    def request(cookies: dict[str, str]) -> Request:
        header = "; ".join(f"{name}={value}" for name, value in cookies.items())
        return Request({"type": "http", "headers": [(b"cookie", header.encode())] if header else [], "client": ("10.0.0.7", 1234)})

    tenant.act(client, "patient")
    session = {name: value for name, value in client.cookies.items()}
    assert user_or_ip(request(session)) == f"user:{tenant.user_ids['patient']}"
    assert user_or_ip(request({})) == "ip:10.0.0.7"
    assert user_or_ip(request({next(iter(session)): "forged.token.value"})) == "ip:10.0.0.7"


def test_a_module_limit_is_per_user_on_a_shared_ip(client: TestClient, tenant: Tenant):
    headers = tenant.act(client, "patient")
    statuses = [client.get("/api/v1/waitlist", headers=headers).status_code for _ in range(301)]
    assert statuses[:300] == [200] * 300
    assert statuses[300] == 429
    refused = client.get("/api/v1/waitlist", headers=headers)
    assert refused.json()["detail"] == TOO_MANY and refused.headers["Retry-After"] == "60"
    # Another patient behind the same IP is not affected, and other modules still answer.
    assert client.get("/api/v1/waitlist", headers=tenant.act(client, "other_patient")).status_code == 200
    assert client.get("/api/v1/notifications", headers=tenant.act(client, "patient")).status_code == 200
    audits = [row for row in _limited_audits(client) if (row.event_metadata or {}).get("reason") == "module:waitlist:read"]
    assert len(audits) == 2 and {row.event_metadata["path"] for row in audits} == {"/api/v1/waitlist"}


def test_notifications_are_generous_for_the_polling_badges(client: TestClient, tenant: Tenant):
    headers = tenant.act(client, "patient")
    assert {client.get("/api/v1/notifications", headers=headers).status_code for _ in range(400)} == {200}


def test_revealing_identifiers_is_limited_per_user(client: TestClient, tenant: Tenant):
    url = f"/api/v1/patients/{tenant.patient_id}/identification/reveal"
    doctor = tenant.act(client, "doctor")
    statuses = [client.post(url, headers=doctor).status_code for _ in range(11)]
    assert statuses == [200] * 10 + [429]
    # The nurse, same IP, still may.
    assert client.post(url, headers=tenant.act(client, "nurse")).status_code == 200


def test_failed_logins_lock_the_account_not_the_ip(client: TestClient, tenant: Tenant):
    limiter.reset()  # setting up the tenant signed in several times from this same IP
    email = tenant.emails["patient"]
    client.cookies.clear()
    statuses = [client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"}).status_code for _ in range(5)]
    assert statuses == [401] * 5
    # Even the right password is refused for the rest of the window...
    locked = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert locked.status_code == 429 and locked.json()["detail"] == ACCOUNT_LOCKED
    assert any((row.event_metadata or {}).get("reason") == "account_login_failures" for row in _limited_audits(client))
    # ...while another account behind the same IP signs in normally.
    other = client.post("/api/v1/auth/login", json={"email": tenant.emails["other_patient"], "password": PASSWORD})
    assert other.status_code == 200


def test_a_successful_login_starts_the_account_count_again(client: TestClient, tenant: Tenant):
    limiter.reset()  # setting up the tenant signed in several times from this same IP
    email = tenant.emails["patient"]
    for _ in range(2):
        client.cookies.clear()
        for _ in range(4):
            assert client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
        assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
