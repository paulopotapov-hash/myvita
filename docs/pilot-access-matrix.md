# Pilot access matrix

Backend authorization is authoritative; frontend visibility is UX only. Cross-tenant resources are hidden with 404 where the existing non-disclosure policy applies.

"Assigned" means an active care assignment between that professional and that patient (`/patients/{id}/care-team`, managed by the clinic admin; the policy lives in `backend/app/core/clinical_access.py`). Without it, or after it is ended, clinicians get 403 and the patient is absent from their lists. Consent is a separate record and never grants clinical access.

| Resource / operation | Patient | Doctor | Nurse | Physiotherapist | Administrative staff | Clinic admin |
|---|---|---|---|---|---|---|
| Own session/password | read/change/logout | same | same | same | same | same |
| Patient directory | forbidden | assigned patients only | assigned patients only | empty | basic same-clinic identity | basic same-clinic identity |
| Full demographics | own read | assigned read | assigned read | forbidden | forbidden | forbidden |
| Demographic update | own phone only | assigned, supported fields | same as doctor | forbidden | forbidden | forbidden |
| Care-team assignment | forbidden | forbidden | forbidden | forbidden | forbidden | create/end same-clinic |
| Patient deactivate | forbidden | forbidden | forbidden | forbidden | forbidden | same clinic |
| Appointments operational data | own read | assigned read/create/update/cancel | same as doctor | forbidden | same-clinic read/create/update/cancel | same-clinic read/create/update/cancel |
| Appointment reason | own read | assigned read/create/update | same as doctor | forbidden | forbidden | forbidden |
| Consent list/detail | own | assigned read | assigned read | forbidden | forbidden | forbidden |
| Consent grant/revoke | own only | forbidden | forbidden | forbidden | forbidden | forbidden |
| Medical records | own read | assigned read/create/version | same as doctor | forbidden | forbidden | forbidden |
| Medication | own read | assigned read/create/update/deactivate | same as doctor | forbidden | forbidden | forbidden |
| Clinical documents | own read/download | assigned read/create/version/download | same as doctor | forbidden | forbidden | forbidden |
| Clinical conversations | own read; reply to team-started threads | assigned start/read/reply | same as doctor | forbidden | forbidden | forbidden |
| Conversation triage | forbidden | close; reply clears escalation | change non-closed status; escalate | forbidden | forbidden | forbidden |
| Notifications | own read/mark read | own | own | own | own | own |
| Staff invitation | forbidden | forbidden | forbidden | forbidden | forbidden | create same-clinic |
| Patient invitation | forbidden | create same-clinic | create same-clinic | forbidden | forbidden | create same-clinic |
| Staff deactivate | forbidden | forbidden | forbidden | forbidden | forbidden | same-clinic, not self |
| Audit history | no API | no API | no API | no API | no API | no API |

The physiotherapist role exists but has no clinical permissions until the product assigns some; this is deliberate. No other application roles exist.
