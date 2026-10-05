# Access governance

Backend authorization is the source of truth; the UI is not a control. The authoritative role matrix is [`docs/pilot-access-matrix.md`](../pilot-access-matrix.md). This document does not repeat it; it records how it is verified and adds the governance around it.

## 1. Role matrix verification

The Phase 1 suite `backend/tests/test_phase1_security.py::test_role_permission_matrix_is_enforced_by_the_backend` exercises more than 200 role-by-operation cells (clinic admin, doctor, nurse, administrative staff, own patient, other patient, anonymous) against the real API and asserts exact status codes. The matrix document and the test encode the same policy; the differences that matter for review are:

- Administrative staff and clinic admin: no clinical records, medications or consents; appointment `reason` is returned as null.
- Doctor and nurse: identical rights today (flagged in the matrix as a clinical decision).
- Patient: own data read, own phone update, own consent grant/revoke; no staff or directory data.
- No role has an audit-log read API, an export API or a delete API.
- There is **no platform/support role**: `UserRole` contains only `patient`, `staff`, `clinic_admin` (guarded by `test_there_is_no_platform_support_role_export_or_audit_read_surface`).

Any difference between intended policy and implementation is a defect or a decision; the policy approvals listed in the matrix are still pending **[DECISION: clinic/clinical lead]**.

## 2. Privileged and support access

Finding: the application has no support access. Operators nonetheless have **infrastructure access** (host, Docker, PostgreSQL, backup bucket, GitHub/CI, secret store), which bypasses every application control. Proposed rules, to be accepted before real data:

| Rule | Detail |
|---|---|
| Default | Operators do not read clinical data. Operations use metrics, health endpoints and logs without payloads |
| No permanent superuser | No shared database login; named accounts only; production database access is exceptional |
| Break-glass | Allowed only for a documented incident or a controller instruction (for example a rights request). Requires a ticket naming the clinic and purpose, approval by a second person, time-boxed credentials, and removal afterwards |
| Logging | Record who, when, why, what was accessed. PostgreSQL connection/statement logging for operator sessions **[not configured; TO DO]** |
| Strong authentication | MFA for host, cloud console, GitHub and secret manager accounts **[external dependency]** |
| Impersonation | Not built and not to be built without a new DPIA review |
| Restored backups | Treated as production data: isolated network, access restricted, destroyed after use |

## 3. Joiner / mover / leaver

| Event | Responsible | Procedure | Technical support (verified) | Evidence |
|---|---|---|---|---|
| New clinic staff | Clinic admin | Create an invitation (`POST /invitations/staff`) or, where enabled, direct creation; the invitee sets their own password; token expires (24 h default) | Invitation stores token digest only | Audit `invitation_created`, `invitation_accepted` (`staff_created` on direct creation) |
| Role change | Clinic admin | `PATCH /staff/{id}/role` | `token_epoch` is bumped: all existing sessions of that user end (`test_privilege_changes_bump_token_epoch_and_revoke_sessions`) | Audit `staff_updated` |
| Staff leaves | Clinic admin, same day | `POST /staff/{id}/deactivate` (not self) | Login refused and live sessions revoked immediately (`test_inactive_user_cannot_log_in_and_live_session_is_revoked`) | Audit `user_disabled` |
| Compromised account | Clinic admin + operator | Deactivate at once; preserve audit rows; investigate per [INCIDENT_RESPONSE_PRIVACY.md](INCIDENT_RESPONSE_PRIVACY.md) | Revocation as above | Incident record |
| Account recovery after compromise | Clinic admin | **No password reset or admin reset exists** (Phase 2 not implemented); a user can only change a known password. Operators must not set passwords by hand | Gap | Raise as a blocker for pilot operations |
| MFA reset | n/a | **MFA is not implemented** | Gap | n/a |
| Temporary user | Clinic admin | Create normally and deactivate on the end date; accounts have no automatic expiry | Gap: no expiry date field | Access review entry |
| Patient leaves | Clinic admin | `POST /patients/{id}/deactivate`; data retention continues per policy | Same revocation | Audit `user_disabled` (the enum value `patient_deleted` is not used) |
| Clinic termination | Controller + operator | [CLINIC_OFFBOARDING.md](CLINIC_OFFBOARDING.md) | n/a | Offboarding checklist |

## 4. Periodic access review

| Population | Frequency (proposal for a pilot) | Reviewer | Method | Evidence |
|---|---|---|---|---|
| Clinic admins and staff accounts | Monthly during the pilot, then quarterly | Clinic admin, countersigned by clinic privacy contact | List via `GET /staff`; deactivate dormant or departed users; confirm roles | Signed review note |
| Patient accounts | Quarterly | Clinic admin | Look for duplicate/inactive accounts | Review note |
| Operators (host, DB, backups, secrets) | Monthly | Operator lead and a second person | Compare access lists with named staff; remove dormant | Access list snapshot |
| GitHub / CI | Quarterly | Repository owner | Collaborators, deploy keys, tokens, Actions secrets | Snapshot |
| Backup credentials | Quarterly or on staff change | Operator lead | Confirm prefix-scoped write-only keys; rotate | Rotation record |
| Dormant detection | Each review | Reviewer | There is **no last-login field**; use `audit_logs` `login_success` per `actor_user_id` | Query output (identifiers only) |

## 5. Audit-log governance

| Question | Current state | Proposal |
|---|---|---|
| Who can read audit logs | No application role; DB operators only | Keep it that way; reading is a break-glass act under section 2; a clinic-facing "who accessed my record" report needs controller approval and a design |
| What is recorded | Login success/failure, logout, password change, user/patient/staff/appointment/consent/record/medication events, permission denied, CSRF failure, rate limit; clinical **views** (`staff_viewed_patient`, `medical_record_viewed`, `medication_viewed`, `consent_viewed`, `patient_viewed_own_record`) | Sufficient for accountability and investigation |
| Content | Identifiers only; tests assert no passwords, tokens, cookies, record text or secrets (`test_audit_trail_contains_no_secrets_or_clinical_content`) | Keep the rule; add a test per new event |
| Integrity | Append-only by convention; the application role can still UPDATE/DELETE; audit writes fail open | Separate DB roles and revoke UPDATE/DELETE on `audit_logs` for the app role; decide which actions must fail closed **[DECISION: security/privacy]** (also noted in `docs/data-security-policy.md`) |
| Retention | Indefinite | Set by the controller ([RETENTION_MATRIX.md](RETENTION_MATRIX.md)) |
| Export | None | Investigation extracts are operator procedures with the same break-glass rules; extract identifiers only |
| Investigation procedure | None formalised | Query by `resource_id`/`actor_user_id`/time window; correlate with request id in the application log (`X-Request-ID` is returned and logged); record query and findings in the incident file |
