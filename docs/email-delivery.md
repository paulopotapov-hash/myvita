# Transactional e-mail delivery

Status: **IMPLEMENTED, NOT CONFIGURED.** The integration exists and is tested against a stand-in transport. No real relay, sender domain or credential has been configured or verified. Until that is done, nothing is e-mailed and every response says so.

## What is e-mailed, and what is not

Only two messages exist. Both are about account access, and both are generic:

| Message | Trigger | Contents |
|---|---|---|
| Invitation | Clinic admin invites staff, or an authorized professional/admin invites a patient | One-time activation link, its validity period, "ignore if unexpected" |
| Password reset | Clinic admin issues a reset link; optionally the self-service "forgot password" form | One-time reset link, its validity period, "ignore if you did not ask" |

No clinical information is ever e-mailed: no names of clinicians, results, records, documents, appointments or messages. Clinical events produce **in-app** notifications only (`app/modules/notifications/events.py`). An in-app notification is never presented as an e-mail.

## How delivery works (`backend/app/core/email.py`)

- Authenticated SMTP relay, over STARTTLS (`SMTP_SECURITY=starttls`, port 587) or implicit TLS (`ssl`, port 465). The certificate is verified with the system trust store. There is no unencrypted mode.
- Bounded timeout (`SMTP_TIMEOUT_SECONDS`, default 10 s). Delivery is synchronous for admin actions, so the admin sees the real outcome.
- The result is reported honestly in the API response (`delivery`), in the audit trail (`metadata.delivery`) and in the metric `myvita_email_deliveries_total{result}`:
  - `sent`: the relay accepted the message. This is not proof that it reached the inbox.
  - `failed`: connection, TLS, authentication or relay refusal. The UI tells the admin to hand the link over.
  - `disabled`: e-mail delivery is off; nothing was attempted.
- **No false success.** A failure never reports `sent`, and it never undoes the invitation or reset. The link is still shown to the admin once as the fallback.
- **Retry and duplicates.** There is no automatic retry and no outbox. Tokens are stored only as hashes, so there is nothing to resend from. The admin retries by issuing a new invitation or reset link, which revokes the previous one. A duplicate e-mail can never carry a second valid link.
- **Logs** contain the message kind, a masked recipient and the error class. They never contain the link, the token or the SMTP password.
- Links are built from `PUBLIC_APP_URL`, never from request headers. The token travels in the URL fragment, which browsers do not send to servers or proxies.

## Self-service password reset

`SELF_SERVICE_PASSWORD_RESET_ENABLED` is off by default and requires `EMAIL_DELIVERY_ENABLED`. When on:

- the public form always gives the same answer, whether or not the account exists;
- an active staff or patient account gets a reset e-mail at most once every 5 minutes; the e-mail is sent after the response, so timing does not reveal the account;
- clinic administrators are never reset this way; they use the operator procedure in `security/account-lifecycle.md`;
- the reset still requires MFA at the next login for staff;
- every request is audited, and self-service sends record the real delivery outcome (`via=self_service`).

**Human decision required before enabling it:** the identity-verification and abuse policy, the support path for people who no longer control their mailbox, and the privacy review of e-mail as a recovery channel (`p6-mfa-password-recovery.md`).

## Configuration

| Variable | Notes |
|---|---|
| `EMAIL_DELIVERY_ENABLED` | `false` by default |
| `SMTP_HOST`, `SMTP_PORT` | relay of the chosen provider |
| `SMTP_SECURITY` | `starttls` (587) or `ssl` (465) |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | secret; required in production; set together |
| `SMTP_TIMEOUT_SECONDS` | default 10 |
| `EMAIL_FROM` | no-reply address on a domain with SPF, DKIM and DMARC configured at the provider |
| `PUBLIC_APP_URL` | `https://<PUBLIC_DOMAIN>`; an origin only; HTTPS required in production |
| `SELF_SERVICE_PASSWORD_RESET_ENABLED` | see above |

The settings are validated at startup: incomplete or insecure combinations stop the backend. `scripts/production_preflight.sh` repeats the checks on the deployment environment.

## External setup still required

1. Choose an e-mail provider (a sub-processor: record it in `privacy/SUBPROCESSORS.md`, with data location and DPA).
2. Verify the sender domain (SPF, DKIM, DMARC) and create relay credentials limited to sending.
3. Store `SMTP_PASSWORD` in the secret manager; set the variables above.
4. Send a test invitation to an internal mailbox, confirm receipt, link validity and that the message lands outside spam. Record the evidence.
5. Watch `MyVitaEmailDeliveryFailing`. Rotate the relay credential on staff change or suspicion of compromise (`p7-secret-management.md`).
