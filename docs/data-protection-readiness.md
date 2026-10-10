# Data protection and clinical governance readiness (Portugal / EU)

A readiness checklist, not a statement of legal compliance. It separates what the software and its configuration **implement** from what needs **organisational decisions, contracts, assessments or external evidence**. Applicable frameworks to review with legal counsel include:

- the GDPR (Regulation (EU) 2016/679), especially Arts. 5, 9, 25, 28, 30, 32–36;
- Portuguese Law 58/2019 (GDPR implementation);
- health-data rules for healthcare providers and professional secrecy;
- guidance from the CNPD (the supervisory authority);
- NIS2 obligations if they apply to the operator.

Which of these apply, and to whom, is a legal determination that has not been made.

Status: **IMPL** (implemented and tested in the repository); **CONFIG** (prepared, needs a real environment or provider); **DECISION** (needs an organisational, legal or clinical decision or document); **EVIDENCE** (needs a recorded exercise or audit).

## Technical controls

| Area | Control in myVita | Status | Evidence / gap |
|---|---|---|---|
| Access control | Central clinical policy: tenant, role and active care assignment, re-checked per request; patients see only their own data | IMPL | `app/core/clinical_access.py`; security matrix and per-module tests |
| Data minimisation (API) | Explicit patient-facing schemas without internal staff/clinic ids (records, results, medications, appointments, consents, messages); drafts and internal records answer 404 | IMPL | `test_patient_facing_clinical_privacy.py` (records, results, medications, appointments, consents, conversations); documents still return the patient's own `patient_id` |
| Clinical-record disclosure | Records internal by default; explicit, audited share/unshare; legacy access labelled as such | IMPL | `test_medical_record_visibility_p2_5.py` |
| Integrity of released results | No edit or delete paths; corrections as new linked results; database trigger rejects UPDATE/DELETE of released rows (migration 8d9e0f1a2b3c); runtime DB role has no DELETE | IMPL | The table owner or a superuser can disable the trigger; protection against a database administrator would need an external append-only copy (review item) |
| Accountability (audit) | Append-only audit log (DB trigger and privileges), identifiers only, denials audited; optional SIEM export | IMPL | Retention period of audit logs: DECISION |
| Authentication | Argon2id, short sessions, CSRF, rate limits, mandatory staff TOTP MFA, recovery codes, operator recovery | IMPL | MFA for patients: DECISION |
| Notifications and e-mail | Generic text only; recipients derived server-side; e-mail limited to account links | IMPL / CONFIG | Provider is a sub-processor (DECISION, DPA) |
| Encryption in transit | HTTPS-only production config, HSTS, TLS 1.2+ template, certificate monitoring | CONFIG | Real domain and endpoint verification: EVIDENCE |
| Encryption at rest | Off-site backups encrypted client-side (age) | IMPL (backups) / CONFIG | Host disk and volume encryption: provider EVIDENCE |
| Backup and recovery | Encrypted off-site copies, integrity checks, restore verification, alerts | IMPL / CONFIG | Real bucket with object lock and a timed restore drill: EVIDENCE |
| Monitoring and alerting | Alert rules, human receiver, heartbeat | CONFIG | Real destination and delivery test: EVIDENCE |
| Logs | No clinical content, tokens or typed e-mails in logs; access log off in backend | IMPL | Log retention and central aggregation: DECISION |
| Environment separation | Production validation refuses dev settings; synthetic test data only | IMPL | Who may access production, and how: DECISION (`privacy/ACCESS_GOVERNANCE.md`) |
| Secrets | No secrets in Git (gitleaks in CI); startup validation; rotation guide | IMPL / DECISION | Secret manager and custodians: DECISION |

## Organisational, legal and clinical items (owner must be named)

| Item | Status | Reference |
|---|---|---|
| Controller/processor roles between myVita and each clinic; DPA (Art. 28) | DECISION | `privacy/DPA_CHECKLIST.md` |
| Lawful basis for health data (Art. 6 and Art. 9(2)(h)), purposes | DECISION | `privacy/PROCESSING_ACTIVITIES.md` |
| Records of processing (Art. 30) | DECISION | `privacy/PROCESSING_ACTIVITIES.md` |
| DPIA (Art. 35) and residual-risk acceptance; prior consultation if required | DECISION | `privacy/DPIA_DRAFT.md` |
| DPO designation and contact | DECISION | — |
| Retention and deletion periods (clinical records, documents, messages, results, audit, backups); deletion workflow not built | DECISION, then implementation | `privacy/RETENTION_MATRIX.md` |
| Data-subject rights (access, rectification, restriction, portability) procedure; clinical rectification rules | DECISION / EVIDENCE | `privacy/DATA_SUBJECT_RIGHTS.md` |
| Sub-processors and data location (hosting, object storage, e-mail, alerting, heartbeat, DNS) | DECISION | `privacy/SUBPROCESSORS.md` |
| Breach procedure, roles and contacts; tabletop exercise | DECISION / EVIDENCE | `incident-response.md`, `privacy/INCIDENT_RESPONSE_PRIVACY.md` |
| Privacy notices for patients and staff | DECISION | `privacy/PRIVACY_NOTICE_DRAFT.md` |
| Clinical governance: who may share records with patients, release and correct results, answer messages and escalations, with expected response times | DECISION | `clinical-messaging.md`, `pilot-access-matrix.md` |
| Clinical responsibility for content shown to patients (sharing, results) | DECISION | — |
| Access reviews and break-glass procedure for operators | DECISION / EVIDENCE | `privacy/ACCESS_GOVERNANCE.md` |
| Staff training and confidentiality undertakings | DECISION | — |
| Real patient data | **Not permitted** until the items above are approved | `privacy/PRODUCTION_DATA_POLICY.md` |

No real patient data and no fictitious clinical records belong in any environment covered by this repository. Synthetic fixtures only.
