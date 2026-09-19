"""
Tests for Phase 1 foundation hardening:
- password strength enforced consistently across every registration path
- rate limiting on public write endpoints
- baseline security headers on every response
- fail-closed settings validation (JWT algorithm allowlist, prod cookie flag)
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
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
        JWT_SECRET_KEY="x" * 32, ENVIRONMENT="production", COOKIE_SECURE=True, CORS_ORIGINS=["https://app.myvita.pt"]
    )
    assert settings.is_production


def test_jwt_secret_key_too_short_is_rejected():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(JWT_SECRET_KEY="too-short")
