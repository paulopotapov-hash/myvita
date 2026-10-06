"""
Phase 3 security regression tests: request ID, CORS, safe logging,
production config fail-closed behavior, health/readiness.

Uses the same create_all/drop_all client pattern as test_auth_hardening.py.
Named to sort before test_data_integrity.py alphabetically — see that
file's fixture docstring for why fixture ordering across files matters here.
"""
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.rate_limit import limiter
from app.core.request_context import new_request_id
from app.main import app
from tests.conftest import TEST_DATABASE_URL, csrf_headers


@pytest.fixture()
def client():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    limiter.reset()
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _onboard_clinic(client, email="admin@clinica.pt", password="SenhaForte123!"):
    return client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": "Clínica Teste",
            "nif": "500999999",
            "admin_full_name": "Admin Teste",
            "admin_email": email,
            "admin_password": password,
        },
    )


# --- Request ID ---------------------------------------------------------


def test_request_without_id_gets_one_assigned(client):
    r = client.get("/health")
    assert r.headers.get("x-request-id")
    assert len(r.headers["x-request-id"]) >= 8


def test_well_formed_client_request_id_is_echoed_back(client):
    r = client.get("/health", headers={"X-Request-ID": "meu-id-de-cliente-123"})
    assert r.headers["x-request-id"] == "meu-id-de-cliente-123"


def test_malformed_client_request_id_is_replaced_not_trusted(client):
    """Too short, and separately, characters outside the allowed set —
    neither should ever be echoed back verbatim."""
    r = client.get("/health", headers={"X-Request-ID": "ab"})
    assert r.headers["x-request-id"] != "ab"

    huge = "a" * 5000
    r = client.get("/health", headers={"X-Request-ID": huge})
    assert r.headers["x-request-id"] != huge
    assert len(r.headers["x-request-id"]) < 100


def test_new_request_id_generates_a_uuid_hex_when_nothing_supplied():
    rid = new_request_id(None)
    assert len(rid) == 32
    int(rid, 16)  # raises if it isn't valid hex — i.e. not a real UUID4 hex


# --- CORS -----------------------------------------------------------------


def test_cors_preflight_allows_configured_origin(client):
    r = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_preflight_rejects_unlisted_origin(client):
    r = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers


def test_cors_does_not_advertise_wildcard_methods_or_headers(client):
    r = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-methods") != "*"
    assert r.headers.get("access-control-allow-headers") != "*"


# --- Health / readiness -----------------------------------------------------


def test_health_does_not_touch_the_database(client, monkeypatch):
    """Liveness must stay up even if the DB layer is completely broken."""

    def _boom(*args, **kwargs):
        raise RuntimeError("the DB is down, but /health must not care")

    monkeypatch.setattr("app.main.engine.connect", _boom)
    r = client.get("/health")
    assert r.status_code == 200


def test_ready_reports_503_when_database_unreachable(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated database outage")

    monkeypatch.setattr("app.main.engine.connect", _boom)
    r = client.get("/ready")
    assert r.status_code == 503
    # Must never leak connection strings, credentials, or exception details.
    assert "postgresql" not in r.text.lower()
    assert "password" not in r.text.lower()


def test_ready_reports_200_when_database_reachable(client):
    r = client.get("/ready")
    assert r.status_code == 200


# --- Metrics endpoint gating -------------------------------------------------


def test_metrics_endpoint_is_404_when_no_token_configured(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.METRICS_TOKEN", None)
    r = client.get("/metrics")
    assert r.status_code == 404


def test_metrics_endpoint_requires_correct_token(client, monkeypatch):
    monkeypatch.setattr("app.main.settings.METRICS_TOKEN", "correct-token")
    assert client.get("/metrics").status_code == 404
    assert client.get("/metrics", headers={"X-Metrics-Token": "wrong"}).status_code == 404
    r = client.get("/metrics", headers={"X-Metrics-Token": "correct-token"})
    assert r.status_code == 200
    assert "myvita_http_requests_total" in r.text


# --- Safe logging: no secrets ever reach the log stream ----------------------


def test_no_secrets_in_logs_across_a_full_auth_flow(client, caplog):
    """
    Runs a realistic sequence (onboarding, login, a failed login, staff
    creation with CSRF) with every myvita.* logger captured, then asserts
    the password and the session/CSRF cookie values never appear in any
    log line, anywhere.
    """
    secret_password = "SenhaMuitoSecreta987!"  # noqa: S105 (test fixture value)

    with caplog.at_level(logging.DEBUG):
        r = _onboard_clinic(client, password=secret_password)
        session_cookie_value = client.cookies.get("myvita_session")
        csrf_cookie_value = client.cookies.get("myvita_csrf")

        client.post(
            "/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "wrong-password"}
        )
        client.post(
            "/api/v1/staff",
            json={
                "full_name": "X",
                "email": "x@clinica.pt",
                "password": secret_password,
                "staff_role": "nurse",
            },
            headers=csrf_headers(client),
        )

    assert r.status_code == 201
    all_log_text = "\n".join(rec.getMessage() for rec in caplog.records)

    assert secret_password not in all_log_text
    assert "wrong-password" not in all_log_text
    if session_cookie_value:
        assert session_cookie_value not in all_log_text
    if csrf_cookie_value:
        assert csrf_cookie_value not in all_log_text
    assert "authorization" not in all_log_text.lower()


# --- Production config fail-closed behavior ---------------------------------


def test_production_config_rejects_wildcard_cors():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            JWT_SECRET_KEY="x" * 32,
            ENVIRONMENT="production",
            COOKIE_SECURE=True,
            CORS_ORIGINS=["*"],
        )


def test_production_config_rejects_empty_cors():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            JWT_SECRET_KEY="x" * 32,
            ENVIRONMENT="production",
            COOKIE_SECURE=True,
            CORS_ORIGINS=[],
        )


def test_environment_typo_is_rejected_not_silently_accepted():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(JWT_SECRET_KEY="x" * 32, ENVIRONMENT="productoin")


# --- Trusted proxy / client IP ------------------------------------------------


def test_untrusted_peer_forwarded_for_header_is_ignored():
    from app.core.client_ip import get_client_ip

    class _Client:
        host = "8.8.8.8"  # not in TRUSTED_PROXIES (empty by default)

    class _Req:
        client = _Client()
        headers = {"x-forwarded-for": "203.0.113.7"}

    # Untrusted peer's own address wins — the spoofed XFF is never used.
    assert get_client_ip(_Req()) == "8.8.8.8"
