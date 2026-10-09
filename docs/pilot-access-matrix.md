# Pilot access matrix

Backend authorization is authoritative; frontend visibility is UX only. Cross-tenant resources are hidden with 404 where the existing non-disclosure policy applies.

"Assigned" means an active care assignment between that professional and that patient (`/patients/{id}/care-team`, managed by the clinic admin; the policy lives in `backend/app/core/clinical_access.py`). Without it, or after it is ended, clinicians get 403 and the patient is absent from their lists. Consent is a separate record and never grants clinical access.

| Resource / operation | Patient | Doctor | Nurse | Physiotherapist | Administrative staff | Clinic admin |
|---|---|---|---|---|---|---|
| Own session/password/MFA | read/change/logout/enrol | same | same | same | same | same |
| Patient directory (incl. name search) | forbidden | assigned patients only | assigned patients only | empty | basic same-clinic identity | basic same-clinic identity |
| Full demographics | own read | assigned read | assigned read | forbidden | forbidden | forbidden |
| Demographic update | own phone only | assigned, supported fields | same as doctor | forbidden | forbidden | forbidden |
| Care-team assignment | forbidden | forbidden | forbidden | forbidden | forbidden | create/end same-clinic |
| Patient deactivate | forbidden | forbidden | forbidden | forbidden | forbidden | same clinic |
| Appointments operational data | own read | assigned read/create/update/cancel | same as doctor | forbidden | same-clinic read/create/update/cancel | same-clinic read/create/update/cancel |
| Appointment reason | own read | assigned read/create/update | same as doctor | forbidden | forbidden | forbidden |
| Appointment requests (P2.3) | create/cancel own; read own | assigned: list/accept/reject | same as doctor | forbidden | same-clinic list/accept/reject | same-clinic list/accept/reject |
| Consent list/detail | own | assigned read | assigned read | forbidden | forbidden | forbidden |
| Consent grant/revoke | own only | forbidden | forbidden | forbidden | forbidden | forbidden |
| Medical records | own read | assigned read/create/version (optimistic `expected_version`) | same as doctor | forbidden | forbidden | forbidden |
| Medication | own read | assigned read/create/update/deactivate | same as doctor | forbidden | forbidden | forbidden |
| Private documents | own read/download | assigned list/upload/download/delete | same as doctor | forbidden | forbidden | forbidden |
| Messages (conversations) | own: start with own professionals, read, reply, mark read | assigned start/read/reply | same as doctor | forbidden | forbidden | forbidden |
| Notifications | own read/mark read/read-all | own | own | own | own | own |
| Staff invitation | forbidden | forbidden | forbidden | forbidden | forbidden | create same-clinic |
| Patient invitation | forbidden | create/list/revoke same-clinic | create/list/revoke same-clinic | forbidden | forbidden | create/list/revoke same-clinic |
| Staff activate/deactivate/role | forbidden | forbidden | forbidden | forbidden | forbidden | same-clinic, not self |
| Account administration (reset link, require password change, MFA reset) | forbidden | forbidden | forbidden | forbidden | forbidden | same-clinic, not self |
| Audit history | no API | no API | no API | no API | no API | no API (reports on request) |

The physiotherapist role exists but has no clinical permissions until the product assigns some; this is deliberate. No other application roles exist. Unknown request fields are rejected; tenant/role/clinic identifiers are server-derived and cannot be assigned through patient or appointment payloads.

All rows containing same-clinic are tenant-scoped by the authenticated user's `clinic_id`. "Own" additionally requires the resource to belong to the authenticated patient/user. There is no clinical hard-delete endpoint except private document removal (audited): patient/staff accounts are deactivated, consent is revoked with history, medication status is changed, and clinical record revisions remain durable.

## Verification against current implementation

- Patients: administrative roles list minimized same-clinic summaries; clinicians list only assigned patients; patient reads own detail; doctor/nurse update supported demographics of assigned patients; clinic admin alone deactivates and manages the care team.
- Appointments and appointment requests: patient reads own; clinic admin and administrative staff operate same-clinic scheduling for any patient; doctors/nurses only for assigned patients. Administrative roles never read/write the clinical reason. Status transitions are restricted to scheduled→confirmed, confirmed→completed/no_show and explicit cancellation.
- Medical records, medication, documents, messages: own-patient read or assigned doctor/nurse access; writes are doctor/nurse only. Record updates carry `expected_version`; a stale edit is refused (409), never merged.
- Consent: patient alone grants/revokes own consent; assigned doctor/nurse read it; admin roles cannot access clinical consent content.
- Notifications and account: always the authenticated user's own resources. Team invitation, staff lifecycle and account administration are clinic-admin scoped; patient invitation follows the clinical-role rules in the router (`INVITE_PATIENT`).
- Audit logs: written internally on a dedicated pool. There is no tenant-facing read API (`GET /api/v1/audit-logs` → 404 for every role); the trail leaves the database only through the SIEM export. Access reports are produced manually by the MyVita team on request.

## Open item (decide with the pilot clinic)

A professional booked by a scheduler for a patient who is **not** on their care team cannot see that appointment until a clinic admin assigns them. This is the existing assignment rule, not a defect; options are (b) refuse the booking/acceptance until assigned (422), or (c) create the assignment automatically on acceptance. See `_integration/open-items.md`.

**DECISÃO CLÍNICA NECESSÁRIA:** approve or change administrative access to appointment operational data, patient access to clinical records, doctor/nurse equivalence, who may correct demographic/clinical data, and the final status-transition policy. Any change requires code and negative authorization tests; the table is descriptive, not approval.
