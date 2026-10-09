# Retention, deletion and backup persistence

**Software today enforces no retention period.** The only lifecycle operations are deactivation (users, patients, medications, staff), consent revocation, appointment cancellation, and invitation expiry (rows are kept). There is no delete endpoint and no scheduled purge. Do not invent legal periods: where law or clinic policy decides, the cell says so. **[DECISION: controller/legal]**

## Matrix

| Data | Current behaviour in software | Retention period | Disposal method to design | Notes |
|---|---|---|---|---|
| Patient identity and records (`patients`, `medical_records`, revisions) | Kept indefinitely; patient account deactivation only | **Controller/legal decision** (health-record legislation, clinic policy) | Archive then anonymise or delete after the legal period | Revisions must follow their record; never delete clinical history on request without legal review |
| Appointments | Kept; cancellation is a status | Controller/legal decision | Same as records | `appointments.patient_id` is `ON DELETE CASCADE` (see below) |
| Medication records | Kept; deactivation is a status | Controller/legal decision | Same as records | |
| Consent records | Kept with revocation history | Controller/legal decision (evidence period) | Keep while they evidence a processing basis | FK `RESTRICT` to patient |
| Notifications | Kept | Proposed: short (for example while unread or a fixed number of days) **[DECISION]** | Scheduled purge job once decided | Cascade-deleted with the user |
| Invitations | Kept after accept/expiry (24 h default validity) | Proposed: purge expired rows after a short period **[DECISION]** | Purge job | Contains invitee email |
| Authentication state | Stateless JWT, 30 min; revocation by `token_epoch`; nothing to retain | n/a | n/a | |
| Audit logs (`audit_logs`) | Kept indefinitely; FKs `SET NULL` on user/clinic removal | **Controller/legal decision**; security view: at least the investigation window | Partition/archive then purge with a privileged role | Do not allow application code to delete them; see immutability gap |
| Operational logs | Docker `json-file` rotation 10 MB x 5 per service; proxy and backend stdout | Effective retention = rotation; no central store | Keep short; central logging requires a new review | Contains IP and path ids |
| Metrics | Prometheus 15 days (`PROMETHEUS_RETENTION`) | 15 days | Automatic | No personal data |
| Backups, local | `BACKUP_RETENTION_DAYS` default 14 | 14 days (default) | Automatic prune script | Pruning is age-based and runs only after a successful backup in the same job, so the fresh copy exists; run standalone it would delete everything older than the limit |
| Backups, off-site | `OFFSITE_RETENTION_DAYS` default 30 | 30 days (default) | Automatic prune script | The off-site prune never removes the last remaining dump; provider-side versioning/immutability is a provider setting **[TBD]** |
| Inactive accounts | Deactivated, never removed | Controller decision | Review in the periodic access review ([ACCESS_GOVERNANCE.md](ACCESS_GOVERNANCE.md)) | |
| Support records | None exist | n/a | n/a | |

## Deletion and anonymisation analysis

Facts from the schema (foreign keys):

- `patients.user_id -> users.id` is `CASCADE`; `appointments.patient_id -> patients.id` is `CASCADE`; `notifications.user_id -> users.id` is `CASCADE`; `staff.user_id -> users.id` is `CASCADE`.
- `medical_records`, revisions, `medications`, `consents` reference patients/staff/clinics with `RESTRICT`: a hard delete of a patient or staff member who authored or owns clinical rows is **refused by the database**. That protects clinical history but also means erasure cannot be a naive `DELETE`.
- `audit_logs` references users and clinics with `SET NULL`: removing a user keeps the event but loses the actor id (the email remains in `actor_email`, which would itself need handling).
- The `CASCADE` on appointments means a hard delete of a patient with no clinical rows would silently delete their appointments. Any future deletion tool must be explicit, transactional and audited, never a raw cascade.

Recommended disposal model once policy exists (not implemented, deliberately):

1. **Retain** by default; the legal retention period governs. Erasure requests are assessed case by case ([DATA_SUBJECT_RIGHTS.md](DATA_SUBJECT_RIGHTS.md)).
2. At end of period, **anonymise in place**: replace identity fields (`full_name`, `email`, `phone`, `birth_date`, `national_health_number`) with irreversible placeholders, keep clinical rows only if a legal need remains, otherwise delete rows in dependency order inside one audited transaction.
3. Audit rows: keep the event, remove or generalise `actor_email`, `ip_address`, `user_agent` after the audit retention period.
4. No mechanism is built until the controller approves the periods, to avoid destroying data that the law requires to be kept.

## Backups and deletion cycles

Deleted or anonymised data persists in backups until those backups expire (14 days local, 30 days off-site by default). The privacy notice and any erasure response must say so. A restored backup would re-introduce data that was erased after the backup; the restore runbook must re-apply pending erasures before the restored system is used. Temporary restore databases must be isolated, protected and deleted after validation (the drill did this).

## Configurable today

`BACKUP_RETENTION_DAYS`, `OFFSITE_RETENTION_DAYS`, `INVITATION_EXPIRE_HOURS`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `PROMETHEUS_RETENTION`, Docker log rotation (compose). Everything else is **pending controller/legal decision**.
