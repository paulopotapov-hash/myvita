# myVita — Phase 6 Defect and Risk Register

Severity: High = wrong behaviour for real users or outage under normal load; Medium = degraded
behaviour or compliance gap with a workaround; Low = cosmetic.

## Defects found by Phase 6 and fixed

| ID | Severity | Found by | Defect | Fix (commit) | Regression guard |
| --- | --- | --- | --- | --- | --- |
| D-01 | High | UAT-10 (browser) | `POST /auth/login` returned `staff_role: null` and `patient_id: null`; the SPA caches that body as the session, so role-dependent UI (for example the appointment reason field for doctors) was missing until a full page reload. `/auth/me` returned the right values | `8f4a3b9` login returns the same payload as `/auth/me` | `test_login_response_matches_auth_me_so_the_spa_has_staff_role_and_patient_id` (fails without the fix, verified) |
| D-02 | High | Concurrency probe (20 simultaneous clients) | Audit rows are written in their own transaction while the request still holds a DB connection, and both came from one pool (5 + 10). With 20 concurrent authenticated reads every connection was held by a request waiting for its audit connection: stalls of 30 s (pool timeout) and failed requests (5 of 200, p95 30 s) | `272f8fd` audit writes use a dedicated pool (3 + 7) | `test_audit_write_does_not_need_a_connection_from_the_request_pool` (30 s stall without the fix, verified) |
| D-03 | Medium | N+1 guard | `GET /appointments` ran one extra permission query per returned row (5 queries for 2 rows, 17 for 14) | `84d6413` computed once per request | `tests/test_query_counts.py` covers 6 list endpoints; query count must not grow with row count |
| D-04 | Medium | UAT-22 (axe) | Colour contrast below WCAG AA on appointment reasons (`text-slate-400`, 2.63:1) and on read notifications (`opacity-70`, 2.7 to 3.6:1) on 3 pages | `319aa72` darker text, no opacity dimming | UAT-22 |

Test-harness defects (not product defects) fixed along the way: stray click on a toggle that did
not exist, stale same-named users from earlier runs, a tab that must be opened before asserting
record titles, an ambiguous alert locator, login throttle budget.

## Open limitations and risks (not fixed)

| ID | Severity | Item | Notes / decision needed |
| --- | --- | --- | --- |
| R-01 | High (for a real pilot) | No MFA and no self-service password recovery | Phase 2 was never implemented. Account recovery is manual by a clinic admin |
| R-02 | High | No staging or production environment; all evidence is a local rehearsal over HTTP | TLS, DNS, real hosting, host hardening, off-site backups and alert receivers are untested |
| R-03 | Medium | Appointment edits have no optimistic concurrency: 15 concurrent `PATCH` calls all returned 200 (last write wins) | Medical records do enforce `expected_version` (1 success, 19 conflicts of 20). Decide whether appointments need the same |
| R-04 | Medium | Login rate limit is 10 per minute per client IP | A clinic behind one NAT address, with several staff signing in at shift start, can lock itself out for a minute. Needs a decision before go-live |
| R-05 | Medium | Capacity: one uvicorn worker. 20 concurrent clients each reading 100-row lists: p50 0.64 s, p95 1.6 s, 0 errors | Fine for a very small pilot; not a capacity statement for production load. Dataset was about 24 patients and 33 appointments |
| R-06 | Medium | Consent is recorded but does not gate clinical access (UAT-14) | Product/legal decision |
| R-07 | Medium | Legal and DPO approvals, contracts, data-processing agreements, privacy notices | Engineering artefacts exist in `docs/privacy/`; nobody has signed anything |
| R-08 | Low | Browsers other than Chromium, real devices, screen readers not tested | Axe only covers part of WCAG |
| R-09 | Low | Local commits have no CI run (not pushed) | CI will run on push; results unknown |
| R-10 | Low | No clinician has used the product | Usability and clinical workflow fit unvalidated |
