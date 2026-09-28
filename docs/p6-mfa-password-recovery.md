# P6 MFA and password-recovery architecture

Status: **POST-P6 / BLOCKED BY IDENTITY AND DELIVERY INFRASTRUCTURE**. No insecure local substitute is implemented.

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

