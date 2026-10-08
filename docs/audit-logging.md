# Audit logging

One centralized, tenant-aware audit trail backs every module in myVita. This
document is the reference for how it works, what is (and is not) recorded, and
the rules every future audit call must follow.

## Architecture

```
routers / security dependencies ──► audit_request(request, …)
service layer (no Request)      ──► record_audit_event(…)
                                          │  sanitize_metadata (allowlist)
                                          │  bounded fields, UTC timestamp
                                          ▼
                              AuditSessionLocal (dedicated pool)
                                          ▼
                                 PostgreSQL  audit_logs
                                          ▲
                 GET /api/v1/audit-logs (clinic_admin, clinic-scoped)
```

* `app/core/audit.py` is the **only** writer. Nothing constructs `AuditLog`
  rows directly.
* `audit_request()` derives actor, clinic, IP, user agent and request ID from
  the request + authenticated user. Routers pass only `action`, `resource_type`,
  `resource_id` and identifier-only `metadata`.
* `record_audit_event()` is the primitive for service code without a `Request`
  (e.g. login success/failure). It still gets the request ID from the
  `ContextVar` bound by the observability middleware.
* The abstraction is a single function boundary, so exporting to an external
  SIEM later means adding a second sink inside `record_audit_event`, not
  touching modules.

## Schema (`audit_logs`)

| column | notes |
| --- | --- |
| `id` | UUID PK |
| `timestamp` | `timestamptz`, server `now()` (UTC) |
| `clinic_id` | FK `clinics` **ON DELETE SET NULL**, nullable (system-level events) |
| `actor_user_id` | FK `users` **ON DELETE SET NULL**, nullable (anonymous failures) |
| `actor_email` | kept so identity survives account deletion |
| `action` | PostgreSQL enum `audit_action` (controlled vocabulary) |
| `resource_type` / `resource_id` | e.g. `document` / UUID |
| `result` | `success` / `failure` / `denied` |
| `ip_address`, `user_agent` | bounded, see IP rules below |
| `request_id` | correlates with `X-Request-ID` and the request log line |
| `metadata` | JSONB, allowlisted identifiers only |

Indexes: `clinic_id`, `actor_user_id`, `timestamp`, `action`,
`(resource_type, resource_id)`, `(clinic_id, timestamp)` (the admin listing).

FK behaviour is deliberately `SET NULL`, never cascade: deleting a user or
clinic must not erase the trail. Migrations: `76dad50950ee` (table), enum
additions in feature migrations, `c2d3e4f5a6b7` (request_id, composite index,
`audit_log_viewed`).

## Actions

Security / administrative: `login_success`, `login_failure`, `logout`,
`password_change`, `invitation_created`, `invitation_accepted`, `user_created`,
`user_disabled`, `patient_created`, `patient_updated`, `patient_deleted`,
`staff_created`, `staff_updated`, `appointment_created`, `appointment_updated`,
`appointment_cancelled`, `clinic_created`, `consent_granted`, `consent_revoked`,
`medical_record_created`, `medical_record_updated`, `medication_created`,
`medication_updated`, `medication_deactivated`, `notification_read`,
`conversation_created`, `message_sent`, `message_read`, `permission_denied`,
`csrf_failure`, `rate_limited`, `audit_log_viewed`.

Sensitive-read access: `staff_viewed_patient`, `staff_viewed_appointment`,
`patient_viewed_own_record`, `consent_viewed`, `medical_record_viewed`,
`medication_viewed`, `conversation_viewed`, `document_downloaded`
(+ `document_uploaded`, `document_deleted`).

Naming convention: `<resource>_<past-tense verb>`. Add a value by extending the
enum **and** `ALTER TYPE audit_action ADD VALUE IF NOT EXISTS` in a migration.
Enum labels are never removed on downgrade.

## What is audited

| module | events |
| --- | --- |
| auth | login success/failure (actor email kept for failures), logout, password change |
| clinics | onboarding |
| patients | register, directory listing, detail view, update, deactivate |
| staff / invitations | create, (de)activate, role change, invitation created/accepted |
| appointments | create, update (incl. reassignment, metadata `patient_id`, `status`), cancel, list/detail views |
| medical records | create, update, list/detail/revisions views |
| medications | create, update, deactivate, list/detail views, denied access |
| consents | grant, revoke, list/detail views |
| notifications | mark read, mark-all-read (`operation=read_all`, `updated_count`) |
| messages | conversation created/viewed, message sent, mark read |
| documents | upload, download, delete (metadata `patient_id`) |
| security | permission denied, CSRF failure, rate limited |
| audit | reading the audit log (`audit_log_viewed`, with the filters used) |

Deliberately **not** audited: `GET /auth/me`, notification/conversation/staff
directory listings, unread counts, `/health`, `/metrics` — high-volume,
non-sensitive reads with no investigative value. Sensitive *list* views record
one row per request (`*_list` resource type, `count` metadata), not one per
item.

## Privacy rules

`sanitize_metadata()` enforces, at write time:

* **Allowlisted keys only** (`ALLOWED_METADATA_KEYS`): `count`, `updated_count`,
  `operation`, `path`, `reason`, `required_roles`, `patient_id`,
  `conversation_id`, `appointment_id`, `staff_role`, `active`, `status`,
  `filters`.
* Any key matching `password|secret|token|authorization|cookie|csrf|session|
  api_key|body|content|message|record|hash` is dropped even if allowlisted.
* Values: scalars, UUIDs (stringified), enums (`.value`), flat lists (≤25),
  one-level dicts of scalars. Strings are truncated to 200 chars. Anything else
  is dropped with a warning.
* Never stored: message bodies, document bytes or filenames, record contents,
  passwords, JWTs, cookies, CSRF tokens, request bodies.

The admin API additionally omits `user_agent` from responses.

## Transaction semantics

Audit rows are written in their **own** transaction on a dedicated connection
pool (`audit_engine`), independent of the request session. Reasons:

1. `FAILURE`/`DENIED` events (bad login, CSRF, permission denied, rate limit)
   happen on requests that fail — a shared transaction would roll them away.
2. The request pool can be saturated without starving audit writes.

To keep SUCCESS rows truthful, routers call `audit_request()` **after** the
service layer has committed. A business transaction that raises never reaches
the audit call, so no row claims success (tested in
`test_rolled_back_operation_does_not_claim_success`). An audit write failure is
logged and never raised.

## Administrator access

`GET /api/v1/audit-logs` — `clinic_admin` only (`require_roles`). The clinic is
always the caller's own; there is no clinic parameter, and `actor_user_id` /
`resource_id` filters cannot cross tenants (they are ANDed with `clinic_id`).

Filters: `actor_user_id` (UUID), `action` (enum), `resource_type`
(`^[a-z_]+$`), `resource_id` (UUID), `date_from`, `date_to`. Pagination `page`
≥1, `page_size` 1–100, newest first, total in `X-Total-Count`. Each read is
itself recorded as `audit_log_viewed`.

Each entry's `actor` is `{user_id, email, name}`. `email` is the historical
value stored on the row; `name` is the actor's *current* `full_name`, resolved
in one query per page and scoped to the administrator's clinic. It is `null`
for deleted users and anonymous events, so history never depends on a live
user row.

Patients, doctors, nurses and administrative staff receive 403. Frontend:
`/app/auditoria` (admin nav only). There is no export surface.

## IP address and request metadata

`get_client_ip()` returns the socket peer unless the peer is in
`TRUSTED_PROXIES` (empty by default → fail closed), in which case the first
`X-Forwarded-For` hop is used. Arbitrary clients cannot spoof their IP. The
request ID is client-suppliable only when it matches `^[A-Za-z0-9_-]{8,64}$`;
otherwise the server mints one.

## Retention

No automatic deletion exists and none should be added without an explicit,
documented organisational/legal policy. The schema is archival-friendly
(append-only, time-indexed, `SET NULL` FKs). Partitioning or export by
`timestamp` is the expected future path.

## SIEM export (optional)

myVita does **not** require any SIEM. The audit trail is complete and
queryable in PostgreSQL on its own. For deployments that run a security
monitoring platform, `app/core/audit_export.py` provides a provider-neutral
exporter — anything that accepts an HTTPS `POST` of a JSON array works
(Splunk HEC, Elastic ingest, Sentinel data collector, a Vector/Fluent Bit
HTTP source, a custom collector…). No vendor SDK is bundled.

### Enabling

```
SIEM_ENABLED=true
SIEM_ENDPOINT=https://siem.example.org/ingest/myvita   # HTTPS required in production
SIEM_API_KEY=<secret>                                   # optional; sent as `Authorization: Bearer`
SIEM_TIMEOUT_SECONDS=5
SIEM_BATCH_SIZE=100
SIEM_CURSOR_FILE=/var/lib/myvita/siem-cursor.json
```

Set these through the environment/secret store, never in files committed to
Git. The key is a `SecretStr`: it is not printed by settings `repr`, not
logged, and never appears in a request body. With `SIEM_ENABLED=false`
(the default) the application opens **no** connection to the endpoint.

### Running the export

```
docker compose exec backend python scripts/export_audit_siem.py          # one run
docker compose exec backend python scripts/export_audit_siem.py --dry-run
```

Schedule it (cron, systemd timer, compose one-shot) every few minutes. It is
**out-of-band by design**: no clinical request ever waits on the SIEM, so a
slow, down, misconfigured or rejecting SIEM cannot affect patients or staff.
There is no worker/queue infrastructure in this project and none is
introduced for this; the trade-off is that delivery latency equals the
schedule interval.

Exit codes: `0` all available events delivered · `1` the sink rejected a batch
(run resumes next time) · `2` SIEM disabled.

### Event format (JSON array per batch, `schema_version: 1`)

```json
{
  "schema_version": 1,
  "id": "8d8e…",                 "timestamp": "2026-10-08T12:00:00.123456+00:00",
  "clinic_id": "…",              "actor_user_id": "…",      "actor_email": "…",
  "action": "document_downloaded", "resource_type": "document", "resource_id": "…",
  "result": "success",           "ip_address": "203.0.113.9", "request_id": "3f2a…",
  "metadata": {"patient_id": "…"}
}
```

Exactly these fields, nothing else. `metadata` is the write-time allowlisted
object described under *Privacy rules*; the exporter adds no fields and reads
no other tables, so message bodies, document bytes/filenames, record contents,
passwords, tokens and cookies cannot appear. `user_agent` is deliberately not
exported.

### Delivery semantics

**At-least-once.** Events are streamed in `(timestamp, id)` order after a
cursor stored in `SIEM_CURSOR_FILE`. The cursor advances only after the sink
returned 2xx for a batch. A timeout, 4xx, 5xx or crash leaves the cursor at
the last accepted event, so the next run re-sends that batch. Downstream
systems should deduplicate on `id` (a globally unique UUID); `request_id` and
`timestamp` are included as secondary keys. Exactly-once is **not** claimed.
Runs are bounded by `SIEM_BATCH_SIZE × --max-batches` (default 100 × 50).

### Connecting a real SIEM later

Point `SIEM_ENDPOINT` at the platform's HTTP ingest URL and put its token in
`SIEM_API_KEY`. If a platform needs a different envelope or auth header,
implement the `AuditSink` protocol (one `send(events)` method) next to
`HttpJsonAuditSink` — the exporter, cursor handling and privacy surface stay
unchanged.

## Adding an audit call

```python
from app.core.audit import audit_request
audit_request(request, action=AuditAction.X, actor=user, resource_type="thing", resource_id=thing.id,
              metadata={"patient_id": thing.patient_id})
```

Call it after the commit, pass identifiers only, and add a representative
assertion to `tests/test_audit_infrastructure.py`.
