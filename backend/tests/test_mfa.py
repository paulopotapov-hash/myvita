"""
Staff MFA (TOTP): enrolment, login challenge, replay protection, lockout,
recovery codes, seed encryption and the pending-action gate.

MFA enforcement is switched on explicitly here (`mfa_enforced`); the rest of
the suite runs with MFA_REQUIRED_FOR_STAFF=false (tests/conftest.py).
"""

import base64
import uuid

import pytest
from pydantic import ValidationError

from app.core import mfa
from app.core.config import Settings, settings
from app.core.security import ACCOUNT_ACTION_HEADER
from app.models import UserMfa
from tests.account_support import (
    PASSWORD,
    audit_rows,
    create_staff,
    enrol_mfa,
    login,
    onboard_clinic,
    post,
    register_patient,
    user_id_by_email,
)

STAFF = "medica@clinica.pt"


def _clinic_with_staff(client) -> dict:
    clinic = onboard_clinic(client)
    create_staff(client, STAFF)
    return clinic


# --- primitives ---------------------------------------------------------------


def test_hotp_matches_rfc_4226_and_6238_vectors():
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert [mfa.hotp(secret, i) for i in range(3)] == ["755224", "287082", "359152"]
    assert mfa.hotp(secret, 59 // 30, digits=8) == "94287082"
    assert mfa.hotp(secret, 1111111109 // 30, digits=8) == "07081804"
    assert mfa.hotp(secret, 20000000000 // 30, digits=8) == "65353130"


def test_verify_totp_accepts_one_step_of_drift_and_never_a_used_step():
    secret = mfa.generate_secret()
    now = 1_000_000 * 30.0
    step = mfa.current_step(now)
    assert mfa.verify_totp(secret, mfa.hotp(secret, step), last_used_step=None, now=now) == step
    assert mfa.verify_totp(secret, mfa.hotp(secret, step - 1), last_used_step=None, now=now) == step - 1
    assert mfa.verify_totp(secret, mfa.hotp(secret, step + 1), last_used_step=None, now=now) == step + 1
    assert mfa.verify_totp(secret, mfa.hotp(secret, step + 2), last_used_step=None, now=now) is None
    assert mfa.verify_totp(secret, mfa.hotp(secret, step), last_used_step=step, now=now) is None
    assert mfa.verify_totp(secret, "abcdef", last_used_step=None, now=now) is None


def test_seed_encryption_is_bound_to_the_user():
    secret = mfa.generate_secret()
    owner, other = uuid.uuid4(), uuid.uuid4()
    stored = mfa.encrypt_secret(secret, owner)
    assert secret not in stored
    assert mfa.decrypt_secret(stored, owner) == secret
    with pytest.raises(mfa.MfaSecretError):
        mfa.decrypt_secret(stored, other)
    with pytest.raises(mfa.MfaSecretError):
        mfa.decrypt_secret("v1:" + base64.urlsafe_b64encode(b"x" * 40).decode(), owner)


def test_challenge_token_is_not_a_session_token_and_vice_versa():
    user_id = uuid.uuid4()
    token = mfa.create_challenge_token(user_id, 0)
    assert mfa.decode_challenge_token(token)["sub"] == str(user_id)
    assert mfa.decode_challenge_token(token + "x") is None
    assert mfa.decode_challenge_token("not-a-jwt") is None


# --- pending enrolment gate ---------------------------------------------------


def test_staff_without_mfa_can_only_enrol_until_they_do(client, enforce_mfa, totp_clock):
    _clinic_with_staff(client)
    enforce_mfa()
    response = login(client, STAFF)
    assert response.status_code == 200
    assert response.json()["pending_action"] == "mfa_setup"
    assert response.json()["mfa_required"] is True

    blocked = client.get("/api/v1/patients")
    assert blocked.status_code == 403
    assert blocked.headers[ACCOUNT_ACTION_HEADER] == "mfa_setup"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["pending_action"] == "mfa_setup"

    enrolment = enrol_mfa(client, totp_clock)
    assert len(enrolment.recovery_codes) == mfa.RECOVERY_CODE_COUNT
    assert client.get("/api/v1/patients").status_code == 200
    me = client.get("/api/v1/auth/me").json()
    assert me["mfa_enabled"] is True and me["pending_action"] is None
    assert len(audit_rows(client, "mfa_enabled")) == 1


def test_clinic_admin_is_also_required_to_enrol(client, mfa_enforced):
    onboard_clinic(client)
    response = login(client, "admin@clinica.pt")
    assert response.json()["pending_action"] == "mfa_setup"
    assert client.get("/api/v1/staff").headers[ACCOUNT_ACTION_HEADER] == "mfa_setup"


def test_patients_are_never_forced_to_enrol(client, mfa_enforced):
    clinic = onboard_clinic(client)
    register_patient(client, clinic["id"], "paciente@example.com")
    response = login(client, "paciente@example.com")
    assert response.json()["pending_action"] is None
    assert response.json()["mfa_required"] is False


def test_enable_with_a_wrong_code_is_rejected_and_audited(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    setup = post(client, "/api/v1/auth/mfa/setup").json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert "secret=" + setup["secret"] in setup["otpauth_uri"]
    wrong = post(client, "/api/v1/auth/mfa/enable", {"code": "000000" if totp_clock.code(setup["secret"]) != "000000" else "111111"})
    assert wrong.status_code == 401
    assert len(audit_rows(client, "mfa_failure")) == 1
    assert post(client, "/api/v1/auth/mfa/enable", {"code": totp_clock.code(setup["secret"])}).status_code == 200


def test_enabling_mfa_revokes_sessions_established_without_it(client, second_client, totp_clock):
    _clinic_with_staff(client)
    login(second_client, STAFF)
    assert second_client.get("/api/v1/auth/me").status_code == 200
    login(client, STAFF)
    enrol_mfa(client, totp_clock)
    assert second_client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 200


def test_secret_is_stored_encrypted(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)
    with client.session_factory() as db:
        row = db.get(UserMfa, uuid.UUID(user_id_by_email(client, STAFF)))
        assert enrolment.secret not in row.secret_ciphertext
        assert row.secret_ciphertext.startswith("v1:")


def test_setup_is_refused_once_mfa_is_active(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrol_mfa(client, totp_clock)
    assert post(client, "/api/v1/auth/mfa/setup").status_code == 409


# --- login challenge ----------------------------------------------------------


def test_login_with_mfa_issues_a_challenge_not_a_session(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)

    challenge = login(client, STAFF)
    assert challenge.status_code == 202
    assert challenge.json() == {"mfa_required": True}
    assert "myvita_session" not in challenge.cookies
    assert client.get("/api/v1/auth/me").status_code == 401
    assert len(audit_rows(client, "login_mfa_challenge")) == 1

    verified = client.post("/api/v1/auth/mfa/verify", json={"code": totp_clock.code(enrolment.secret)})
    assert verified.status_code == 200
    assert verified.json()["pending_action"] is None
    assert client.get("/api/v1/patients").status_code == 200
    success = [row for row in audit_rows(client, "login_success") if row.event_metadata.get("mfa")]
    assert success and success[-1].event_metadata["method"] == "totp"


def test_challenge_cookie_cannot_be_used_as_a_session(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrol_mfa(client, totp_clock)
    challenge = login(client, STAFF)
    token = challenge.cookies.get("myvita_mfa_challenge")
    assert token
    client.cookies.clear()
    client.cookies.set("myvita_session", token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_verify_without_a_challenge_is_rejected(client):
    _clinic_with_staff(client)
    client.cookies.clear()
    assert client.post("/api/v1/auth/mfa/verify", json={"code": "123456"}).status_code == 401


def test_wrong_code_is_rejected_and_audited(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)
    login(client, STAFF)
    wrong = mfa.hotp(enrolment.secret, totp_clock.step + 5)
    response = client.post("/api/v1/auth/mfa/verify", json={"code": wrong})
    assert response.status_code == 401
    assert "myvita_session" not in response.cookies
    assert len(audit_rows(client, "mfa_failure")) == 1


def test_a_code_cannot_be_replayed(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)
    code = totp_clock.code(enrolment.secret)
    login(client, STAFF)
    assert client.post("/api/v1/auth/mfa/verify", json={"code": code}).status_code == 200
    login(client, STAFF)
    assert client.post("/api/v1/auth/mfa/verify", json={"code": code}).status_code == 401


def test_repeated_failures_lock_the_second_factor(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)
    login(client, STAFF)
    wrong = mfa.hotp(enrolment.secret, totp_clock.step + 5)
    for _ in range(mfa.MAX_FAILED_ATTEMPTS):
        assert client.post("/api/v1/auth/mfa/verify", json={"code": wrong}).status_code == 401
    locked = client.post("/api/v1/auth/mfa/verify", json={"code": totp_clock.code(enrolment.secret)})
    assert locked.status_code == 429


def test_deactivated_account_cannot_finish_a_challenge(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)
    login(client, STAFF)
    challenge_cookie = client.cookies.get("myvita_mfa_challenge")
    from app.models import User

    with client.session_factory() as db:
        user = db.get(User, uuid.UUID(user_id_by_email(client, STAFF)))
        user.is_active = False
        db.commit()
    client.cookies.set("myvita_mfa_challenge", challenge_cookie, path="/api/v1/auth/mfa")
    response = client.post("/api/v1/auth/mfa/verify", json={"code": totp_clock.code(enrolment.secret)})
    assert response.status_code == 401


# --- recovery codes -------------------------------------------------------------


def test_recovery_code_works_once(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)
    code = enrolment.recovery_codes[0]

    login(client, STAFF)
    first = client.post("/api/v1/auth/mfa/verify", json={"code": code.upper()})
    assert first.status_code == 200
    used = audit_rows(client, "mfa_recovery_code_used")
    assert used[-1].event_metadata["recovery_codes_remaining"] == mfa.RECOVERY_CODE_COUNT - 1
    assert code not in str(used[-1].event_metadata)

    login(client, STAFF)
    assert client.post("/api/v1/auth/mfa/verify", json={"code": code}).status_code == 401


def test_regenerating_recovery_codes_invalidates_the_old_ones(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)
    regenerated = post(client, "/api/v1/auth/mfa/recovery-codes", {"code": totp_clock.code(enrolment.secret)})
    totp_clock.advance()
    assert regenerated.status_code == 200
    new_codes = regenerated.json()["recovery_codes"]
    assert set(new_codes).isdisjoint(enrolment.recovery_codes)

    login(client, STAFF)
    assert client.post("/api/v1/auth/mfa/verify", json={"code": enrolment.recovery_codes[1]}).status_code == 401
    assert client.post("/api/v1/auth/mfa/verify", json={"code": new_codes[0]}).status_code == 200


def test_recovery_codes_cannot_authorise_regeneration(client, totp_clock):
    _clinic_with_staff(client)
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)
    response = post(client, "/api/v1/auth/mfa/recovery-codes", {"code": enrolment.recovery_codes[0]})
    assert response.status_code == 401


# --- disable ----------------------------------------------------------------------


def test_staff_cannot_disable_mandatory_mfa(client, enforce_mfa, totp_clock):
    _clinic_with_staff(client)
    enforce_mfa()
    login(client, STAFF)
    enrolment = enrol_mfa(client, totp_clock)
    response = post(
        client,
        "/api/v1/auth/mfa/disable",
        {"current_password": PASSWORD, "code": totp_clock.code(enrolment.secret)},
    )
    assert response.status_code == 403


def test_patient_can_opt_in_and_disable_with_password_and_totp(client, totp_clock):
    clinic = onboard_clinic(client)
    register_patient(client, clinic["id"], "paciente@example.com")
    login(client, "paciente@example.com")
    enrolment = enrol_mfa(client, totp_clock)

    wrong_password = post(
        client, "/api/v1/auth/mfa/disable", {"current_password": "errada!!", "code": totp_clock.code(enrolment.secret)}
    )
    assert wrong_password.status_code == 400
    with_recovery = post(
        client, "/api/v1/auth/mfa/disable", {"current_password": PASSWORD, "code": enrolment.recovery_codes[0]}
    )
    assert with_recovery.status_code == 401

    disabled = post(
        client, "/api/v1/auth/mfa/disable", {"current_password": PASSWORD, "code": totp_clock.code(enrolment.secret)}
    )
    assert disabled.status_code == 204
    assert len(audit_rows(client, "mfa_disabled")) == 1
    assert login(client, "paciente@example.com").status_code == 200


# --- configuration --------------------------------------------------------------


def _production(**overrides) -> Settings:
    values = {
        "ENVIRONMENT": "production",
        "JWT_SECRET_KEY": "prod-signing-material-AbCdEf0123456789xyz!",
        "COOKIE_SECURE": True,
        "CORS_ORIGINS": ["https://app.myvita.pt"],
        "ALLOWED_HOSTS": ["app.myvita.pt"],
        "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/myvita_prod",
        "ALLOW_DIRECT_STAFF_CREATION": False,
        "MFA_REQUIRED_FOR_STAFF": True,
        "MFA_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"k" * 32).decode(),
        "PRIVACY_FINGERPRINT_KEY": "privacy-fingerprint-key-0123456789abcdef",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_configuration_requires_mfa_controls():
    assert _production().is_production
    with pytest.raises(ValidationError, match="MFA_REQUIRED_FOR_STAFF"):
        _production(MFA_REQUIRED_FOR_STAFF=False)
    with pytest.raises(ValidationError, match="MFA_ENCRYPTION_KEY must be set"):
        _production(MFA_ENCRYPTION_KEY=None)
    with pytest.raises(ValidationError, match="exactly 32 bytes"):
        _production(MFA_ENCRYPTION_KEY=base64.urlsafe_b64encode(b"k" * 16).decode())
    with pytest.raises(ValidationError, match="PRIVACY_FINGERPRINT_KEY must be set"):
        _production(PRIVACY_FINGERPRINT_KEY=None)
    with pytest.raises(ValidationError, match="PRIVACY_FINGERPRINT_KEY must differ"):
        _production(PRIVACY_FINGERPRINT_KEY="prod-signing-material-AbCdEf0123456789xyz!")


def test_test_suite_runs_without_mandatory_mfa_by_default():
    # Guard against the default silently flipping for every other suite.
    assert settings.MFA_REQUIRED_FOR_STAFF is False
