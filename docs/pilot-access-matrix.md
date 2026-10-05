# Pilot access matrix

Backend authorization is authoritative; frontend visibility is UX only. Cross-tenant resources are hidden with 404 where the existing non-disclosure policy applies.

| Resource / operation | Patient | Doctor | Nurse | Administrative staff | Clinic admin |
|---|---|---|---|---|---|
| Own session/password | read/change/logout | same | same | same | same |
| Patient directory | forbidden | read basic same-clinic identity | read basic same-clinic identity | read basic same-clinic identity | read basic same-clinic identity |
| Full demographics | own read | same-clinic read | same-clinic read | forbidden | forbidden |
| Demographic update | own phone only | same-clinic supported fields | same-clinic supported fields | forbidden | forbidden |
| Patient deactivate | forbidden | forbidden | forbidden | forbidden | same clinic |
| Appointments operational data | own read | same-clinic read/create/update/cancel | same | same | same |
| Appointment reason | own read | same-clinic read/create/update | same | forbidden | forbidden |
| Consent list/detail | own | same-clinic read | same-clinic read | forbidden | forbidden |
| Consent grant/revoke | own only | forbidden | forbidden | forbidden | forbidden |
| Medical records | own read | same-clinic read/create/version | same | forbidden | forbidden |
| Medication | own read | same-clinic read/create/update/deactivate | same | forbidden | forbidden |
| Notifications | own read/mark read | own | own | own | own |
| Staff invitation | forbidden | forbidden | forbidden | forbidden | create same-clinic |
| Patient invitation | forbidden | create same-clinic | create same-clinic | forbidden | create same-clinic |
| Staff deactivate | forbidden | forbidden | forbidden | forbidden | same-clinic, not self |
| Audit history | no API | no API | no API | no API | no API |

No other application roles exist. Unknown request fields are rejected; tenant/role/clinic identifiers are server-derived and cannot be assigned through patient or appointment payloads.

All rows containing same-clinic are tenant-scoped by the authenticated user's `clinic_id`. “Own” additionally requires the resource to belong to the authenticated patient/user. There is no clinical hard-delete endpoint: patient/staff accounts are deactivated, consent is revoked with history, medication status is changed, and clinical record revisions remain durable.

## Verification against current implementation

- Patients: staff/admin can list minimized same-clinic summaries; patient can read own detail; doctor/nurse can read/update supported demographics; clinic admin alone can deactivate.
- Appointments: patient reads own; staff and clinic admin operate same-clinic appointments. Administrative roles cannot read/write the clinical reason. Status transitions are restricted to scheduled→confirmed, confirmed→completed/no_show and explicit cancellation.
- Medical records and medication: own-patient read or same-clinic doctor/nurse access; create/update is doctor/nurse only. Notes use optimistic version checks.
- Consent: patient alone grants/revokes own consent; doctor/nurse can read same-clinic consent; admin roles cannot access clinical consent content.
- Notifications and account: always the authenticated user's own resources. Team invitation/deactivation is clinic-admin scoped; patient invitation follows the clinical-role rules in the router.
- Audit logs: written internally; no application role has a read API.

**DECISÃO CLÍNICA NECESSÁRIA:** approve or change administrative access to appointment operational data, patient access to clinical records, doctor/nurse equivalence, who may correct demographic/clinical data, and the final status-transition policy. Any change requires code and negative authorization tests; the table is descriptive, not approval.
