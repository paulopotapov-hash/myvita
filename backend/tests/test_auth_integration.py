"""
Integration tests exercising the real HTTP app (FastAPI TestClient), not
just the ORM layer. These mirror the manual smoke test run during
development, kept here so they run in CI going forward.
"""

from tests.conftest import csrf_headers


def _onboard_clinic(client, email="admin@clinica.pt"):
    return client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": "Clínica Teste",
            "nif": "500999999",
            "admin_full_name": "Admin Teste",
            "admin_email": email,
            "admin_password": "SenhaForte123!",
        },
    )


def test_clinic_onboarding_then_login(client):
    r = _onboard_clinic(client)
    assert r.status_code == 201
    assert "myvita_session" in r.cookies

    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@clinica.pt", "password": "SenhaForte123!"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "clinic_admin"


def test_login_with_wrong_password_is_rejected(client):
    _onboard_clinic(client)
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@clinica.pt", "password": "errada"},
    )
    assert r.status_code == 401


def test_patient_registration_and_me(client):
    clinic_resp = _onboard_clinic(client)
    clinic_id = clinic_resp.json()["id"]

    r = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": clinic_id,
            "full_name": "João Pereira",
            "email": "joao@example.com",
            "password": "OutraSenha456!",
            "birth_date": "1990-05-20",
        },
    )
    assert r.status_code == 201

    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "joao@example.com"
    assert r.json()["role"] == "patient"


def test_logout_immediately_invalidates_the_cookie_even_if_reused(client):
    """
    This is the key security property of the token_epoch design: logging
    out must invalidate the session token server-side, not just tell the
    browser to forget the cookie. A copied/replayed cookie must stop
    working right after logout.
    """
    _onboard_clinic(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@clinica.pt", "password": "SenhaForte123!"},
    )
    stolen_cookie = login.cookies.get("myvita_session")

    logout = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert logout.status_code == 204

    client.cookies.set("myvita_session", stolen_cookie)
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_duplicate_admin_email_rejected_on_onboarding(client):
    _onboard_clinic(client, email="dup@clinica.pt")
    r = _onboard_clinic(client, email="dup@clinica.pt")
    assert r.status_code == 400


def test_patient_registration_at_unknown_clinic_returns_404(client):
    r = client.post(
        "/api/v1/patients/register",
        json={
            "clinic_id": "00000000-0000-0000-0000-000000000000",
            "full_name": "Ninguém",
            "email": "ninguem@example.com",
            "password": "SenhaForte123!",
        },
    )
    assert r.status_code == 404


def test_me_without_cookie_is_unauthenticated(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
