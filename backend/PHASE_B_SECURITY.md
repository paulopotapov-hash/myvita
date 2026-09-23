# Phase B backend security and data lifecycle

## Authorization matrix

The source of truth is `app/core/security.py` (`ClinicalPermission`). Tenant
scope comes from the authenticated user and object lookups filter by `clinic_id`.

| Capability | Patient | Doctor | Nurse | Administrative staff | Clinic admin |
|---|---:|---:|---:|---:|---:|
| Own appointments and clinical data | read | — | — | — | — |
| Patient directory | — | read/update | read/update | read/update | read/update |
| Appointments | own read/cancel | manage | manage | manage | manage |
| Medical records | own read | read/write | read/write | — | — |
| Medication | own read | read/write | read | — | — |
| Consent events | own read/record | read/record | read/record | — | — |
| Staff directory | active staff | active staff | active staff | active staff | manage lifecycle |
| Own notifications | read | read | read | read | read |

Denied capabilities return `403`. Tenant-mismatched identifiers return `404`
to avoid confirming another clinic's resource exists. Inactive users are
rejected and deactivation increments `token_epoch`, invalidating existing sessions.

## Clinical history and integrity

- Consent rows are immutable events. Withdrawal creates a new event with status
  `withdrawn`; it never edits the original grant.
- Every medical-record update saves the replaced value in the append-only
  `medical_record_revisions` table and increments the current version.
- Database triggers reject updates/deletes on consent events and revisions.
- Composite foreign keys bind patients and staff to the appointment or clinical
  row's `clinic_id`.
- Audit rows contain identifiers and outcomes only, never clinical content.

## Data lifecycle

- Staff: update, role change, deactivate and reactivate. History remains linked;
  staff rows are never hard-deleted.
- Patients: no hard-delete endpoint. Their clinical history is retained.
- Appointments: terminal states remain in history; cancellation does not delete.
- Medications: end or mark inactive; retain the record.
- Consent and record revisions: append-only and protected by database triggers.
- Notifications: private to the recipient; only read state is mutable.

Retention periods and lawful deletion/anonymization depend on jurisdiction and
controller policy. They must be agreed before production data is accepted.
Database restore is covered by the repository backup/restore runbook. A scoped
clinical-data export and a formal archival/retention job are not implemented in
Phase B and require compliance review before production.

All collection endpoints use `limit`/`offset`, default `50`, maximum `100`.
Appointment creation, update and cancellation create notifications in the same
transaction. Docker startup applies `alembic upgrade head` before serving traffic.
