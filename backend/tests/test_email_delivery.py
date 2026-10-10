"""E-mail delivery of invitation and password-reset links (app/core/email.py, docs/email-delivery.md).

No real relay is contacted: a recording transport stands in for SMTP, and the
real SMTP transport is only exercised against a closed local port (failure path).
"""

import logging
import smtplib
import uuid
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core import email as email_module
from app.core.config import Settings, settings
from app.core.metrics import email_deliveries_total
from app.models import AuditLog, PasswordResetToken, User
from tests.clinical_support import Tenant, make_tenant

APP_URL = "https://app.myvita.test"
_TEST_JWT = "unit-test-signing-key-0123456789abcdefghijkl"


class RecordingTransport:
    def __init__(self, fail: Exception | None = None) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = fail

    def send(self, message: EmailMessage) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append(message)


@pytest.fixture()
def tenant(client: TestClient) -> Tenant:
    return make_tenant(client, "email")


@pytest.fixture()
def email_on(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.myvita.test")
    monkeypatch.setattr(settings, "EMAIL_FROM", "nao-responder@myvita.test")
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", APP_URL)
    transport = RecordingTransport()
    previous = email_module.set_transport(transport)
    yield transport
    email_module.set_transport(previous)


def _audit(client: TestClient, action: str) -> list[AuditLog]:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        rows = db.query(AuditLog).filter(AuditLog.action == action).order_by(AuditLog.timestamp).all()
        for row in rows:
            db.expunge(row)
        return rows


def _invite_patient(client: TestClient, tenant: Tenant, email: str = "novo.paciente@example.pt"):
    return client.post(
        "/api/v1/invitations/patients",
        headers=tenant.act(client, "clinic_admin"),
        json={"email": email, "full_name": "Paciente Convidado"},
    )


def test_delivery_is_reported_as_disabled_and_nothing_is_sent_by_default(client: TestClient, tenant: Tenant):
    transport = RecordingTransport()
    previous = email_module.set_transport(transport)
    try:
        created = _invite_patient(client, tenant)
    finally:
        email_module.set_transport(previous)
    assert created.status_code == 201, created.text
    assert created.json()["delivery"] == "disabled"
    assert created.json()["token"]
    assert transport.sent == []
    assert _audit(client, "invitation_created")[-1].event_metadata["delivery"] == "disabled"


def test_invitation_link_is_emailed_generically(client: TestClient, tenant: Tenant, email_on: RecordingTransport):
    created = _invite_patient(client, tenant)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["delivery"] == "sent"
    (message,) = email_on.sent
    assert message["To"] == "novo.paciente@example.pt"
    assert message["Subject"] == "Convite para o myVita"
    assert message["From"] == "nao-responder@myvita.test"
    text = message.get_content()
    # The link points at the configured public origin, with the token in the fragment.
    assert f"{APP_URL}/convite#token={body['token']}" in text
    assert "Paciente Convidado" not in text and tenant.clinic_id not in text
    row = _audit(client, "invitation_created")[-1]
    assert row.event_metadata["delivery"] == "sent"
    assert body["token"] not in str(row.event_metadata)


def test_a_failed_email_is_reported_without_undoing_the_invitation(
    client: TestClient, tenant: Tenant, email_on: RecordingTransport, caplog
):
    email_on.fail = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    failed_before = email_deliveries_total.snapshot().get(("failed",), 0.0)
    with caplog.at_level(logging.WARNING, logger="myvita.email"):
        created = _invite_patient(client, tenant)
    assert created.status_code == 201
    assert created.json()["delivery"] == "failed"
    # The invitation exists and its link is still handed to the admin as the fallback.
    tenant.act(client, "clinic_admin")
    assert any(row["id"] == created.json()["id"] for row in client.get("/api/v1/invitations").json())
    assert email_deliveries_total.snapshot()[("failed",)] == failed_before + 1
    assert "SMTPAuthenticationError" in caplog.text
    assert created.json()["token"] not in caplog.text
    assert "novo.paciente@example.pt" not in caplog.text


def test_admin_issued_reset_link_is_emailed(client: TestClient, tenant: Tenant, email_on: RecordingTransport):
    issued = client.post(
        f"/api/v1/users/{tenant.user_ids['nurse']}/password-reset", headers=tenant.act(client, "clinic_admin")
    )
    assert issued.status_code == 201, issued.text
    assert issued.json()["delivery"] == "sent"
    (message,) = email_on.sent
    assert message["Subject"] == "Redefinição da palavra-passe do myVita"
    assert f"{APP_URL}/redefinir-palavra-passe#token={issued.json()['token']}" in message.get_content()
    assert _audit(client, "password_reset_issued")[-1].event_metadata["delivery"] == "sent"


def _request_reset(client: TestClient, email: str):
    client.cookies.clear()
    return client.post("/api/v1/auth/password-reset/request", json={"email": email})


def _tokens(client: TestClient, user_id: str) -> int:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.query(PasswordResetToken).filter(PasswordResetToken.user_id == uuid.UUID(user_id)).count()


def _email_of(client: TestClient, user_id: str) -> str:
    with client.session_factory() as db:  # type: ignore[attr-defined]
        return db.get(User, uuid.UUID(user_id)).email


def test_self_service_reset_issues_nothing_unless_enabled(client: TestClient, tenant: Tenant, email_on):
    answer = _request_reset(client, _email_of(client, tenant.user_ids["patient"]))
    assert answer.status_code == 202
    assert "contacte o administrador" in answer.json()["detail"]
    assert _tokens(client, tenant.user_ids["patient"]) == 0
    assert email_on.sent == []


def test_self_service_reset_emails_eligible_accounts_once_per_cooldown(
    client: TestClient, tenant: Tenant, email_on: RecordingTransport, monkeypatch
):
    monkeypatch.setattr(settings, "SELF_SERVICE_PASSWORD_RESET_ENABLED", True)
    patient_email = _email_of(client, tenant.user_ids["patient"])

    unknown = _request_reset(client, "ninguem@example.pt")
    known = _request_reset(client, patient_email)
    # Same answer whether or not the account exists.
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    (message,) = email_on.sent
    assert message["To"] == patient_email
    assert _tokens(client, tenant.user_ids["patient"]) == 1
    sent_row = [r for r in _audit(client, "password_reset_requested") if r.event_metadata.get("via") == "self_service"]
    assert sent_row and sent_row[-1].event_metadata["delivery"] == "sent"

    # A repeated request within the cooldown sends nothing new (no e-mail bombing, no duplicate links).
    assert _request_reset(client, patient_email).json() == known.json()
    assert len(email_on.sent) == 1 and _tokens(client, tenant.user_ids["patient"]) == 1

    # Clinic administrators are recovered by an operator, never by self-service.
    admin_email = _email_of(client, tenant.user_ids["clinic_admin"])
    assert _request_reset(client, admin_email).json() == known.json()
    assert _tokens(client, tenant.user_ids["clinic_admin"]) == 0
    assert len(email_on.sent) == 1


def test_self_service_delivery_failure_is_audited_as_a_failure(
    client: TestClient, tenant: Tenant, email_on: RecordingTransport, monkeypatch
):
    monkeypatch.setattr(settings, "SELF_SERVICE_PASSWORD_RESET_ENABLED", True)
    email_on.fail = smtplib.SMTPServerDisconnected("gone")
    answer = _request_reset(client, _email_of(client, tenant.user_ids["nurse"]))
    assert answer.status_code == 202
    row = [r for r in _audit(client, "password_reset_requested") if r.event_metadata.get("via") == "self_service"][-1]
    assert row.result.value == "failure" and row.event_metadata["delivery"] == "failed"


def test_the_real_smtp_transport_fails_closed_and_fast(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", 1)  # nothing listens there
    monkeypatch.setattr(settings, "SMTP_TIMEOUT_SECONDS", 2.0)
    monkeypatch.setattr(settings, "EMAIL_FROM", "nao-responder@myvita.test")
    monkeypatch.setattr(settings, "PUBLIC_APP_URL", APP_URL)
    previous = email_module.set_transport(email_module.SmtpTransport())
    try:
        result = email_module.deliver(email_module.invitation_email("x@example.test", "t" * 64))
    finally:
        email_module.set_transport(previous)
    assert result == "failed"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"EMAIL_DELIVERY_ENABLED": True}, "SMTP_HOST"),
        (
            {"EMAIL_DELIVERY_ENABLED": True, "SMTP_HOST": "smtp.x.test", "EMAIL_FROM": "a@x.test"},
            "PUBLIC_APP_URL must be set",
        ),
        (
            {
                "EMAIL_DELIVERY_ENABLED": True,
                "SMTP_HOST": "smtp.x.test",
                "EMAIL_FROM": "a@x.test",
                "PUBLIC_APP_URL": "http://app.x.test",
            },
            "HTTPS",
        ),
        (
            {
                "EMAIL_DELIVERY_ENABLED": True,
                "SMTP_HOST": "smtp.x.test",
                "EMAIL_FROM": "a@x.test",
                "PUBLIC_APP_URL": "https://app.x.test/path",
            },
            "origin",
        ),
        (
            {
                "EMAIL_DELIVERY_ENABLED": True,
                "SMTP_HOST": "smtp.x.test",
                "EMAIL_FROM": "a@x.test",
                "PUBLIC_APP_URL": "https://app.x.test",
                "SMTP_USERNAME": "relay",
            },
            "together",
        ),
        ({"SELF_SERVICE_PASSWORD_RESET_ENABLED": True}, "requires EMAIL_DELIVERY_ENABLED"),
    ],
)
def test_incoherent_email_configuration_is_refused_at_startup(overrides: dict, message: str):
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, JWT_SECRET_KEY=_TEST_JWT, **overrides)


def test_production_email_must_authenticate():
    with pytest.raises(ValidationError, match="authenticate"):
        Settings(
            _env_file=None,
            JWT_SECRET_KEY=_TEST_JWT,
            ENVIRONMENT="production",
            EMAIL_DELIVERY_ENABLED=True,
            SMTP_HOST="smtp.x.test",
            EMAIL_FROM="a@x.test",
            PUBLIC_APP_URL="https://app.x.test",
        )
