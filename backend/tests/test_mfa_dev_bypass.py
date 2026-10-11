"""MFA dev/demo bypass (MFA_DEV_BYPASS_EMAILS / MFA_DEV_BYPASS_CODE).

Proves the three rules the bypass must follow:
- off by default: no account skips the second factor unless the variable lists it;
- only the listed accounts, and only with the configured code (wrong codes still count as failures);
- never in production: the settings refuse to load, so the app refuses to start, and the
  service ignores the list if ENVIRONMENT is production.

Synthetic accounts and codes only.
"""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.modules.auth import mfa_service
from tests.account_support import audit_rows, create_staff, enrol_mfa, login, onboard_clinic, post
from tests.test_auth_hardening import TEST_FINGERPRINT_KEY, TEST_MFA_KEY
from tests.test_mfa import _production

LISTED = "demo.medica@clinica.pt"
UNLISTED = "outra.medica@clinica.pt"
BYPASS_CODE = "246810"


def test_bypass_is_off_by_default():
    assert Settings.model_fields["MFA_DEV_BYPASS_EMAILS"].default == ""
    # _env_file=None: the defaults themselves, never a developer's local .env.
    defaults = Settings(_env_file=None, JWT_SECRET_KEY="development-key-material-0123456789!")  # type: ignore[call-arg]
    assert defaults.mfa_dev_bypass_emails == frozenset()


def test_production_settings_refuse_a_bypass_list():
    with pytest.raises(ValidationError, match="MFA_DEV_BYPASS_EMAILS must be empty when ENVIRONMENT=production"):
        _production(MFA_DEV_BYPASS_EMAILS=LISTED)
    # Empty or blank is accepted.
    assert _production(MFA_DEV_BYPASS_EMAILS="").mfa_dev_bypass_emails == frozenset()
    assert _production(MFA_DEV_BYPASS_EMAILS="  ").mfa_dev_bypass_emails == frozenset()


def _start_app_in_production(bypass_emails: str) -> subprocess.CompletedProcess[str]:
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
        "MFA_DEV_BYPASS_EMAILS": bypass_emails,
    }
    return subprocess.run(
        [sys.executable, "-c", "from app.main import app"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_the_app_refuses_to_start_in_production_with_the_bypass_enabled():
    refused = _start_app_in_production(LISTED)
    assert refused.returncode != 0
    assert "MFA_DEV_BYPASS_EMAILS must be empty when ENVIRONMENT=production" in refused.stderr
    # Control: the same production configuration starts without the bypass.
    started = _start_app_in_production("")
    assert started.returncode == 0, started.stderr


def test_the_service_ignores_the_list_in_production(monkeypatch):
    user = SimpleNamespace(email=LISTED)
    monkeypatch.setattr(settings, "MFA_DEV_BYPASS_EMAILS", LISTED)
    monkeypatch.setattr(settings, "MFA_DEV_BYPASS_CODE", BYPASS_CODE)
    assert mfa_service._dev_bypass_applies(user, BYPASS_CODE) is True  # type: ignore[arg-type]
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert mfa_service._dev_bypass_applies(user, BYPASS_CODE) is False  # type: ignore[arg-type]


def _enrolled(client, totp_clock, email: str) -> None:
    login(client, "admin@clinica.pt")
    create_staff(client, email)
    login(client, email)
    enrol_mfa(client, totp_clock)


def test_without_the_variable_the_fixed_code_never_passes(client, totp_clock, monkeypatch):
    monkeypatch.setattr(settings, "MFA_DEV_BYPASS_EMAILS", "")
    monkeypatch.setattr(settings, "MFA_DEV_BYPASS_CODE", BYPASS_CODE)
    onboard_clinic(client)
    _enrolled(client, totp_clock, LISTED)
    login(client, LISTED)
    assert client.post("/api/v1/auth/mfa/verify", json={"code": BYPASS_CODE}).status_code == 401


def test_only_listed_accounts_with_the_configured_code_pass(client, totp_clock, monkeypatch):
    monkeypatch.setattr(settings, "MFA_DEV_BYPASS_EMAILS", f" {LISTED.upper()} ,")
    monkeypatch.setattr(settings, "MFA_DEV_BYPASS_CODE", BYPASS_CODE)
    onboard_clinic(client)
    _enrolled(client, totp_clock, LISTED)
    _enrolled(client, totp_clock, UNLISTED)

    # A listed account with a wrong code fails like any wrong code (and is audited).
    login(client, LISTED)
    assert client.post("/api/v1/auth/mfa/verify", json={"code": "135791"}).status_code == 401
    assert len(audit_rows(client, "mfa_failure")) == 1

    # The listed account passes with the configured code; the login records how.
    assert client.post("/api/v1/auth/mfa/verify", json={"code": BYPASS_CODE}).status_code == 200
    success = [row for row in audit_rows(client, "login_success") if row.event_metadata.get("mfa")]
    assert success[-1].event_metadata["method"] == "dev_bypass"
    assert client.get("/api/v1/auth/me").json()["email"] == LISTED

    # An account that is not listed never passes with it.
    login(client, UNLISTED)
    assert client.post("/api/v1/auth/mfa/verify", json={"code": BYPASS_CODE}).status_code == 401


def test_bypass_code_is_not_accepted_for_sensitive_step_up_actions(client, totp_clock, monkeypatch):
    """Regenerating recovery codes re-checks a real second factor (allow_recovery_code=False path)."""
    monkeypatch.setattr(settings, "MFA_DEV_BYPASS_EMAILS", LISTED)
    monkeypatch.setattr(settings, "MFA_DEV_BYPASS_CODE", BYPASS_CODE)
    onboard_clinic(client)
    _enrolled(client, totp_clock, LISTED)
    response = post(client, "/api/v1/auth/mfa/recovery-codes", {"code": BYPASS_CODE})
    assert response.status_code == 401
