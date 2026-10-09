# Personal-data breach procedure, severity and vulnerability management

Complements `docs/operations.md` ("Incident response") and `docs/pilot-incident-response.md`. This document adds the privacy dimension. **Whether an incident is a notifiable personal-data breach is decided by the controller with its DPO and legal advisers, never by engineering alone.** Not every security incident is a personal-data breach (GDPR Art. 4(12): a breach of security leading to accidental or unlawful destruction, loss, alteration, unauthorised disclosure of, or access to, personal data).

Legal clock (verified, GDPR Art. 33): the controller must notify the supervisory authority without undue delay and, where feasible, within 72 hours after becoming aware, unless the breach is unlikely to result in a risk to individuals; the processor must notify the controller without undue delay after becoming aware (Art. 33(2)); high risk to individuals also requires communication to them (Art. 34). The exact start of the 72 hours is a legal question, so **record the moment of awareness precisely**.

## 1. Procedure

| Phase | Responsible | Actions | Evidence produced |
|---|---|---|---|
| Detect | Anyone; on-call operator | Alert, user report, audit anomaly, third-party notice. **Write down the date/time and who first became aware** | Incident ticket opened with `T0 = awareness time` |
| Triage | Operator incident lead | Classify severity (section 2) and whether personal data may be involved | Severity + privacy flag in ticket |
| Contain | Operator, with clinic admin for account actions | Revoke sessions (deactivate the user / bump epoch), rotate credentials, remove traffic, isolate hosts. Do not delete evidence or run destructive commands | Containment log |
| Preserve evidence | Operator | Section 4 | Evidence manifest |
| Assess data | Operator + clinic | Which tenants, which tables, which time window, categories of data, approximate number of records and subjects, whether data was encrypted/unintelligible to the recipient, whether it is a confidentiality, integrity or availability breach | Assessment note (identifiers only) |
| Identify controller | Operator | The affected clinic(s) are controllers; the operator is controller only for its own data (platform logs, operator accounts) | Controller list |
| Escalate and notify the controller | Operator incident lead | **Notify each affected clinic's contact immediately** (contractual maximum interval to be agreed). Provide: what is known, when awareness occurred, data categories, mitigations, a contact | Notification record with timestamps |
| Support controller decision | Operator | Provide facts for the Art. 33(3) content (nature, categories and approximate numbers, likely consequences, measures); information can be provided in phases (Art. 33(4)) | Facts sheet |
| Document | Controller (Art. 33(5)); operator keeps its own | Timeline, effects, remedial actions, decisions including a decision *not* to notify with the reasoning | Breach register entry |
| Remediate | Engineering | Fix root cause, add regression test, rotate secrets, verify | Fix commit, test, verification |
| Review | Operator + clinics | Post-incident review within a short fixed period; update the DPIA and this document | Lessons-learned note |

## 2. Severity classification

| Level | Meaning | Privacy examples | Initial response |
|---|---|---|---|
| **SEV-1 Critical** | Confirmed or highly likely exposure of health data to unauthorised parties, or loss of all data | Cross-tenant health-data disclosure; database exposed publicly; stolen clinic-admin or operator credentials in use; lost or leaked backup; ransomware | Immediate, contain first, controller notified at once |
| **SEV-2 High** | Probable exposure or serious control failure without confirmed disclosure | Stolen single staff session; authorisation bug found but not exploited; unauthorised operator access | Same day; assess for breach |
| **SEV-3 Medium** | Security event with limited privacy impact | Sustained failed-login or rate-limit attack with no success; sensitive field briefly logged | Within the working day |
| **SEV-4 Low** | No personal-data impact | Minor UI error, a single mistyped login, noisy alert | Normal backlog |

Privacy impact raises severity by one level when special-category data is in scope.

## 3. Mapping of detections available today

Alerts: `MyVitaAuthenticationFailuresHigh`, `MyVitaAuthorizationDenialsHigh`, backend/PostgreSQL down, backup failures (`monitoring/alerts.yml`). Audit events `permission_denied`, `csrf_failure`, `rate_limited`, `login_failure`. **Not available**: alerts for unusual volumes of clinical reads by one account, impossible-travel, MFA anomalies (no MFA). Alertmanager has **no human receiver configured**, so none of these currently reach a person.

## 4. Evidence preservation

Preserve without copying patient content:

- Audit rows by time window and identifiers (query output kept in the incident file, access limited).
- Application logs for the same window: they carry request id, method, path (no query), status, duration. Export the relevant lines, not whole files.
- Deployed version: image digests and the commit SHA; `alembic current`; configuration with secrets removed.
- Infrastructure logs: host/auth logs, proxy logs, cloud audit logs, backup access logs, timestamps in UTC with the clock source noted.
- Hash the evidence files and record who handled them.
- Do not restore a production backup to a convenience location for analysis; use an isolated, access-controlled environment and delete it afterwards.

## 5. Vulnerability management

| Source | Current practice | Proposed response |
|---|---|---|
| Python dependencies | `pip-audit` is a blocking CI gate; zero exceptions at present (`backend/SECURITY-EXCEPTIONS.md`); PyJWT upgraded to 2.15.1 in Phase 2 baseline to clear 8 advisories | Critical or actively exploited and reachable: patch or mitigate promptly and verify with the test suite; High: schedule in the next release cycle; others: routine updates |
| npm dependencies | `npm audit --audit-level=high` in CI; 0 vulnerabilities at the last run | Same tiers |
| Container images | Pinned tags; no image scan evidenced | Add an image scan to CI before production **[gap]** |
| Exceptions | Must name advisory, affected surface, compensating controls, owner, review date | Never added only to make CI pass; review dates enforced |
| Advisories | No subscription process defined | Subscribe to FastAPI/Starlette/PyJWT/PostgreSQL/nginx advisories and GitHub Dependabot (already opening PRs) |

Remediation targets must be agreed by the team that will meet them; this document deliberately sets no numeric SLA. **[DECISION: operator lead]**
