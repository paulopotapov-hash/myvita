"""
Pure-function guards: e-mail masking/fingerprinting (app/core/privacy.py)
and the refusal to run the destructive test setup against anything but a
local *_test database (tests/db_safety.py).
"""

import pytest

from app.core import privacy
from app.core.config import settings
from tests.db_safety import UnsafeTestDatabaseError, validate_test_database_url

# --- privacy -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("email", "masked"),
    [
        ("ana.silva@clinica.pt", "a***@clinica.pt"),
        ("  Ana@Clinica.PT ", "a***@clinica.pt"),
        ("x@y.pt", "x***@y.pt"),
        ("no-at-sign", "***"),
        ("", "***"),
    ],
)
def test_mask_email(email, masked):
    assert privacy.mask_email(email) == masked


def test_fingerprint_is_stable_normalised_and_not_reversible():
    first = privacy.email_fingerprint("Ana@Clinica.pt")
    assert first == privacy.email_fingerprint("  ana@clinica.pt ")
    assert first != privacy.email_fingerprint("ana2@clinica.pt")
    assert len(first) == 16 and all(ch in "0123456789abcdef" for ch in first)
    assert "ana" not in first


def test_fingerprint_uses_its_dedicated_key_not_the_session_key(monkeypatch):
    monkeypatch.setattr(settings, "PRIVACY_FINGERPRINT_KEY", None)
    development = privacy.email_fingerprint("ana@clinica.pt")

    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "a-completely-different-session-key-0123456789")
    assert privacy.email_fingerprint("ana@clinica.pt") == development

    monkeypatch.setattr(settings, "PRIVACY_FINGERPRINT_KEY", "dedicated-fingerprint-key-0123456789abcdef")
    keyed = privacy.email_fingerprint("ana@clinica.pt")
    assert keyed != development
    monkeypatch.setattr(settings, "PRIVACY_FINGERPRINT_KEY", "another-fingerprint-key-0123456789abcdefgh")
    assert privacy.email_fingerprint("ana@clinica.pt") != keyed


# --- test database safety ---------------------------------------------------------


def _ok(url: str, *, environment: str | None = None, extra_hosts: str | None = None) -> str:
    return validate_test_database_url(url, environment=environment, extra_hosts=extra_hosts)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@localhost:5432/myvita_test",
        "postgresql://u:p@127.0.0.1/myvita_test",
        "postgresql+psycopg://u:p@localhost:55432/anything_test",
    ],
)
def test_accepts_local_test_databases(url):
    assert _ok(url) == url


@pytest.mark.parametrize(
    ("url", "environment", "extra_hosts", "message"),
    [
        (None, None, None, "not set"),
        ("", None, None, "not set"),
        ("postgresql+psycopg://u:p@localhost/myvita", None, None, "must end in '_test'"),
        ("postgresql+psycopg://u:p@localhost/myvita_test_backup", None, None, "must end in '_test'"),
        ("postgresql+psycopg://u:p@db.example.com/myvita_test", None, None, "Only local hosts"),
        ("postgresql+psycopg://u:p@localhost/myvita_test", "production", None, "ENVIRONMENT=production"),
        ("postgresql+psycopg://u:p@localhost/myvita_test", "staging", None, "ENVIRONMENT=staging"),
        ("sqlite:///myvita_test", None, None, "PostgreSQL"),
        ("::not a url::", None, None, "not a valid"),
    ],
)
def test_refuses_anything_that_could_be_a_real_database(url, environment, extra_hosts, message):
    with pytest.raises(UnsafeTestDatabaseError, match=message):
        _ok(url, environment=environment, extra_hosts=extra_hosts)


def test_extra_hosts_must_be_listed_explicitly():
    url = "postgresql+psycopg://u:p@postgres/myvita_test"
    with pytest.raises(UnsafeTestDatabaseError):
        _ok(url)
    assert _ok(url, extra_hosts="ci-db, postgres") == url
