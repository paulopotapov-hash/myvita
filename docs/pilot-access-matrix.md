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
