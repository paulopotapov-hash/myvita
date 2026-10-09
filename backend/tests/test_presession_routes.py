"""The three Parent-A endpoints that are reachable without a session (and are
therefore excluded from the anonymous/CSRF route sweeps in test_phase1_security):

  POST /api/v1/auth/mfa/verify             — authenticated by the MFA challenge cookie
  POST /api/v1/auth/password-reset/request — anonymous self-service recovery entry
  POST /api/v1/auth/password-reset/confirm — anonymous, authenticated by the reset token

Existing coverage (not duplicated here): tests/test_mfa.py
`test_verify_without_a_challenge_is_rejected`, `test_challenge_cookie_cannot_be_used_as_a_session`,
`test_a_code_cannot_be_replayed`; tests/test_account_lifecycle.py
`test_anonymous_reset_request_never_issues_a_token_or_reveals_accounts`,
`test_reset_link_works_exactly_once_and_revokes_sessions`, `test_expired_reset_link_is_rejected`,
`test_weak_or_unknown_reset_input_is_rejected`. This module adds the gaps."""

from app.core.rate_limit import PASSWORD_RESET_RATE_LIMIT, limiter
from app.models import User
from tests.account_support import (
    NEW_PASSWORD,
    PASSWORD,
    create_staff,
    login,
    onboard_clinic,
    post,
    user_id_by_email,
)

ADMIN = "admin@presession.pt"
STAFF = "nurse@presession.pt"


def _setup(client) -> None:
    onboard_clinic(client, ADMIN)
    create_staff(client, STAFF, staff_role="nurse")
    login(client, ADMIN)


def _epoch(client, email: str) -> int:
    with client.session_factory() as db:
        return db.query(User.token_epoch).filter(User.email == email).scalar()


def test_mfa_verify_with_a_valid_body_but_no_or_garbage_challenge_is_401_not_422(client):
    _setup(client)
    client.cookies.clear()
    assert client.post("/api/v1/auth/mfa/verify", json={"code": "123456"}).status_code == 401
    client.cookies.set("myvita_mfa_challenge", "not-a-real-challenge", path="/api/v1/auth/mfa")
    rejected = client.post("/api/v1/auth/mfa/verify", json={"code": "123456"})
    assert rejected.status_code == 401
    assert "myvita_session" not in rejected.cookies
    # A real session cookie is not accepted as a challenge either.
    login(client, STAFF)
    session_value = client.cookies.get("myvita_session")
    client.cookies.clear()
    client.cookies.set("myvita_mfa_challenge", session_value, path="/api/v1/auth/mfa")
    assert client.post("/api/v1/auth/mfa/verify", json={"code": "123456"}).status_code == 401


def test_password_reset_request_is_rate_limited_per_client(client):
    _setup(client)
    client.cookies.clear()
    limiter.reset()
    allowed = int(PASSWORD_RESET_RATE_LIMIT.split("/")[0])
    statuses = [
        client.post("/api/v1/auth/password-reset/request", json={"email": f"probe-{i}@presession.pt"}).status_code
        for i in range(allowed + 1)
    ]
    assert statuses[:allowed] == [202] * allowed
    assert statuses[allowed] == 429


def test_password_reset_confirm_rejects_bad_tokens_and_a_success_bumps_the_token_epoch(client):
    _setup(client)
    before = _epoch(client, STAFF)
    issued = post(client, f"/api/v1/users/{user_id_by_email(client, STAFF)}/password-reset")
    assert issued.status_code == 201
    token = issued.json()["token"]

    client.cookies.clear()
    for bad in ("", "x", token[:-1] + ("a" if token[-1] != "a" else "b")):
        rejected = client.post("/api/v1/auth/password-reset/confirm", json={"token": bad, "new_password": NEW_PASSWORD})
        assert rejected.status_code in (400, 422), bad
    assert _epoch(client, STAFF) == before

    assert client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": NEW_PASSWORD}).status_code == 204
    assert _epoch(client, STAFF) == before + 1
    # Reuse is refused and does not bump again.
    assert client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": PASSWORD}).status_code == 400
    assert _epoch(client, STAFF) == before + 1
