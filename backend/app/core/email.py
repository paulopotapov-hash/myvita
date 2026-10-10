"""
Transactional e-mail (docs/email-delivery.md).

Only two kinds of message exist, both account-related and generic: an
invitation link and a password-reset link. No clinical information is ever
e-mailed; in-app notifications stay in the app.

Delivery is synchronous, over an authenticated SMTP relay with TLS (STARTTLS
or implicit TLS), a verified certificate and a bounded timeout. The result is
reported honestly as one of:

- "sent"     — the relay accepted the message (not proof of inbox delivery);
- "failed"   — connection, TLS, authentication or relay refusal; nothing was
               accepted, or the outcome is unknown;
- "disabled" — EMAIL_DELIVERY_ENABLED is false; nothing was attempted.

Retries are deliberately left to the user: re-issuing an invitation or reset
link revokes the previous token, so a duplicate e-mail can never carry a
second valid link. Tokens are never stored in plaintext, so there is no outbox
to retry from. Logs carry the message kind, a masked recipient and the error
class only — never the link, the token or the SMTP password.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Literal, Protocol

from app.core.config import settings
from app.core.metrics import email_deliveries_total
from app.core.privacy import mask_email

logger = logging.getLogger("myvita.email")

DeliveryResult = Literal["sent", "failed", "disabled"]
EmailKind = Literal["invitation", "password_reset"]

INVITATION_PATH = "/convite#token="
PASSWORD_RESET_PATH = "/redefinir-palavra-passe#token="


@dataclass(frozen=True)
class OutgoingEmail:
    kind: EmailKind
    to: str
    subject: str
    body: str


class EmailTransport(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class SmtpTransport:
    """Authenticated SMTP over TLS with certificate verification and a timeout."""

    def send(self, message: EmailMessage) -> None:
        assert settings.SMTP_HOST is not None
        context = ssl.create_default_context()
        timeout = settings.SMTP_TIMEOUT_SECONDS
        smtp: smtplib.SMTP
        if settings.SMTP_SECURITY == "ssl":
            smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout, context=context)
        else:
            smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout)
        with smtp:
            if settings.SMTP_SECURITY == "starttls":
                smtp.starttls(context=context)
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD.get_secret_value())
            refused = smtp.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)


_transport: EmailTransport = SmtpTransport()


def set_transport(transport: EmailTransport) -> EmailTransport:
    """Swap the transport (tests); returns the previous one."""
    global _transport
    previous, _transport = _transport, transport
    return previous


def _link(path: str, token: str) -> str:
    base = (settings.PUBLIC_APP_URL or "").rstrip("/")
    # The token travels in the URL fragment, which browsers never send to servers or proxies.
    return f"{base}{path}{token}"


def invitation_email(to: str, token: str) -> OutgoingEmail:
    hours = settings.INVITATION_EXPIRE_HOURS
    return OutgoingEmail(
        kind="invitation",
        to=to,
        subject="Convite para o myVita",
        body=(
            "Olá,\n\n"
            "Foi convidado(a) a criar a sua conta no myVita.\n"
            f"Para ativar a conta, abra esta ligação nas próximas {hours} horas:\n\n"
            f"{_link(INVITATION_PATH, token)}\n\n"
            "Se não esperava este convite, ignore esta mensagem e contacte a sua clínica.\n"
            "Esta mensagem foi enviada automaticamente; não responda.\n"
        ),
    )


def password_reset_email(to: str, token: str) -> OutgoingEmail:
    minutes = settings.PASSWORD_RESET_EXPIRE_MINUTES
    return OutgoingEmail(
        kind="password_reset",
        to=to,
        subject="Redefinição da palavra-passe do myVita",
        body=(
            "Olá,\n\n"
            "Foi pedida a redefinição da palavra-passe da sua conta myVita.\n"
            f"Para escolher uma nova palavra-passe, abra esta ligação nos próximos {minutes} minutos:\n\n"
            f"{_link(PASSWORD_RESET_PATH, token)}\n\n"
            "Se não fez este pedido, ignore esta mensagem; a sua palavra-passe não muda.\n"
            "Se receber pedidos que não fez, contacte a sua clínica.\n"
            "Esta mensagem foi enviada automaticamente; não responda.\n"
        ),
    )


def deliver(outgoing: OutgoingEmail) -> DeliveryResult:
    """Send `outgoing`, never raising. See the module docstring for the meaning of the result."""
    if not settings.EMAIL_DELIVERY_ENABLED:
        email_deliveries_total.inc("disabled")
        return "disabled"
    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = outgoing.to
    message["Subject"] = outgoing.subject
    message["Message-ID"] = make_msgid(domain=(settings.EMAIL_FROM or "myvita").split("@")[-1])
    # Ask auto-responders and list software to stay quiet; the content is a one-off link.
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(outgoing.body)
    try:
        _transport.send(message)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        email_deliveries_total.inc("failed")
        logger.warning(
            "E-mail delivery failed: kind=%s to=%s error=%s",
            outgoing.kind,
            mask_email(outgoing.to),
            type(exc).__name__,
        )
        return "failed"
    email_deliveries_total.inc("sent")
    logger.info("E-mail accepted by the relay: kind=%s to=%s", outgoing.kind, mask_email(outgoing.to))
    return "sent"
