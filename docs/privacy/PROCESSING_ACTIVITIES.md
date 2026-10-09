# Draft record of processing activities (RoPA)

Draft for controller review (GDPR Art. 30). **No legal basis below is confirmed.** "Proposed" entries are hypotheses derived from how the software works. The controller (the clinic, see [SUBPROCESSORS.md](SUBPROCESSORS.md)) must confirm identity, legal basis (Art. 6), Art. 9(2) condition, retention and recipients. **[DECISION: controller/legal/DPO]** applies to every row.

Distinguish three things that are easy to confuse:

1. **GDPR legal basis** (Art. 6) and **Art. 9 condition** for health data: chosen by the controller; consent is not assumed to be the universal basis.
2. **Clinical or treatment consent**: a healthcare/ethical matter, not the same as GDPR consent.
3. **Product consent records** in myVita (`consents` table: type, purpose, policy snapshot, grant/revoke): evidence of choices captured in the app; their legal effect depends on how the clinic uses them.

Common fields for all rows unless stated: controller = clinic **[TO CONFIRM]**; international transfers = none known, hosting location **[TO CONFIRM]**; security controls = tenant isolation, RBAC, CSRF, session revocation, audit logging, backups (see [DATA_FLOW.md](DATA_FLOW.md) and [ACCESS_GOVERNANCE.md](ACCESS_GOVERNANCE.md)).

| ID | Activity | Purpose | Data subjects | Personal data | Special-category | Recipients / processors | Retention | Proposed Art. 6 basis | Proposed Art. 9 condition | Validation required |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 | Staff and admin account management | Give clinic personnel access | Clinic staff, clinic admins | email, name, role, staff role, specialty, license number, password hash | No | Clinic; myVita operator as processor; hosting **[TBD]** | While employed + clinic policy **[DECISION]** | Contract / legitimate interests of the clinic **[controller to confirm]** | n/a | Employment-context rules (Art. 88 national law) |
| P2 | Patient account and identity | Identify the patient and let them see their own data | Patients | email, name, birth date, phone, national health number | Yes (patient status, health identifier) | Clinic staff per RBAC; processor; hosting | Per clinical record rules **[DECISION]** | Likely Art. 6(1)(b)/(c)/(e) depending on clinic type **[legal]** | Likely Art. 9(2)(h) with Art. 9(3) secrecy **[legal]** | National identifier conditions (Art. 87); clinic type (private/public) |
| P3 | Appointment scheduling | Organise care | Patients, staff | schedule, status, reason, notes, notifications | Yes (`reason`, `notes`) | Same-clinic staff; patient | Per record rules **[DECISION]** | As P2 | As P2 | What may go in `notes`; administrative roles never see `reason` |
| P4 | Clinical documentation | Document care | Patients | record title and content, revisions, author | Yes | Same-clinic doctors/nurses; patient (read) | Legal retention for clinical records **[DECISION: law/clinic]** | As P2 | As P2 | Patient access policy; revision retention |
| P5 | Medication management | Record prescribed medication | Patients | name, dosage, route, frequency, instructions, dates, status | Yes | As P4 | As P4 | As P2 | As P2 | Not a prescription system; no e-prescription integration |
| P6 | Consent recording | Evidence of in-app consents | Patients | consent type, purpose, policy version/text, timestamps | May imply health context | Patient; same-clinic doctors/nurses | Evidence period **[DECISION]** | Controller to define; GDPR consent only where the controller relies on it | If consent is used for Art. 9(2)(a), it must be **explicit** and meet Art. 7 | Approved policy texts; effect of revocation; old consents |
| P7 | Authentication, sessions, abuse protection | Secure access, prevent abuse | All users | password hash, session/CSRF cookies, IP, user agent, rate-limit events | No | Processor | Session 30 min; audit per policy **[DECISION]** | Legitimate interests (security) / legal obligation (Art. 32) **[controller and processor to confirm]** | n/a | Whether myVita is controller or processor for security logs |
| P8 | Audit logging | Accountability, investigation, clinical traceability | Users, patients (as resources) | actor email/id, action, resource id, IP, user agent, outcome | Indirect (care relationship via ids) | Operators; no API reader | **[DECISION]** | Legal obligation / legitimate interests | n/a | Who may read, retention, immutability (see gaps) |
| P9 | Operational logging and monitoring | Run the service | Users | request id, path, status, client IP, user id (login/logout) | No (query strings excluded) | Operator; monitoring stack | Logs rotated 10 MB x 5; Prometheus 15 d | Legitimate interests (security/operations) | n/a | Log retention for incident investigation |
| P10 | Backup and recovery | Availability and integrity | All | Full database copy | Yes | Backup destination **[TBD]** | Local 14 d, off-site 30 d (defaults) **[DECISION]** | Legal obligation (Art. 32(1)(c)) / processor duty | As P2 | Provider, region, encryption evidence, deletion cycle |
| P11 | Invitations | Onboard staff/patients | Invitees | email, name, role | No | Inviter | Until accepted/expired (24 h default); rows are kept | Contract / legitimate interests | n/a | Expired-row cleanup not automated |
| P12 | Support access | **None defined**: no support role or tooling exists | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Define before any operator touches production data |
| P13 | Email / SMS / AI / analytics | **Not performed** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Adding any of these requires a new RoPA entry and DPIA review |

## Observations that affect the RoPA

- The processing is multi-tenant: each clinic is a separate controller of its own patients' data. The operator must not combine data across clinics (the code isolates by `clinic_id`; tests prove cross-clinic denial).
- P7, P8 and P9 are partly the operator's own purpose (running and securing a service). Whether this makes myVita a controller for those logs is a legal classification. **[DECISION: legal/DPO]**
- There is no profiling or automated decision-making (Art. 22): none is implemented.
