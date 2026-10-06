"""
Tests for Phase 1 foundation hardening:
- password strength enforced consistently across every registration path
- rate limiting on public write endpoints
- baseline security headers on every response
- fail-closed settings validation (JWT algorithm allowlist, prod cookie flag)
"""

import base64
import os
import subprocess
import sys

import pytest

from tests.conftest import csrf_headers

TEST_MFA_KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()
TEST_FINGERPRINT_KEY = "test-only-privacy-fingerprint-key-0123456789"



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


# --- Password policy consistency -------------------------------------------


def test_weak_password_rejected_on_clinic_onboarding(client):
    r = _onboard_clinic(client, password="password123")
    assert r.status_code == 422


def test_weak_password_rejected_on_patient_registration(client):
    clinic_id = _onboard_clinic(client).json()["id"]
    r = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": "João Pereira",
            "email": "joao@example.com",
            "password": "aaaaaaaa",  # 8 chars, passes length, no variety
        },
    )
    assert r.status_code == 422


def test_weak_password_rejected_on_staff_creation(client):
    _onboard_clinic(client)
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@clinica.pt", "password": "SenhaForte123!"},
    )
    r = client.post(
        "/api/v1/staff",
        json={
            "full_name": "Enfermeiro Teste",
            "email": "enfermeiro@clinica.pt",
            "password": "12345678",
            "staff_role": "nurse",
        },
        headers=csrf_headers(client),
    )
    assert r.status_code == 422


def test_strong_password_still_accepted_everywhere(client):
    """Sanity check that the new validator doesn't reject legitimate passwords."""
    r = _onboard_clinic(client)
    assert r.status_code == 201


# --- Rate limiting -----------------------------------------------------------


def test_login_is_rate_limited_after_repeated_attempts(client):
    _onboard_clinic(client)

    last_status = None
    for _ in range(15):
        last_status = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@clinica.pt", "password": "errada"},
        ).status_code

    assert last_status == 429


def test_clinic_onboarding_is_rate_limited_after_repeated_attempts(client):
    last_status = None
    for i in range(10):
        last_status = _onboard_clinic(client, email=f"admin{i}@clinica.pt").status_code

    assert last_status == 429


def test_staff_creation_is_rate_limited_after_repeated_attempts(client):
    _onboard_clinic(client)
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@clinica.pt", "password": "SenhaForte123!"},
    )

    last_status = None
    for i in range(25):
        last_status = client.post(
            "/api/v1/staff",
            json={
                "full_name": f"Staff {i}",
                "email": f"staff{i}@clinica.pt",
                "password": "SenhaForte123!",
                "staff_role": "nurse",
            },
            headers=csrf_headers(client),
        ).status_code

    assert last_status == 429


# --- Security headers ---------------------------------------------------------


def test_baseline_security_headers_present_on_every_response(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "permissions-policy" in r.headers
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_api_responses_are_not_cacheable(client):
    r = client.get("/api/v1/auth/me")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["pragma"] == "no-cache"


def test_oversized_request_is_rejected_before_payload_parsing(client):
    r = client.post(
        "/api/v1/auth/login",
        content=b"x" * 1_048_577,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json() == {"detail": "Pedido demasiado grande."}
    assert r.headers["x-content-type-options"] == "nosniff"


def test_unknown_payload_fields_are_rejected(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@clinica.pt", "password": "wrong", "role": "clinic_admin"},
    )
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "extra_forbidden"


def test_public_login_rejects_untrusted_browser_origin(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@clinica.pt", "password": "wrong"},
        headers={"origin": "https://evil.example"},
    )
    assert r.status_code == 403
    assert r.json() == {"detail": "Origem do pedido não permitida."}


def test_email_longer_than_database_column_is_rejected(client):
    local_part = "a" * 250
    r = client.post(
        "/api/v1/auth/login",
        json={"email": f"{local_part}@example.com", "password": "wrong"},
    )
    assert r.status_code == 422


def test_audit_log_has_no_tenant_facing_api(client):
    assert client.get("/api/v1/audit-logs").status_code == 404


# --- Settings validation (unit-level, no HTTP client needed) -----------------


def test_jwt_algorithm_outside_allowlist_is_rejected():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(JWT_SECRET_KEY="x", JWT_ALGORITHM="none")


def test_production_requires_cookie_secure():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(JWT_SECRET_KEY="x", ENVIRONMENT="production", COOKIE_SECURE=False)


def test_production_with_cookie_secure_is_accepted():
    from app.core.config import Settings

    settings = Settings(
        JWT_SECRET_KEY="production-key-material-with-12+unique-chars!",
        ENVIRONMENT="production",
        COOKIE_SECURE=True,
        CORS_ORIGINS=["https://app.myvita.pt"],
        ALLOWED_HOSTS=["app.myvita.pt"],
        DATABASE_URL="postgresql+psycopg://app:strong-password@db:5432/myvita_prod",
        ALLOW_DIRECT_STAFF_CREATION=False,
        MFA_REQUIRED_FOR_STAFF=True,
        MFA_ENCRYPTION_KEY=TEST_MFA_KEY,
        PRIVACY_FINGERPRINT_KEY=TEST_FINGERPRINT_KEY,
    )
    assert settings.is_production


def test_jwt_secret_key_too_short_is_rejected():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(JWT_SECRET_KEY="too-short")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"JWT_SECRET_KEY": "x" * 32}, "JWT_SECRET_KEY"),
        ({"DATABASE_URL": "postgresql+psycopg://myvita:myvita@db:5432/myvita"}, "DATABASE_URL"),
        ({"CORS_ORIGINS": ["http://app.myvita.pt"]}, "HTTPS"),
        ({"ALLOWED_HOSTS": ["localhost"]}, "local/test"),
        ({"METRICS_TOKEN": "short"}, "METRICS_TOKEN"),
    ],
)
def test_production_rejects_obviously_insecure_configuration(overrides, message):
    from pydantic import ValidationError

    from app.core.config import Settings

    values = {
        "JWT_SECRET_KEY": "production-key-material-with-12+unique-chars!",
        "ENVIRONMENT": "production",
        "COOKIE_SECURE": True,
        "CORS_ORIGINS": ["https://app.myvita.pt"],
        "ALLOWED_HOSTS": ["app.myvita.pt"],
        "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/myvita_prod",
        "MFA_REQUIRED_FOR_STAFF": True,
        "MFA_ENCRYPTION_KEY": TEST_MFA_KEY,
        "PRIVACY_FINGERPRINT_KEY": TEST_FINGERPRINT_KEY,
    }
    values.update(overrides)
    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_production_disables_interactive_and_openapi_documentation():
    environment = {
        **os.environ,
        "ENVIRONMENT": "production",
        "DEBUG": "false",
        "COOKIE_SECURE": "true",
        "JWT_SECRET_KEY": "production-key-material-with-12+unique-chars!",
        "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/myvita_prod",
        "CORS_ORIGINS": '["https://app.myvita.pt"]',
        "ALLOWED_HOSTS": '["app.myvita.pt"]',
        "ALLOW_PUBLIC_CLINIC_ONBOARDING": "false",
        "ALLOW_PUBLIC_PATIENT_REGISTRATION": "false",
        "ALLOW_DIRECT_STAFF_CREATION": "false",
        "MFA_REQUIRED_FOR_STAFF": "true",
        "MFA_ENCRYPTION_KEY": TEST_MFA_KEY,
        "PRIVACY_FINGERPRINT_KEY": TEST_FINGERPRINT_KEY,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.main import app; "
            "assert app.docs_url is None; assert app.redoc_url is None; assert app.openapi_url is None",
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
