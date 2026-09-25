# Security hardening review

This document records the endpoint-level authorization inventory and the
deployment assumptions reviewed before the first controlled clinic rollout.
The backend remains the security boundary; frontend route guards are only a
user-experience feature.

## Endpoint authorization inventory

All authenticated unsafe methods also require a valid, session-bound CSRF
token and an allowed `Origin` when that header is present. Object lookups
return 404 when an identifier belongs to another clinic or another patient,
avoiding existence disclosure.

| Endpoint | Method | Authentication / role | Tenant and object scope |
| --- | --- | --- | --- |
| `/health`, `/ready` | GET | Public | No clinical data |
| `/metrics` | GET | Internal metrics token; public proxy blocks it | Operational counters only |
| `/api/v1/auth/login` | POST | Public; 10/min/IP | Generic credential failure; sets secure cookies |
| `/api/v1/auth/logout` | POST | Any authenticated user | Current user; increments token epoch |
| `/api/v1/auth/me` | GET | Any authenticated user | Current user only |
| `/api/v1/clinics` | POST | Public; 5/min/IP | Creates one clinic/admin atomically |
| `/api/v1/clinics` | GET | Public | Deliberately minimal `id` + `name` directory |
| `/api/v1/patients/register` | POST | Public; 5/min/IP | Joins an existing clinic; cannot set role |
| `/api/v1/patients` | GET | Staff or clinic admin | Session clinic only; paginated |
| `/api/v1/patients/{id}` | GET/PATCH | Authenticated | Session clinic; patients restricted to self |
| `/api/v1/staff` | POST | Clinic admin; 20/min/IP | Session clinic; cannot set clinic ownership |
| `/api/v1/staff` | GET | Authenticated | Session clinic directory only |
| `/api/v1/appointments` | POST | Staff or clinic admin | Patient and staff must belong to session clinic |
| `/api/v1/appointments` | GET | Authenticated | Patients see self; staff/admin see session clinic |
| `/api/v1/appointments/{id}` | GET | Authenticated | Session clinic; patients restricted to self |
| `/api/v1/appointments/{id}` | PATCH | Staff or clinic admin | Session clinic; substituted IDs revalidated |
| `/api/v1/appointments/{id}/cancel` | POST | Staff or clinic admin | Session clinic |
| `/api/v1/patients/{id}/consents` | GET/POST | Authenticated | Session clinic; patients restricted to self |
| `/api/v1/consents/{id}` | GET | Authenticated | Session clinic; patients restricted to self |
| `/api/v1/consents/{id}/revoke` | POST | Authenticated | Session clinic; patients restricted to self |
| `/api/v1/patients/{id}/medical-records` | GET | Patient self, doctor or nurse | Session clinic and patient ownership |
| `/api/v1/patients/{id}/medical-records` | POST | Doctor or nurse | Session clinic; patient ID revalidated |
| `/api/v1/medical-records/{id}` | GET | Patient self, doctor or nurse | Session clinic and patient ownership |
| `/api/v1/medical-records/{id}` | PATCH | Doctor or nurse | Session clinic and patient ownership |
| `/api/v1/medical-records/{id}/revisions` | GET | Patient self, doctor or nurse | Parent record is authorized first |
| `/api/v1/patients/{id}/medications` | GET | Patient self, doctor or nurse | Session clinic and patient ownership |
| `/api/v1/patients/{id}/medications` | POST | Doctor or nurse | Session clinic; patient ID revalidated |
| `/api/v1/medications/{id}` | GET | Patient self, doctor or nurse | Session clinic and patient ownership |
| `/api/v1/medications/{id}` | PATCH | Doctor or nurse | Session clinic and patient ownership |
| `/api/v1/notifications` | GET | Authenticated | Current user only; paginated |
| `/api/v1/notifications/{id}/read` | POST | Authenticated | Current user only |

Audit logs have no read API, so no tenant can query them through the product.
They are an operator-only database concern at present.

## Reviewed controls

- JWT algorithms are allowlisted, the secret is at least 32 characters, and
  token epochs revoke copied or concurrent session cookies after logout.
- Passwords use Argon2id; unknown accounts take the same hash-verification
  path as incorrect passwords; responses do not enumerate login accounts.
- Session cookies are HttpOnly, Secure in production, SameSite=Lax and scoped
  to `/`. The separate CSRF cookie is intentionally readable by the frontend.
- Request schemas reject extra fields and bound stored strings. The backend
  and reverse proxy reject request bodies over 1 MiB.
- SQLAlchemy expressions parameterize every user-influenced query. The only
  application `text()` call is the constant readiness query `SELECT 1`.
- API responses use `Cache-Control: no-store`; production proxy responses set
  CSP, HSTS (TLS configuration), frame, MIME, referrer and permissions policy.
- Request logs omit bodies, query strings and headers. Audit fields controlled
  by clients are bounded; audit metadata must contain identifiers only.
- The frontend stores no session token in Web Storage, renders no raw HTML,
  and validates post-login navigation against the internal `/app` namespace.
- File upload and download infrastructure does not exist, so upload MIME,
  filename, path traversal and cross-tenant download surfaces are absent.
- Production app containers are non-root, drop Linux capabilities and enable
  `no-new-privileges`; the backend filesystem is read-only. PostgreSQL,
  Grafana, Prometheus and exporters have no public port in production.

## Accepted and external risks

- Rate-limit counters are process-local. A multi-replica deployment must use
  shared Redis-backed limits before adding the second backend replica.
- The documented Starlette advisories remain accepted only because the
  affected static-file/upload surfaces are absent; see
  `backend/SECURITY-EXCEPTIONS.md` for exact advisory IDs and re-check rules.
- cAdvisor requires documented host/container visibility for monitoring; it
  is internal-only and is the sole intentionally privileged monitoring case.
- Real TLS still requires the deployment domain and certificate material.
  Off-site backup credentials and a human Alertmanager destination are also
  external deployment configuration, not repository secrets.
