# Rate limiting

How myVita limits requests, and what must change before running more than one backend
process. Code: `backend/app/core/rate_limit.py`. Tests: `backend/tests/test_rate_limits.py`
and `backend/tests/test_phase1_security.py`.

## Who is counted

| Requests | Counted per | Why |
|---|---|---|
| Authenticated (a valid session cookie) | **user** | A clinic's staff share one public IP. Per IP, one busy colleague would block the others, and one abusive account could hide among them. |
| Public: login, MFA verification, registration, clinic onboarding, password reset, public invitation links | client IP | There is no account yet. |
| Failed logins | **account** (e-mail fingerprint) and IP | Stops a slow, distributed guess at one account. The address itself is never stored, only its keyed fingerprint. |

The user comes from the signed session cookie: a forged cookie cannot be made without the
server key, and falls back to the IP. The client IP is read through `get_client_ip`, which
trusts `X-Forwarded-For` only from `TRUSTED_PROXIES`.

## Limits

| What | Limit |
|---|---|
| Login (per IP) | 10 per minute |
| Failed logins (per account) | 5 in 15 minutes. After that, even the right password gets 429 until the window passes. A successful login starts the count again. |
| Registration, clinic onboarding (per IP) | 5 per minute |
| Password reset (per IP) | 5 per minute |
| Public invitation links (per IP) | 10 per minute |
| Clinical modules, per user and module: appointments, appointment requests, clinical history, clinical results, consents, documents, medical records, medications, messages, patients, scheduling, staff, users, waiting list | reads 300/minute, writes 60/minute |
| Document upload (per user) | 10 per minute and 100 per hour |
| Notifications (per user) | reads 600/minute, writes 120/minute (the badges poll) |
| Revealing full NIF / NISS / Nº de utente (per user) | 10 per hour |
| Other authenticated writes with their own decorator (password change and MFA settings, staff, users, messages, invitations, appointment requests, waiting list) | 20 per minute, per user (on top of the module limit) |

A refused request gets `429` with `Retry-After: 60` and a Portuguese message, and is
audited (`rate_limited`, with the path and a reason code; never the body).

## More than one backend process: move the counters to Redis

The counters live **in the memory of the backend process** (`RATE_LIMIT_STORAGE_URI=memory://`).
That is correct for today's deployment: one container, one `uvicorn` process, no `--workers`.

With more than one process (uvicorn or gunicorn workers, or several backend replicas),
each process keeps its own counters. Every limit would then be multiplied by the number of
processes, and the per-account login lock would no longer be reliable. Before running a
second process:

1. Add a Redis service, reachable only on the internal `data` network, with a password.
2. Add the `redis` package to `backend/requirements-runtime.txt` (the `limits` library uses it).
3. Set `RATE_LIMIT_STORAGE_URI=redis://:<password>@redis:6379/0` for the backend **and** the
   `jobs` service (`docker-compose.prod.yml`). Inject it from the secret store.
4. Run `tests/test_rate_limits.py` against that Redis, and check that two processes share one
   count: exhaust a limit through one and see the other refuse.

The deploy checklist (`docs/deploy-checklist.md`) refuses a multi-process deploy until this is done.
