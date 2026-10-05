# Personal-data inventory

Derived from the SQLAlchemy models (`backend/app/models`), API schemas and code paths at commit `5d49174`. "Storage" is PostgreSQL unless stated. Retention is **not enforced by software** anywhere except where noted; see [RETENTION_MATRIX.md](RETENTION_MATRIX.md). Protection column states only what is evidenced in the repository.

Legend: **H** = health data / special category (GDPR Art. 4(15), Art. 9). **P** = personal data. **S** = security/credential data.

## Inventory

| Category | Fields (table.column) | Data subject | Purpose | Source | Recipients | Class | Protection (evidenced) |
|---|---|---|---|---|---|---|---|
| User identity | `users.email`, `full_name`, `role`, `clinic_id`, `is_active` | Staff, clinic admins, patients | Account, access control | User / clinic admin | Same-clinic staff per RBAC (names via lists); clinic admin | P | Tenant-scoped queries; unique email |
| Authentication | `users.hashed_password` (Argon2id), `token_epoch`; session JWT and CSRF cookies (not stored server-side) | All users | Authenticate, revoke sessions | User | Nobody (never returned by API) | S | Argon2id; HttpOnly session cookie; HMAC-bound CSRF; epoch revocation |
| Invitation | `invitations.email`, `full_name`, `role`, `token_hash` (SHA-256), `status`, `expires_at` | Invited staff/patients | Onboarding | Clinic admin / staff | Inviter (token shown once at creation) | P | Token stored as digest, expiry |
| Staff profile | `staff.staff_role`, `specialty`, `license_number`, `clinic_id` | Staff | Role-based access, clinical attribution | Clinic admin | Same-clinic users see role/specialty; `license_number` not in `StaffPublic` | P | RBAC; field omitted from API |
| Patient identity | `patients.birth_date`, `phone`, `national_health_number`, `user_id`, `clinic_id` | Patients | Identify patient for care | Patient / clinical staff | Patient (own), doctor/nurse (same clinic) | P; **H** because it identifies a person as a patient and `national_health_number` is a health identifier (Recital 35) | Tenant + role scoping, 404 non-disclosure |
| Appointment | `appointments.scheduled_at`, `duration_minutes`, `status`, `reason`, `notes`, `patient_id`, `staff_id` | Patients, staff | Scheduling | Staff | Patient (own), same-clinic staff; `reason` hidden from administrative roles | **H** (`reason`, `notes`, existence of a visit) | Role-scoped serialisation; audit on view/change |
| Medical record | `medical_records.title`, `content`, `version`, author; `medical_record_revisions` (full prior text) | Patients | Clinical documentation | Doctor/nurse | Patient (own read), same-clinic doctor/nurse | **H** | RBAC, optimistic versioning, revisions retained, audited access |
| Medication | `medications.name`, `dosage`, `route`, `frequency`, `instructions`, `status`, dates | Patients | Medication management | Doctor/nurse | Patient (own read), same-clinic doctor/nurse | **H** | RBAC, audit |
| Consent | `consents.consent_type`, `purpose`, `policy_version`, `policy_text`, status, timestamps, `recorded_by_user_id` | Patients | Evidence of choices made in-app | Patient | Patient (own), same-clinic doctor/nurse | P (may imply **H**) | Patient-only grant/revoke, history kept |
| Notification | `notifications.title`, `message`, `is_read`, `read_at`, `user_id` | Users | In-app notices (currently appointment events) | System | Owner only | P (may imply **H**) | Owner-scoped queries |
| Audit event | `audit_logs.actor_email`, `actor_user_id`, `clinic_id`, `action`, `resource_type`, `resource_id`, `result`, `ip_address`, `user_agent`, `metadata` (JSONB) | Users incl. failed-login subjects | Accountability, security investigation | System | **No API role can read it**; DB operators only | P; metadata is identifiers only by rule; resource ids can indirectly reveal care relationships | Written in an independent transaction; secrets/clinical content excluded (tested). **Not DB-immutable** (see gaps) |
| Security event | Audit rows with `login_failure`, `csrf_failure`, `permission_denied`, `rate_limited` (attempted email, IP, user agent) | Anyone who attempts login | Abuse detection | System | DB operators | P | As above |
| Technical log | stdout JSON/text from backend, nginx proxy, Docker: timestamp, request id, method, **path without query string**, status, duration, client IP (proxy), `user_id` on login/logout | Users | Operations | System | Operators | P (IP, user id) | Query strings and attempted emails are not logged (fixed in `5d49174`, tested); log rotation 10 MB x 5 per container |
| IP addresses | `audit_logs.ip_address`; proxy access log `client=` | Users | Security | Network | Operators | P (Recital 30) | Only trusted-proxy headers honoured |
| Backup copy | Whole database dump (everything above) | All | Recovery | System | Operators; S3-compatible destination if configured | **H** | Checksum, `pg_restore --list`; SSE option; encryption at rest of the destination not evidenced |
| Support data | None stored. No ticketing, no support role, no impersonation | n/a | n/a | n/a | n/a | n/a | n/a |
| Browser storage | None: no `localStorage`/`sessionStorage`; two cookies only (`myvita_session` HttpOnly, `myvita_csrf`) | Users | Session | Browser | n/a | S | Cookie flags verified by tests |

## Explicit special-category (health) data

Appointment `reason`/`notes`, medical records and their revisions, medications, patient identity linked to a clinic, `national_health_number`, consent text where it concerns treatment, notification text where it names a visit, and every backup containing them.

## Gaps and findings from this inventory

1. **Audit log is append-only by convention, not by database control.** No trigger or privilege separation prevents `UPDATE`/`DELETE` by the application database role. Recommendation: separate DB roles (app role without UPDATE/DELETE on `audit_logs`, a distinct retention role) once the retention policy is decided. Needs a decision because the `ON DELETE SET NULL` foreign keys legitimately update rows when a user or clinic is removed. **[DECISION: security/privacy]**.
2. **`actor_email` is stored in plaintext in the audit log**, including for unknown addresses typed at login. It is needed for investigation; access is DB-only. Decide retention and access. **[DECISION: privacy]**.
3. **`policy_text` snapshot** copies consent wording into each consent row: intentional evidence, but storage grows per consent.
4. **No automated retention/deletion exists.** Deactivation is the only lifecycle operation.

## Minimisation classification

| Item | Class | Rationale |
|---|---|---|
| `users.email`, `full_name` | retain | Needed for identity and login |
| `patients.national_health_number` | needs business decision | Collection is optional; confirm legal need and national identifier rules (Art. 87) before the pilot |
| `patients.birth_date`, `phone` | retain | Needed for identification and contact; revisit if no outbound contact exists (today none, because there is no email/SMS) |
| `staff.license_number` | retain, restricted | Already excluded from API responses |
| `appointments.notes` | needs business decision | Free text can hold arbitrary health detail; define what clinics should put there |
| `medical_record_revisions` full text | retain | Required for clinical traceability; retention follows the record |
| `consents.policy_text` | retain | Evidence of what was accepted |
| `audit_logs.user_agent` | restrict | Limited investigative value; consider hashing or shorter retention |
| `audit_logs.actor_email` | restrict | See gap 2 |
| `notifications.message` | retain (keep generic) | Verified: current texts are fixed generic Portuguese sentences ("Foi criada uma consulta na sua agenda.") with no clinical detail; keep it that way |
| Backups | restrict | Same data as production; see retention matrix |
| `GET /api/v1/clinics` public directory | restrict (done) | Now empty for anonymous callers and limited to the caller's own clinic unless public patient registration is enabled |

## Fixes made in this phase (commit `5d49174`)

- Failed-login application log no longer contains the attempted email.
- uvicorn access log (full request line including query strings such as patient search terms) is disabled in the backend image and production compose; the application's own request log records the path only.
- The public clinic directory no longer lists all clinics when public registration is disabled.
- Tests: `backend/tests/test_privacy_controls.py`.
