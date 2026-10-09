# myVita privacy and governance pack (Phase 5)

Status: **ENGINEERING DRAFT. LEGAL/DPO APPROVAL: PENDING.** This pack documents what the system actually does and proposes governance. It is not legal advice and it does not claim GDPR compliance. Every legal classification, legal basis, retention period and contract term is marked **[DECISION: controller/legal/DPO]**.

Baseline: repository commit `5d49174` (branch `frontend-patient-separation`). No staging or production environment exists yet, so hosting, locations and subprocessors are **unknown** and are listed as open items, never assumed. Phase 2 (MFA, password recovery) is not implemented; documents say so where it matters.

## Contents

| File | Purpose |
|---|---|
| [DATA_INVENTORY.md](DATA_INVENTORY.md) | Personal-data inventory, special-category data, minimisation classification |
| [DATA_FLOW.md](DATA_FLOW.md) | Data flows, encryption review, environment separation |
| [PROCESSING_ACTIVITIES.md](PROCESSING_ACTIVITIES.md) | Draft record of processing activities (RoPA) |
| [DPIA_DRAFT.md](DPIA_DRAFT.md) | DPIA assessment draft with threat scenarios and privacy-by-design review |
| [RETENTION_MATRIX.md](RETENTION_MATRIX.md) | Retention, deletion/anonymisation and backup persistence |
| [DATA_SUBJECT_RIGHTS.md](DATA_SUBJECT_RIGHTS.md) | Rights-request procedures and export |
| [ACCESS_GOVERNANCE.md](ACCESS_GOVERNANCE.md) | Role matrix, support access, joiner/mover/leaver, access review, audit-log governance |
| [SUBPROCESSORS.md](SUBPROCESSORS.md) | Role analysis, providers, transfers, AI gate, subprocessor process |
| [DPA_CHECKLIST.md](DPA_CHECKLIST.md) | Article 28 checklist (not a contract) |
| [INCIDENT_RESPONSE_PRIVACY.md](INCIDENT_RESPONSE_PRIVACY.md) | Breach procedure, severity matrix, evidence, vulnerability management |
| [CLINIC_OFFBOARDING.md](CLINIC_OFFBOARDING.md) | Clinic offboarding |
| [PRODUCTION_DATA_POLICY.md](PRODUCTION_DATA_POLICY.md) | Production-data and environment rules, SDLC summary |
| [PRIVACY_NOTICE_DRAFT.md](PRIVACY_NOTICE_DRAFT.md) | Draft notice (pt-PT) with placeholders |
| [COMPLIANCE_MATRIX.md](COMPLIANCE_MATRIX.md) | Evidence matrix and human approval gates |

Existing documents this pack builds on, not replaces: `docs/pilot-access-matrix.md`, `docs/data-security-policy.md`, `docs/operations.md`, `docs/p7-backup-and-restore.md`, `docs/pilot-data-protection-checklist.md`.

## Regulatory boundaries (technical facts only)

- **Medical-device boundary.** Current functionality: stores and displays clinical notes and medications, schedules appointments, records consents. It does not diagnose, predict, score risk, recommend treatment or generate decision support, and contains no AI. No MDR classification is made. If any feature moves toward diagnosis, prediction, treatment recommendation or clinical decision support, **a medical-device regulatory assessment is required** before release.
- **NIS2.** The operator entity, clinic types and service model are not defined, so applicability is unknown. **[DECISION: legal/compliance]**. The technical controls are written to a strong-practice standard regardless of formal scope.
- **National law.** GDPR Art. 9(4) lets Member States add conditions for health data, and Art. 87 lets them set conditions for national identifiers (the patient record carries `national_health_number`). Portuguese implementing law, health-record law and CNPD guidance (including the CNPD Art. 35(4) DPIA list) were **not** verified in this phase; the DPO must confirm them. **[DECISION: DPO/legal]**.

## Secure development lifecycle (as demonstrated in the repository)

Demonstrated: CI with Ruff, `mypy`, pytest, migrations up/down/up, frontend typecheck/lint/tests/build, `pip-audit` and `npm audit`, gitleaks configuration, Alembic migrations, a 176-test backend suite including cross-tenant/IDOR, CSRF, RBAC matrix, audit and privacy tests, branch-based development, production-readiness preflight. Gaps: no enforced code-review rule evidenced in the repo, no container-image vulnerability scan evidenced, no automated staging deploy, Phase 2 authentication features missing.

## What engineering cannot approve

See the human approval gates at the end of [COMPLIANCE_MATRIX.md](COMPLIANCE_MATRIX.md).
