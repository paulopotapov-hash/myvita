# DPIA draft (GDPR Art. 35)

Status: **DRAFT for the controller and DPO.** Engineering has filled the factual and technical parts. Risk acceptance, necessity/proportionality conclusions and final approval belong to the controller. **[DECISION: controller/DPO]**

## 1. Is a DPIA likely required?

Art. 35(1) requires one where processing is likely to result in high risk, and Art. 35(3)(b) names processing "on a large scale of special categories of data". myVita processes health data (Art. 4(15), Art. 9) for patients, who are a vulnerable group relative to the provider, in a multi-tenant platform that concentrates many clinics' records. Whether a single small pilot is "large scale" is a judgement the controller must make, but the combination of sensitive data, concentrated hosting and new software is a strong indicator. **Recommendation: perform the DPIA before processing real health data.** The Portuguese supervisory authority's published list under Art. 35(4) and the EDPB/WP29 DPIA guidelines were not re-verified in this phase; the DPO must check them. If residual high risk remains, Art. 36 prior consultation applies.

## 2. Description of processing (Art. 35(7)(a))

See [PROCESSING_ACTIVITIES.md](PROCESSING_ACTIVITIES.md) and [DATA_FLOW.md](DATA_FLOW.md). Summary: clinic staff record appointments, clinical notes (with revisions), medications and consent records for patients of their own clinic; patients can read their own data and grant/revoke consents; one operator hosts the platform for several clinics. No AI, analytics, outbound email, support tooling or third-party APIs exist today.

## 3. Necessity and proportionality (Art. 35(7)(b))

| Question | Engineering finding | Open for controller |
|---|---|---|
| Is each data field necessary? | See minimisation table in [DATA_INVENTORY.md](DATA_INVENTORY.md). Candidates to review: `national_health_number`, `appointments.notes`, `audit_logs.user_agent` | Confirm purpose for each |
| Is each recipient necessary? | Recipients are same-clinic roles only; administrative roles cannot read clinical content or appointment reasons; no external recipient except hosting/backup providers **[TBD]** | Confirm provider list |
| Is each permission necessary? | Matrix in [ACCESS_GOVERNANCE.md](ACCESS_GOVERNANCE.md) is least-privilege by role; patient is read-only except phone and own consents | Approve patient access to clinical records and doctor/nurse equivalence (already flagged in `docs/pilot-access-matrix.md`) |
| Is each log necessary? | Query strings and attempted emails removed from logs; audit log keeps actor email, IP, user agent | Set retention |
| Retention proportionate? | No retention enforcement exists | Define periods ([RETENTION_MATRIX.md](RETENTION_MATRIX.md)) |

## 4. Risk assessment (Art. 35(7)(c)) and mitigations (Art. 35(7)(d))

Likelihood and severity are engineering estimates (L = low, M = medium, H = high) for a pilot **before** the open items are closed. Mitigations are listed only where verified in code or tests (test file: `backend/tests/test_phase1_security.py` unless stated).

| # | Threat scenario | Impact on subjects | Verified mitigations | Gaps / residual risk | Residual |
|---|---|---|---|---|---|
| R1 | Cross-clinic data disclosure | Disclosure of health data to another clinic | `clinic_id` derived from session and applied in every query; non-disclosing 404; cross-clinic IDOR sweep over ~25 operations x all roles (`test_clinic_a_cannot_touch_clinic_b_and_vice_versa_by_id`, `test_cross_tenant_ids_inside_bodies_and_mixed_requests_are_blocked`) | New endpoints could omit scoping; regression suite is the control | M |
| R2 | Patient-to-patient IDOR in the same clinic | Disclosure to another patient | Own-resource checks and 404/403 (`test_patient_a1_cannot_touch_patient_a2_in_the_same_clinic`) | 403-vs-404 wording differs for some existing ids (low; ids are random UUIDs) | L |
| R3 | Privileged account compromise (clinic admin, doctor) | Bulk disclosure within one clinic | Argon2id, HttpOnly cookie, CSRF, rate limiting, 30-minute sessions, `token_epoch` revocation, audit of access | **No MFA** (Phase 2 not implemented); **no password recovery**; no anomaly alerting on clinical reads beyond auth-failure counters | **H** until MFA exists |
| R4 | Lost or phished staff credentials | Same as R3 | Same as R3; deactivation revokes sessions immediately (`test_inactive_user_cannot_log_in_and_live_session_is_revoked`) | No MFA | H |
| R5 | Backup compromise | Disclosure of all clinics' data | Backups not in Git, checksums, off-site is optional, restores run in isolation | Encryption at rest and bucket policy **not evidenced**; backup container holds DB and S3 credentials; no real destination | **H** until provider evidence |
| R6 | Operator/support misuse or malicious insider | Disclosure of all clinics' data | No support role or impersonation endpoint exists (`test_there_is_no_platform_support_role_export_or_audit_read_surface`); no API reads audit logs | Operators with DB or host access can read everything; no break-glass procedure, no operator access log outside DB logs | **H** until access is controlled ([ACCESS_GOVERNANCE.md](ACCESS_GOVERNANCE.md)) |
| R7 | Ransomware / host loss | Loss of availability and integrity | Daily backup, off-site copy path, restore tested (24 h RPO / 4 h RTO targets, drill in `docs/operations.md`) | Real destination and timed restore on real infrastructure pending | M |
| R8 | Incorrect RBAC after a change | Over-exposure within or across roles | Role matrix test of ~200 cells; matrix doc matches the tests | Policy approvals pending ("DECISÃO CLÍNICA NECESSÁRIA" in the access matrix) | M |
| R9 | Software defect exposing data | Any of the above | 176 backend tests, mypy, ruff, security regression tests, request-id correlated logs | Unknown defects remain; no external penetration test | M |
| R10 | Accidental or bulk export | Mass disclosure | **No export or bulk-read endpoint exists**; patient list is paginated (max 100) | A future export feature must be designed per [DATA_SUBJECT_RIGHTS.md](DATA_SUBJECT_RIGHTS.md) | L |
| R11 | Email disclosure | Disclosure via mail | **No email is sent.** Invitation tokens are returned to the inviter and shared out of band | Out-of-band sharing of invitation links is uncontrolled; a future email provider needs a new review | M |
| R12 | Excessive retention | Data kept longer than necessary | None automated | No retention jobs; backups persist copies (30 d off-site) | **H** until policy and tooling exist |
| R13 | Audit-log leakage or tampering | Exposure of access history or loss of accountability | No API reader; secrets and clinical text excluded (`test_audit_trail_contains_no_secrets_or_clinical_content`); independent transaction writes | Not DB-immutable; `actor_email`/IP stored in clear; audit write is best-effort (fails open, logged) | M |
| R14 | Third-party compromise (hosting, backup, registry, CI) | Disclosure or tampering | Few third parties; secrets outside Git; gitleaks configured | Providers not chosen; image provenance and scanning not evidenced | M |
| R15 | Sensitive data in logs | Disclosure to operators or log processors | Fixed in this phase: no attempted email, no query strings (`backend/tests/test_privacy_controls.py`) | Reverse-proxy logs include client IP and path ids | L |
| R16 | Enumeration of platform clients | Reveals which clinics use myVita | Fixed in this phase: public clinic directory limited when registration is off | While public patient registration is enabled the directory is public by design | L |

## 5. Conclusion

Engineering view: the application-level isolation and authorisation controls are strong and tested. The residual **high** risks are all outside application code: **no MFA/password recovery (Phase 2)**, **no evidence of encryption at rest or backup protection**, **no controlled operator access**, and **no retention tooling**. Real health data should not be processed until R3, R5, R6 and R12 are at least mitigated or explicitly accepted in writing by the controller.

| Item | Owner | Status |
|---|---|---|
| Controller identity, DPO consultation (Art. 35(2)) | Controller | PENDING |
| Views of data subjects where appropriate (Art. 35(9)) | Controller | PENDING |
| Risk acceptance and final approval | Controller / DPO | PENDING |
| Art. 36 prior consultation decision | Controller / DPO | PENDING |
| Review trigger | Any new data category, provider, feature (AI, email, export), or incident (Art. 35(11)) | Defined |

## 6. Privacy by design and by default review (Art. 25)

| Area | Finding | Action |
|---|---|---|
| Tenant isolation | By construction in queries and verified by tests | Keep the regression suite mandatory in CI |
| Least privilege | Strong role split; staff admin sees no clinical content | None |
| Patient self-access | Read-only except phone and own consents | Controller to approve scope |
| Default visibility | Patient list returns only `id, clinic_id, full_name, is_active`; staff list omits license number; `/auth/me` omits hash and epoch (`test_list_endpoints_return_only_the_minimum_fields`) | None |
| Search | Name-only, paginated, same clinic, term not logged | None |
| Notifications | Generic fixed text | Keep generic |
| Exports | None exist | Design before building |
| Administration | Clinic admin can deactivate users/patients, change staff roles, create invitations; no clinical content | None |
| Defaults for new users | Public onboarding/registration disabled by default (`ALLOW_PUBLIC_*` false); direct staff creation disabled in production | None |
| Fixed in this phase | Public clinic directory, log content | Done (`5d49174`) |
