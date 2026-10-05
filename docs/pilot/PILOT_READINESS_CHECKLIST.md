# myVita — Pilot Readiness Checklist (end of Phase 6)

Status values: DONE (evidence exists), PARTIAL, OPEN, NOT DONE (nobody has done it), N/A.
Nothing here is an approval. Rows marked "owner" need a named human decision; none has been given.

## Engineering

| # | Item | Status | Evidence / note |
| --- | --- | --- | --- |
| E1 | 22 UAT scenarios pass on final build | DONE | 22/22, final run after the last code change |
| E2 | Backend tests, lint, types | DONE | 179 tests, `ruff`, `mypy` clean |
| E3 | Migrations up/down/up, no model drift | DONE | head `f6a7b8c9d0e1`, `alembic check` clean |
| E4 | Frontend typecheck, lint, tests, build | DONE | 74 tests, 17 files; build OK |
| E5 | Dependency advisories | DONE | `pip-audit` runtime: none; `npm audit`: 0 |
| E6 | Tenant isolation, role matrix | DONE | UAT-04/07/08/09/15 plus ~170 security tests |
| E7 | Audit trail, no secrets or clinical text | DONE | 26 action types observed; only matches for sensitive words were the phrase "Token CSRF" in CSRF failure reasons |
| E8 | Restart persistence | DONE | frontend, backend, proxy, db restarted in turn: row counts unchanged, login and reads work |
| E9 | Backup, integrity check, restore | DONE (local) | dump + sha256 + `pg_restore --list` + restore to scratch DB with identical row counts. Local volume only |
| E10 | Concurrency | DONE | 25 identical bookings: 1 created, 24 conflicts; record edits with same version: 1 success, 19 conflicts |
| E11 | Load stability | PARTIAL | 200 reads at 20 concurrent, 0 errors after fix D-02. One host, small dataset. See R-05 |
| E12 | Accessibility (automated) | PARTIAL | axe A/AA clean on 14 pages. No manual or screen-reader review |
| E13 | CI green on the final commits | NOT DONE | commits are local and unpushed; CI has not run on them |
| E14 | MFA and password recovery | NOT DONE | never implemented (R-01) |
| E15 | Appointment edit concurrency control | OPEN | R-03 |
| E16 | Login rate limit vs clinics behind one NAT | OPEN | R-04 |

## Environment and operations (cannot be completed from a workstation)

| # | Item | Status |
| --- | --- | --- |
| O1 | Real staging or production host provisioned | NOT DONE |
| O2 | Domain, DNS, TLS certificate issued and renewal tested | NOT DONE |
| O3 | Off-site backup target configured and a restore from it tested | NOT DONE |
| O4 | Alert receivers (email/chat/pager) configured and a test alert received | NOT DONE |
| O5 | Named on-call and incident owner | NOT DONE (owner) |
| O6 | Secrets generated and stored in the real secret store | NOT DONE |
| O7 | Image registry and signed release process used for the pilot build | NOT DONE |

## Legal, privacy, clinical (cannot be completed by engineering)

| # | Item | Status |
| --- | --- | --- |
| L1 | DPO / legal review of `docs/privacy/*` | NOT DONE (owner) |
| L2 | Data-processing agreement with hosting provider(s) | NOT DONE (owner) |
| L3 | Pilot agreement with the clinic, scope and exit terms | NOT DONE (owner) |
| L4 | Patient information notice and consent wording approved | NOT DONE (owner) |
| L5 | Clinical safety sign-off for the intended use | NOT DONE (owner) |
| L6 | Decision on whether consent should gate clinical access (R-06) | OPEN (owner) |
| L7 | Training for pilot clinic staff; support contact published | NOT DONE |
| L8 | Pilot success and stop criteria agreed | NOT DONE (owner) |

## Gate

The controlled real pilot may start only when every O and L row is DONE, E13 to E16 are DONE or
explicitly accepted by a named owner, and a human has signed the go decision. Today that is not
the case.
