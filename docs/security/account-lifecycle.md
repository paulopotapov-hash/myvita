# Account lifecycle, MFA and access recovery

Status: **implemented (Phase 1)**. Self-service delivery of reset links (e-mail/SMS) remains **blocked** until a delivery provider and an identity-verification policy are approved (see `../p6-mfa-password-recovery.md`). Until then, recovery always involves a person: the clinic admin, or the platform operator for clinic admins.

## Roles and obligations

| Role | MFA | Who recovers the account |
|---|---|---|
| `patient` | optional (opt-in on *Segurança*) | clinic admin of the patient's clinic |
| `staff` | **mandatory** (`MFA_REQUIRED_FOR_STAFF=true`, enforced in production) | clinic admin of the same clinic |
| `clinic_admin` | **mandatory** | platform operator (procedure below) |

While an account has a pending obligation, every endpoint answers `403` with header `X-Account-Action-Required: <action>`, except `GET /auth/me`, `POST /auth/logout`, `POST /auth/change-password` and MFA enrolment. The frontend shows a gate page for the action and always offers *Terminar sessão*. Actions, in order of precedence:

1. `password_change` — set by an admin (or on admin-chosen initial passwords). Cleared by changing the password or completing a reset.
2. `mfa_verification` — MFA is enabled but the session was not established with it. Sign out and log in again.
3. `mfa_setup` — the role requires MFA and none is enrolled.

## Login contract

- `POST /api/v1/auth/login` → `200` + `UserPublic` (session cookie) when no second factor is enrolled; `202` + `{"mfa_required": true}` when it is. A `202` creates **no session**, only a 5-minute `httpOnly`, `SameSite=Strict` challenge cookie scoped to `/api/v1/auth/mfa`, signed with a key and purpose distinct from session tokens.
- `POST /api/v1/auth/mfa/verify {"code"}` exchanges the challenge plus a TOTP code or a recovery code for a session marked `mfa=true`.
- `UserPublic` always carries `must_change_password`, `mfa_enabled`, `mfa_required` and `pending_action`.

## MFA (TOTP)

- RFC 6238, SHA-1, 6 digits, 30 s steps, ±1 step drift. A step is accepted at most once (`last_used_step`), so codes cannot be replayed.
- 5 consecutive failures lock the second factor for 15 minutes (`429`), on top of per-IP rate limits.
- Seeds are encrypted with AES-256-GCM under a subkey of `MFA_ENCRYPTION_KEY`, with the user id as associated data. **Losing or changing `MFA_ENCRYPTION_KEY` invalidates every enrolment**: everyone with MFA must be reset and enrol again. Rotate it only together with a planned mass re-enrolment.
- 10 single-use recovery codes, shown once, stored as HMAC-SHA256 under a separate subkey. They can be used to log in, but not to disable MFA or regenerate codes (those need a TOTP code).
- Enabling MFA revokes all earlier sessions. Staff and admins cannot disable mandatory MFA; patients can, with password + TOTP.

## Password reset and change

- **Admin-issued reset** (*Contas* page, `POST /api/v1/users/{id}/password-reset`): returns a 384-bit token **once**; only its SHA-256 is stored; it expires after `PASSWORD_RESET_EXPIRE_MINUTES` (default 60). Issuing a new link, deactivating the account or completing any reset revokes outstanding links. The link carries the token in the URL fragment (`/redefinir-palavra-passe#token=…`), which browsers never send to servers. Hand it over in person or through an already-verified channel; never by the channel the request came from if identity is in doubt.
- **Completing a reset** sets the new password, clears `must_change_password`, revokes every session (`token_epoch`) and all other links. It **does not bypass MFA**.
- **Anonymous request** (`POST /auth/password-reset/request`): never issues a token. It always answers the same way, and records an audit event with **no actor**, the matching account (if any) as the resource, and only a masked e-mail plus a keyed fingerprint (`PRIVACY_FINGERPRINT_KEY`).
- **Admin guard rails**: own clinic only (others → `404`), never the admin's own account (`409`), and never another clinic admin's credentials (`403`). An admin cannot deactivate themselves ("Não pode desativar a própria conta.") and the last active admin of a clinic can never be deactivated.

## Clinic admin recovery (operator procedure)

Use this when a clinic admin forgot their password, lost their MFA device **and** recovery codes, or is otherwise locked out. Another clinic admin of the same clinic can only deactivate/reactivate them, never touch their credentials.

1. **Open a ticket** with the request. Record who asked, when, and through which channel.
2. **Verify identity out of band**, never only through the channel the request arrived on. Use at least one of: a call back to a number already on file for the clinic; confirmation by the clinic's legal representative or another active clinic admin; in-person verification. If identity cannot be verified, **stop**.
3. **If the account may be compromised**, have another active admin of that clinic deactivate it first. If there is none, run `reset-mfa` and `issue-password-reset` anyway: both revoke every session and outstanding link. Then escalate under the incident procedure (`../pilot-incident-response.md`).
4. **Run the recovery tool** on the production host, inside the backend container, which already has the runtime database credentials and keys:

   ```sh
   # Lost MFA device and recovery codes:
   docker compose -f docker-compose.prod.yml run --rm --no-deps backend \
     python -m app.account_recovery reset-mfa --email <admin e-mail> --ticket <ticket id>

   # Forgotten password (prints a one-time link path, valid PASSWORD_RESET_EXPIRE_MINUTES):
   docker compose -f docker-compose.prod.yml run --rm --no-deps backend \
     python -m app.account_recovery issue-password-reset --email <admin e-mail> --ticket <ticket id>
   ```

   The tool only acts on active `clinic_admin` accounts and refuses anything else. Every action is audited with no actor, `via=operator` and the ticket reference. `reset-mfa` revokes every session. The reset token is printed once and never logged or audited.
5. **Hand over the reset link** (`https://<public domain>` + the printed path) through the verified channel from step 2, never in the ticket.
6. **Confirm**: the admin logs in, re-enrols MFA (mandatory), stores the new recovery codes, and the operator checks the audit events (`mfa_reset` / `password_reset_issued` / `password_reset_completed`). Close the ticket with the audit event ids. Never record the token.

Operators never set or transmit a plaintext password, and never edit `users`, `user_mfa` or `audit_logs` with SQL. `audit_logs` is append-only at the database level anyway.

## Configuration

| Variable | Production requirement |
|---|---|
| `MFA_REQUIRED_FOR_STAFF` | must be `true` |
| `MFA_ENCRYPTION_KEY` | urlsafe base64 of exactly 32 random bytes, distinct from `JWT_SECRET_KEY` |
| `PRIVACY_FINGERPRINT_KEY` | ≥ 32 random characters, distinct from `JWT_SECRET_KEY` and `MFA_ENCRYPTION_KEY` |
| `PASSWORD_RESET_EXPIRE_MINUTES` | 5–1440, default 60 |

Generate the MFA key with `python -c "import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` and the fingerprint key with `python -c "import secrets;print(secrets.token_urlsafe(48))"`. In development they are derived or fixed, so local setup needs no extra secrets. The application refuses to start in production without them.
