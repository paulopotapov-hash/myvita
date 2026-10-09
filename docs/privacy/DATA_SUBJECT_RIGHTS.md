# Data-subject rights: procedures and export

Roles: the **clinic (controller)** receives and decides every request; the **myVita operator (processor)** assists on documented instruction (GDPR Art. 28(3)(e)). The operator must forward any request it receives to the clinic without acting on it. Deadlines are the controller's: one month from receipt, extendable by two months for complexity, with reasons (Art. 12(3)); free of charge unless manifestly unfounded or excessive (Art. 12(5)). **[DECISION: controller/DPO]** for every outcome. Not every right applies identically to clinical records (for example Art. 17(3)(b),(c),(e) limit erasure, Art. 20 applies only to consent/contract bases processed automatically).

## What the software can do today

| Right | Self-service in myVita | Operator-assisted today | Gap |
|---|---|---|---|
| Access (Art. 15) | Patient reads own profile, appointments, medical records, medications, consents, notifications through the UI/API | Clinic doctor/nurse can read same-clinic records | **No single consolidated, machine-readable export**; audit information about the patient is not exposed (no audit read API) |
| Rectification (Art. 16) | Patient can edit own phone only | Doctor/nurse can update supported demographics and write new record versions (revisions keep history) | Rectifying clinical content creates a new revision; the original remains by design |
| Restriction (Art. 18) | None | Clinic admin can deactivate a patient (blocks login, keeps data) | **No true "restricted processing" flag** that blocks clinical use while keeping the record |
| Objection (Art. 21) | None | Case by case | Applies only to Art. 6(1)(e)/(f) bases; controller decides |
| Erasure (Art. 17) | None | None; no delete tool by design | See [RETENTION_MATRIX.md](RETENTION_MATRIX.md); clinical records are normally retained by law **[DECISION: legal]** |
| Portability (Art. 20) | None | None | Likely limited applicability; if required, build the export below |
| Withdraw consent | Patient revokes own consents; history kept | n/a | Effect of revocation on clinical access is **not implemented**: the code records revocation but does not gate clinical access on it. Do not tell patients otherwise **[DECISION: product/legal]** |

## Procedure (all requests)

| Step | Responsible role | Trigger / action | Evidence produced |
|---|---|---|---|
| 1 Receive and log | Clinic privacy contact | Request arrives (any channel); record date, requester, right invoked | Request register entry (outside myVita) |
| 2 Verify identity | Clinic | Use existing account login where possible; otherwise reasonable checks (Art. 12(6)); never ask the operator to bypass login or reset a password | Verification note |
| 3 Assess | Clinic privacy contact with DPO | Decide scope, applicable exceptions, third-party data, legal holds | Decision record with reasons |
| 4 Instruct operator if help is needed | Clinic -> operator | Written instruction naming one patient and one right | Instruction ticket |
| 5 Gather | Operator, only on instruction | Use the least-privileged method below | Gathering log: who, when, what, where stored |
| 6 Deliver | Clinic | Secure channel; do not email clinical data in clear | Delivery record |
| 7 Close | Clinic | Reply within one month (or extension notice) | Closed register entry |

## Subject-access gathering (current manual method)

For one patient `P` in clinic `C`, using an authorised clinical account of clinic `C` (never a platform bypass):

1. `GET /api/v1/patients/{P}` (identity), `GET /api/v1/patients/{P}/medical-records` and each `.../revisions`, `GET /api/v1/patients/{P}/medications`, `GET /api/v1/patients/{P}/consents`, `GET /api/v1/appointments` (paginated, clinic-wide for staff: pick the patient's rows; there is no patient filter).
2. Notifications are owned by the patient's user: only the patient can list them via the API.
3. Audit events about the patient: operator-run database query on `audit_logs` filtered by `resource_id`/`actor_user_id`, returned only after the controller decides what is disclosable (they include other people's emails and IPs; Art. 15(4) protects the rights of others). Document the query and the redactions.
4. Each read by clinical staff is itself audited (`staff_viewed_patient`, `medical_record_viewed`, ...), so the access is traceable.

## Export design (not built; requires controller approval)

Requirement from this phase: avoid a bulk endpoint that allows easy mass exfiltration. If a consolidated export is approved, it must:

- be **per patient**, never per clinic or "all";
- be available only to (a) the patient for their own data and (b) doctor/nurse of the same clinic on the controller's instruction, never to administrative roles;
- be clinic-scoped from the session, rate-limited, CSRF-protected, and produce an audit event (new `AuditAction`, resource id only, no content);
- return a structured file (JSON) generated on the fly, not stored on the server, delivered over the authenticated session;
- exclude other persons' data (staff emails reduced to names and roles);
- have a maximum size and one active request per patient.

A bulk or clinic-wide export for offboarding is a separate controlled operator procedure ([CLINIC_OFFBOARDING.md](CLINIC_OFFBOARDING.md)), not an API.

## Tests that exist

There is no export, so there is nothing to test for it. `test_there_is_no_platform_support_role_export_or_audit_read_surface` fails if an export-, audit- or support-like path is added, forcing a deliberate review and tests for it.
