# myVita — Phase 6 Report

Result: **PHASE 6: ENGINEERING PASS. Real-world readiness: not established.**
All scenarios pass on a local rehearsal of the production topology with synthetic data.
Nothing in this report is a legal, clinical or operational approval.

## Baseline

Commits made in this phase (all local, none pushed):

| Commit | Change |
| --- | --- |
| `8f4a3b9` | login response includes `staff_role` and `patient_id` (D-01) |
| `319aa72` | text contrast fixes (D-04) |
| `e6e10e7` | 22-scenario UAT suite with axe |
| `272f8fd` | dedicated DB pool for audit writes (D-02) |
| `84d6413` | N+1 fix on appointment list and query-count guard (D-03) |
| (docs) | `docs/pilot/*` |

## Results

| Check | Result |
| --- | --- |
| UAT (22 scenarios, Chromium, production-topology stack, HTTP) | 22 passed on the final build |
| Backend `pytest` | 179 passed |
| `ruff`, `mypy` | clean (67 source files) |
| Alembic | up, down to base, up; `alembic check`: no drift |
| `pip-audit` (runtime requirements) | no known vulnerabilities |
| Frontend `tsc -b`, `oxlint`, Vitest, build | clean; 74 tests in 17 files |
| `npm audit` | 0 vulnerabilities |
| Audit log after UAT | 26 action types; no secrets, no clinical text in metadata |
| Restart of frontend, backend, proxy, db | counts unchanged (51 users / 24 patients / 33 appointments / 24 records); login and reads work after |
| Backup | dump + sha256 + archive check OK; restore into scratch DB: identical counts; freshness check OK |

## Performance and concurrency (single host, about 24 patients and 33 appointments)

Sequential, 40 requests each: p50 10 to 23 ms, p95 at most 35 ms for the main lists and `/auth/me`.

| Probe | Before fixes | After fixes |
| --- | --- | --- |
| 200 list reads, 20 concurrent clients | 5 failures, p95 30 s (pool deadlock) | 0 failures, p50 0.64 s, p95 1.6 s |
| 25 simultaneous identical bookings | 1 created, 24 conflicts | same |
| 20 record edits with same `expected_version` | 1 success, 19 conflicts | same |
| 15 simultaneous appointment edits | all 200 (last write wins) | same, see R-03 |
| Queries for appointment list | grew by 1 per row | constant |

These are not capacity numbers for production. One uvicorn worker, one database, no network latency.

## Defects found and fixed

See `DEFECT_REGISTER.md`. Two of the four were High severity and would have hurt real users:
doctors lost role-dependent UI after login (D-01), and 20 simultaneous users could freeze the API
for 30 seconds (D-02). Both were caught only because the suite drove a real browser and a real
concurrent load against the production topology; the existing unit tests passed throughout.

## What this phase does not show

- That the system is ready for real patients. No staging or production environment exists; TLS,
  DNS, real hosting, off-site backups and alert delivery are untested.
- MFA and password recovery do not exist (Phase 2 was never implemented).
- No legal, DPO, contractual or clinical sign-off exists.
- No clinician has used the product. Axe is automated and partial. Only Chromium was used.
- CI has not run on these commits.

## Open items needing a human decision

R-03 appointment edit concurrency, R-04 login rate limit behind shared NAT, R-06 consent gating,
plus every O and L row in `PILOT_READINESS_CHECKLIST.md`.

## Phase 7 gate: BLOCKED

A controlled real pilot requires, at minimum: a real hosted environment with TLS and monitoring
alerts that reach a person, tested off-site backups, named operational ownership, signed
legal/DPO/contract documents, clinical safety sign-off and a named human go decision. None exists
and engineering cannot create them. No approvals have been assumed or recorded here.
Next engineering steps that remain possible without those: fix R-03/R-04 after a decision, push and
get CI green, and implement MFA and password recovery.
