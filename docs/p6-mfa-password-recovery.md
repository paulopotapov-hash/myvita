# P6 MFA and password-recovery architecture

Status: **TOTP MFA and admin-mediated recovery implemented in Phase 1** (see `security/account-lifecycle.md`). Self-service delivery (e-mail/SMS) and WebAuthn remain **BLOCKED BY IDENTITY AND DELIVERY INFRASTRUCTURE**; no insecure local substitute is implemented.

## MFA decision

Prefer WebAuthn/passkeys for phishing resistance, with TOTP as a reviewed compatibility fallback. Enrollment requires a recently authenticated session, re-authentication, audit events, encrypted credential storage and recovery-code generation displayed once. MFA must be mandatory for clinic admins and privileged operational access before production clinical use; the clinic/product security owner must decide patient policy.

Recovery codes must be random, one-time, hashed at rest, rate-limited and revocable. Disabling/replacing MFA requires strong identity verification, audit and session invalidation. SMS is not proposed as the primary factor.

## Password recovery decision

1. Accept an email/identifier and always return a generic response.
2. Create a high-entropy, single-use, digest-only token with short expiry and replacement revocation.
3. Deliver only through a verified provider and approved template/link over HTTPS; never include a password.
4. Rate-limit by trusted client IP and account-safe dimensions without revealing account existence.
5. On successful reset, atomically change the Argon2id hash, consume the token, increment `token_epoch`, revoke all sessions and audit the event without the token.
6. Notify the account owner and provide a compromise path; do not auto-login privileged accounts without reviewed policy.

Required external inputs: verified email/identity provider, sender/domain configuration, secret storage, delivery monitoring, identity-verification/support policy, abuse thresholds, privacy-approved retention and named owner. Until then, recovery is a controlled support escalation; operators must not set or transmit plaintext passwords.


## MFA dev/demo bypass (development and staging only)

`MFA_DEV_BYPASS_EMAILS` lists test accounts (comma-separated) that may pass the second factor with `MFA_DEV_BYPASS_CODE` instead of a TOTP code, so demo accounts need no authenticator app. Rules, each covered by `backend/tests/test_mfa_dev_bypass.py`:

- **Off by default.** The list is empty unless the environment variable sets it.
- **Never in production.** With `ENVIRONMENT=production` and a non-empty list, the settings refuse to load and the app does not start. The service also ignores the list in production.
- **Allowed in staging** when the variable is set, by decision.
- **Only listed accounts, only with the configured code.** Wrong codes count as failures and are audited; a login through the bypass is audited with `method=dev_bypass`. Step-up actions (regenerating recovery codes, disabling MFA) never accept it.
- **Lockout still applies.** An account locked after repeated failures cannot enter, not even with the bypass code.
- **Startup warning.** While the bypass is on, the app logs a WARNING (`myvita.security`) with the environment and the number of listed accounts, never the code or the emails.

**Before any online deployment** (staging included, or any host reachable from the internet), either clear `MFA_DEV_BYPASS_EMAILS` or replace `MFA_DEV_BYPASS_CODE`: its default, `123456`, is public. Check the startup log for the warning above to confirm which state is running.
