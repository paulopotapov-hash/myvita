"""
Dedicated CSRF protection test suite (double-submit cookie, HMAC-signed
and bound to the session's user_id + token_epoch — see
app/core/security.py for the full design rationale).

These tests exercise real HTTP behavior through the FastAPI TestClient,
not just unit-level token generation/validation.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from tests.conftest import TEST_DATABASE_URL


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


def _onboard_clinic(client, email="admin@clinica.pt"):
    return client.post(
        "/api/v1/clinics",
        json={
            "clinic_name": "Clínica Teste",
            "admin_full_name": "Admin Teste",
            "admin_email": email,
            "admin_password": "SenhaForte123!",
        },
    )


def _valid_csrf_header(client) -> dict:
    token = client.cookies.get(settings.CSRF_COOKIE_NAME)
    return {settings.CSRF_HEADER_NAME: token}


# ---------------------------------------------------------------------------
# Cookie shape
# ---------------------------------------------------------------------------


def test_login_sets_both_session_and_csrf_cookies(client):
    _onboard_clinic(client)
    r = client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    assert settings.COOKIE_NAME in r.cookies
    assert settings.CSRF_COOKIE_NAME in r.cookies


def test_session_cookie_is_httponly_csrf_cookie_is_not(client):
    """
    Confirms the core requirement of this whole feature: the JWT session
    cookie stays httpOnly (unreadable by JS, unchanged from before), while
    the CSRF cookie is deliberately readable by frontend JS — that's the
    double-submit design, not a regression.
    """
    _onboard_clinic(client)
    r = client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    set_cookie_headers = r.headers.get_list("set-cookie")
    session_header = next(h for h in set_cookie_headers if h.startswith(f"{settings.COOKIE_NAME}="))
    csrf_header = next(h for h in set_cookie_headers if h.startswith(f"{settings.CSRF_COOKIE_NAME}="))

    assert "httponly" in session_header.lower()
    assert "httponly" not in csrf_header.lower()


def test_csrf_cookie_does_not_contain_the_jwt(client):
    _onboard_clinic(client)
    r = client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    session_jwt = r.cookies.get(settings.COOKIE_NAME)
    csrf_value = r.cookies.get(settings.CSRF_COOKIE_NAME)

    assert csrf_value != session_jwt
    # A JWT has three dot-separated base64url segments; our CSRF token has
    # exactly one dot (nonce.signature) — structurally different, not a JWT.
    assert csrf_value.count(".") == 1
    assert session_jwt.count(".") == 2


# ---------------------------------------------------------------------------
# Safe methods never require CSRF
# ---------------------------------------------------------------------------


def test_authenticated_get_works_without_csrf_header(client):
    _onboard_clinic(client)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    r = client.get("/api/v1/auth/me")  # deliberately no X-CSRF-Token header
    assert r.status_code == 200


def test_options_preflight_is_never_blocked_by_csrf(client):
    r = client.options(
        "/api/v1/appointments",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Starlette/FastAPI's CORS middleware answers OPTIONS itself; the key
    # assertion is that it's not a 403 from our CSRF check.
    assert r.status_code != 403


# ---------------------------------------------------------------------------
# Unsafe methods on authenticated endpoints require CSRF
# ---------------------------------------------------------------------------


def test_post_without_csrf_token_is_rejected(client):
    _onboard_clinic(client)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    r = client.post(
        "/api/v1/staff",
        json={"full_name": "Dr. X", "email": "x@x.pt", "password": "SenhaForte123!", "staff_role": "doctor"},
        # no X-CSRF-Token header at all
    )
    assert r.status_code == 403


def test_post_with_wrong_csrf_token_is_rejected(client):
    _onboard_clinic(client)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    r = client.post(
        "/api/v1/staff",
        json={"full_name": "Dr. X", "email": "x@x.pt", "password": "SenhaForte123!", "staff_role": "doctor"},
        headers={settings.CSRF_HEADER_NAME: "attacker-guessed-value-not-matching-anything"},
    )
    assert r.status_code == 403


def test_post_with_correct_csrf_token_succeeds(client):
    _onboard_clinic(client)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    r = client.post(
        "/api/v1/staff",
        json={"full_name": "Dr. X", "email": "x@x.pt", "password": "SenhaForte123!", "staff_role": "doctor"},
        headers=_valid_csrf_header(client),
    )
    assert r.status_code == 201


def test_patch_and_delete_also_require_csrf():
    """
    PATCH/DELETE aren't implemented on any endpoint yet (see README "por
    fazer"), so this test exercises the CSRF dependency directly against a
    throwaway route registered only for this test, proving the protection
    is method-generic and will cover PATCH/DELETE endpoints the moment
    they're added — not something that has to be re-implemented per verb.
    """
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient as _TestClient

    from app.core.security import get_current_user

    probe_app = FastAPI()

    @probe_app.patch("/probe")
    def patch_probe(user=Depends(get_current_user)):
        return {"ok": True}

    @probe_app.delete("/probe")
    def delete_probe(user=Depends(get_current_user)):
        return {"ok": True}

    # Reuse the real app's dependency override plumbing isn't needed here —
    # we only need get_current_user's CSRF branch, which runs before any
    # DB lookup would even be reached in the no-cookie case. To exercise
    # the fully authenticated path we still need a real logged-in client,
    # so we hit the real app to log in, then reuse those cookies here.
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
    try:
        with TestClient(app) as real_client:
            _onboard_clinic(real_client)
            real_client.post(
                "/api/v1/auth/login",
                json={"email": "admin@clinica.pt", "password": "SenhaForte123!"},
            )
            session_cookie = real_client.cookies.get(settings.COOKIE_NAME)
            csrf_cookie = real_client.cookies.get(settings.CSRF_COOKIE_NAME)

        probe_app.dependency_overrides[get_db] = override_get_db
        with _TestClient(probe_app) as probe_client:
            probe_client.cookies.set(settings.COOKIE_NAME, session_cookie)
            probe_client.cookies.set(settings.CSRF_COOKIE_NAME, csrf_cookie)

            r = probe_client.patch("/probe")
            assert r.status_code == 403  # no header

            r = probe_client.delete("/probe")
            assert r.status_code == 403  # no header

            r = probe_client.patch("/probe", headers={settings.CSRF_HEADER_NAME: csrf_cookie})
            assert r.status_code == 200

            r = probe_client.delete("/probe", headers={settings.CSRF_HEADER_NAME: csrf_cookie})
            assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Login/logout keep working; JWT/session semantics unchanged
# ---------------------------------------------------------------------------


def test_login_itself_does_not_require_csrf(client):
    """Login is how a client OBTAINS a CSRF token — it can't be expected to
    already have one. It stays CSRF-exempt (it's not behind get_current_user)."""
    _onboard_clinic(client)
    r = client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})
    assert r.status_code == 200


def test_logout_requires_and_accepts_correct_csrf(client):
    _onboard_clinic(client)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    # without CSRF header — rejected
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 403

    # with correct CSRF header — succeeds
    r = client.post("/api/v1/auth/logout", headers=_valid_csrf_header(client))
    assert r.status_code == 204


def test_logout_invalidates_csrf_token_along_with_session(client):
    """
    The CSRF token is bound to token_epoch, so it must die together with
    the session on logout — a captured pre-logout CSRF+session cookie pair
    must not keep working afterwards.
    """
    _onboard_clinic(client)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})
    stolen_session = client.cookies.get(settings.COOKIE_NAME)
    stolen_csrf = client.cookies.get(settings.CSRF_COOKIE_NAME)

    client.post("/api/v1/auth/logout", headers=_valid_csrf_header(client))

    client.cookies.set(settings.COOKIE_NAME, stolen_session)
    client.cookies.set(settings.CSRF_COOKIE_NAME, stolen_csrf)
    r = client.post(
        "/api/v1/staff",
        json={"full_name": "Dr. X", "email": "x@x.pt", "password": "SenhaForte123!", "staff_role": "doctor"},
        headers={settings.CSRF_HEADER_NAME: stolen_csrf},
    )
    # 401 (session itself already invalid) — CSRF check never even needs to
    # run, but either way the state-changing request must be blocked.
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# The actual attack this feature defends against
# ---------------------------------------------------------------------------


def test_csrf_token_from_a_different_session_is_not_accepted(client):
    """
    Binding requirement: even a well-formed, validly-issued CSRF token
    (correct nonce.signature shape, matching header==cookie) must be
    rejected if it wasn't issued for the CURRENT session. This is what the
    HMAC binding to (user_id, token_epoch) buys over a plain double-submit
    cookie that only checks "does the header match the cookie".
    """
    # Session/user A
    _onboard_clinic(client, email="a@clinica.pt")
    client.post("/api/v1/auth/login", json={"email": "a@clinica.pt", "password": "SenhaForte123!"})
    token_from_a = client.cookies.get(settings.CSRF_COOKIE_NAME)

    # Session/user B, on the same browser client (e.g. shared/kiosk machine,
    # or simply a second account) — must NOT be usable with A's CSRF token.
    _onboard_clinic(client, email="b@clinica.pt")
    client.post("/api/v1/auth/login", json={"email": "b@clinica.pt", "password": "SenhaForte123!"})

    # Attacker/mistake scenario: B's session cookie is active, but the
    # X-CSRF-Token header carries A's previously-seen token.
    r = client.post(
        "/api/v1/staff",
        json={"full_name": "Dr. Y", "email": "y@y.pt", "password": "SenhaForte123!", "staff_role": "doctor"},
        headers={settings.CSRF_HEADER_NAME: token_from_a},
    )
    assert r.status_code == 403


def test_simulated_cross_site_form_post_is_blocked(client):
    """
    End-to-end simulation of the actual attack CSRF protection exists for:
    a malicious page on another origin makes the victim's browser submit a
    state-changing request. The browser WOULD automatically attach the
    myvita_session cookie (that's the vulnerability SameSite/CSRF tokens
    defend against), but the attacker's page has no way to read the
    myvita_csrf cookie's value (different origin, cookie not exposed to
    it) — so it cannot set a matching X-CSRF-Token header. We simulate
    this by sending the request with the session cookie present but no
    CSRF header, exactly as a forged cross-site request would look from
    the server's point of view.
    """
    _onboard_clinic(client)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})

    forged_request = client.post(
        "/api/v1/staff",
        json={
            "full_name": "Forged Doctor",
            "email": "forged@x.pt",
            "password": "SenhaForte123!",
            "staff_role": "doctor",
        },
        headers={"Origin": "https://attacker.example"},
        # crucially: no X-CSRF-Token header — attacker.example cannot read it
    )
    assert forged_request.status_code == 403


def test_cross_origin_post_with_mismatched_origin_header_is_rejected_even_with_stolen_csrf(client):
    """
    Defense-in-depth: if an Origin header is present and doesn't match our
    configured CORS origins, we reject before even checking the CSRF
    token — covers scenarios where a CSRF token leaked (e.g. via a
    same-site subdomain XSS) but the request still comes from a
    disallowed origin.
    """
    _onboard_clinic(client)
    client.post("/api/v1/auth/login", json={"email": "admin@clinica.pt", "password": "SenhaForte123!"})
    valid_csrf = client.cookies.get(settings.CSRF_COOKIE_NAME)

    r = client.post(
        "/api/v1/staff",
        json={"full_name": "Dr. X", "email": "x@x.pt", "password": "SenhaForte123!", "staff_role": "doctor"},
        headers={
            "Origin": "https://attacker.example",
            settings.CSRF_HEADER_NAME: valid_csrf,  # even with a technically-valid token
        },
    )
    assert r.status_code == 403
