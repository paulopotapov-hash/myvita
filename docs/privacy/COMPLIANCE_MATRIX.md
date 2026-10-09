# Compliance evidence matrix and approval gates

Status vocabulary: **IMPLEMENTED** (code and a test or reproducible evidence exist), **DOCUMENTED** (procedure written, not exercised or not automatable), **NEEDS HUMAN DECISION**, **EXTERNAL DEPENDENCY** (needs infrastructure, a provider or an account that does not exist yet). "Owner" is the proposed accountable role. Nothing here is a statement of legal compliance.

## Traceability

| Requirement / risk | Control | Implementation / evidence | Test / procedure | Owner | Status |
|---|---|---|---|---|---|
| Cross-clinic disclosure (R1) | Tenant isolation: `clinic_id` from session in every query, 404 non-disclosure | `get_current_clinic_id`, service queries | `test_clinic_a_cannot_touch_clinic_b_and_vice_versa_by_id`, `test_cross_tenant_ids_inside_bodies_and_mixed_requests_are_blocked`, `test_cross_tenant_attempts_left_victim_data_untouched` | Engineering | **IMPLEMENTED** |
| Patient-to-patient access (R2) | Own-resource checks | `accessible_patient` | `test_patient_a1_cannot_touch_patient_a2_in_the_same_clinic` | Engineering | **IMPLEMENTED** (403/404 wording differs for some ids; low) |
| Role over-exposure (R8, Art. 25, 32) | Backend RBAC | `require_roles`, role checks | `test_role_permission_matrix_is_enforced_by_the_backend` (>200 cells) | Engineering | **IMPLEMENTED**; policy approval **NEEDS HUMAN DECISION** |
| Default-deny and CSRF | Auth on every non-public route; CSRF on all unsafe methods | `get_current_user` | `test_every_non_public_route_rejects_anonymous_callers`, `test_every_state_changing_route_enforces_csrf_for_authenticated_callers` | Engineering | **IMPLEMENTED** |
| Credential protection | Argon2id, HttpOnly session, HMAC-bound CSRF, 30-min sessions, `token_epoch` | `core/security.py` | Auth/session tests in Phase 1 and existing suites | Engineering | **IMPLEMENTED** |
| Disabled accounts lose access (JML) | Deactivation bumps epoch | staff/patient services | `test_inactive_user_cannot_log_in_and_live_session_is_revoked`, `test_privilege_changes_bump_token_epoch_and_revoke_sessions` | Engineering | **IMPLEMENTED** |
| MFA for privileged users (R3, R4) | None | Phase 2 not implemented (`docs/p6-mfa-password-recovery.md`) | n/a | Engineering | **NOT IMPLEMENTED** (blocker for real data) |
| Password recovery (JML) | None | n/a | n/a | Engineering | **NOT IMPLEMENTED** |
| Audit trail (Art. 5(2), 32) | `record_audit_event`, independent transaction | `core/audit.py` | `test_security_and_clinical_events_are_audited_with_correct_context` | Engineering | **IMPLEMENTED** |
| No secrets or clinical text in audit (R13) | Identifier-only metadata rule | `models/audit_log.py` | `test_audit_trail_contains_no_secrets_or_clinical_content` | Engineering | **IMPLEMENTED** |
| Audit immutability and fail-closed policy (R13) | None at DB level | Append-only by convention | n/a | Security / privacy | **NEEDS HUMAN DECISION** |
| No sensitive data in logs (R15, Art. 5(1)(c)) | Attempted email and query strings not logged; uvicorn access log disabled | `5d49174` | `test_failed_login_application_logs_do_not_contain_the_attempted_email`, `test_request_logs_never_contain_query_strings_such_as_patient_search_terms`, existing `test_no_secrets_in_logs_across_a_full_auth_flow`; manual log check on the dev stack | Engineering | **IMPLEMENTED** |
| Platform client enumeration (R16) | Public clinic directory restricted | `clinics/router.py` | `test_clinic_directory_is_not_enumerable_without_public_registration` | Engineering | **IMPLEMENTED** |
| Data minimisation in API (Art. 25) | Minimal list schemas; no hash/epoch exposure | schemas | `test_list_endpoints_return_only_the_minimum_fields` | Engineering | **IMPLEMENTED**; field-level business decisions **NEEDS HUMAN DECISION** |
| No support/export/audit-read/delete surface (R6, R10) | None built | OpenAPI inventory | `test_there_is_no_platform_support_role_export_or_audit_read_surface` | Engineering | **IMPLEMENTED** |
| Operator and break-glass access (R6) | Policy proposed | [ACCESS_GOVERNANCE.md](ACCESS_GOVERNANCE.md) | Access review | Operator lead | **DOCUMENTED**; MFA and logging on infra **EXTERNAL DEPENDENCY** |
| Encryption in transit | HTTPS enforced by config; TLS overlay | Config validation | Not verifiable without a host | Operator | **EXTERNAL DEPENDENCY** |
| Encryption at rest | Host/volume/provider level | None evidenced | Provider evidence | Operator | **EXTERNAL DEPENDENCY** |
| Backups and restore (Art. 32(1)(c)) | Daily dump, checksum, optional S3, isolated restore | `docs/operations.md` drill evidence | Local drill: restore validated, 24 h RPO supported | Operator | **IMPLEMENTED** locally; real destination **EXTERNAL DEPENDENCY** |
| Environment separation | Compose + settings validation | [DATA_FLOW.md](DATA_FLOW.md) | Config validation; real infra check pending | Operator | **IMPLEMENTED** in config; **EXTERNAL DEPENDENCY** to verify |
| Retention and deletion (Art. 5(1)(e)) | Not enforced; design written | [RETENTION_MATRIX.md](RETENTION_MATRIX.md) | n/a | Controller | **NEEDS HUMAN DECISION** |
| Data-subject rights (Arts. 12-22) | Procedure; self-access for patients | [DATA_SUBJECT_RIGHTS.md](DATA_SUBJECT_RIGHTS.md) | Dry run on synthetic data (to do) | Clinic + operator | **DOCUMENTED**; export tool pending decision |
| Breach handling (Arts. 33-34) | Procedure, severity matrix, evidence rules | [INCIDENT_RESPONSE_PRIVACY.md](INCIDENT_RESPONSE_PRIVACY.md) | Tabletop exercise (to do); no human alert receiver | Operator lead | **DOCUMENTED**; alert receiver **EXTERNAL DEPENDENCY** |
| Processor contract (Art. 28) | Checklist | [DPA_CHECKLIST.md](DPA_CHECKLIST.md) | Legal review | Legal | **NEEDS HUMAN DECISION** |
| Sub-processors and transfers (Arts. 28, 44-49) | Inventory (none selected) and process | [SUBPROCESSORS.md](SUBPROCESSORS.md) | Provider selection | Operator + DPO | **EXTERNAL DEPENDENCY** / **NEEDS HUMAN DECISION** |
| RoPA (Art. 30) | Draft | [PROCESSING_ACTIVITIES.md](PROCESSING_ACTIVITIES.md) | Controller review | Controller | **NEEDS HUMAN DECISION** |
| DPIA (Art. 35) | Draft | [DPIA_DRAFT.md](DPIA_DRAFT.md) | DPO consultation and approval | Controller / DPO | **NEEDS HUMAN DECISION** |
| Transparency (Arts. 12-14) | Draft notice | [PRIVACY_NOTICE_DRAFT.md](PRIVACY_NOTICE_DRAFT.md) | Controller completion | Controller | **NEEDS HUMAN DECISION** |
| Production data policy | Written rule + synthetic fixtures | [PRODUCTION_DATA_POLICY.md](PRODUCTION_DATA_POLICY.md) | Seed script guards, git-ignore, gitleaks | Operator | **IMPLEMENTED** / **DOCUMENTED** |
| Clinic offboarding | Procedure | [CLINIC_OFFBOARDING.md](CLINIC_OFFBOARDING.md) | Rehearsal on synthetic clinic (to do) | Operator + clinic | **DOCUMENTED** |
| Vulnerability management | CI gates, no exceptions | `pip-audit`, `npm audit`; PyJWT 2.15.1 | CI | Engineering | **IMPLEMENTED**; image scanning gap |
| AI / LLM gate | None exist; gate defined | [SUBPROCESSORS.md](SUBPROCESSORS.md) | n/a | Product | **DOCUMENTED** |
| Medical-device boundary | Functional description | [README.md](README.md) | Reassess on any decision-support feature | Product / regulatory | **NEEDS HUMAN DECISION** if scope grows |
| NIS2 applicability | Unknown operator/entity | [README.md](README.md) | Legal review | Legal | **NEEDS HUMAN DECISION** |

## Technical results behind the IMPLEMENTED rows (this phase)

Backend: 176 tests pass (171 before this phase plus 5 new privacy tests); Ruff and `mypy app` clean; migrations unchanged (no schema change in Phase 5); `pip-audit` clean at the last run. Frontend: unchanged in this phase. The dev stack was rebuilt and confirmed to emit no query strings in logs.

## Human approval gates (engineering cannot approve these)

| Gate | Decider | Needed before |
|---|---|---|
| Controller identity per clinic; DPO designation (Art. 37) and contact | Clinic / legal | Any real data |
| Art. 6 legal basis per processing activity | Controller / legal | Any real data |
| Art. 9(2) condition (and national conditions, Art. 9(4); national identifier rules, Art. 87) | Controller / legal | Any real data |
| Retention periods for clinical records, audit logs, notifications, consents, backups | Controller / legal | Any real data |
| Effect of consent revocation on clinical access (not implemented today) | Product / legal / clinical lead | Pilot start |
| Patient access scope to clinical records; doctor/nurse equivalence; administrative access (from `pilot-access-matrix.md`) | Clinical lead | Pilot start |
| Final DPIA approval and Art. 36 consultation decision | Controller / DPO | Any real data |
| DPA/Art. 28 contract language, sub-processor approvals, breach-notification interval | Legal / controller | Contract signature |
| Hosting and backup providers, regions, international-transfer assessment and mechanism | Operator / DPO / legal | Infrastructure build |
| Audit log immutability and fail-closed actions | Security / privacy | Pilot start |
| Operator access and break-glass policy acceptance | Operator lead / DPO | Pilot start |
| Breach reportability decisions (case by case) | Controller / DPO | Each incident |
| NIS2 applicability; medical-device classification (only if functionality changes) | Legal / regulatory | As triggered |

## Blocking technical items before real health data (not legal)

1. MFA and password recovery for privileged and clinical users (Phase 2).
2. Evidence of encryption at rest for database host and backups; a real, protected off-site backup.
3. A human alert receiver and a restore timed on real infrastructure.
4. Controlled operator access (named accounts, MFA, access logging).
5. Retention tooling once periods are approved.
