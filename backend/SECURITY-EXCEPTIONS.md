# Dependency scan exceptions

Every ignored vulnerability here is enforced by `--ignore-vuln` in
`.github/workflows/ci.yml`. CI fails on anything NOT listed here — this
file is what makes an exception a documented decision instead of a
silently-passing check.

## starlette 0.41.3 — PYSEC-2026-161, -248, -249, -1941, -1942, -2280, -2281

**Why not fixed:** all fix versions are `>=0.47.2` (several of them are on
the `1.x` line). `fastapi==0.115.6` pins `starlette<0.42.0,>=0.40.0` — there
is no combination of a compatible starlette fix and our current FastAPI
version. Getting a fixed starlette means a FastAPI major-version upgrade,
which is a framework-level change explicitly out of scope for a hardening
pass (risk of breaking every route/dependency in the app, needs its own
dedicated, carefully tested upgrade — see "NÃO trocar frameworks" in the
brief this phase worked from).

**Why the risk is acceptable in the meantime** — checked against this
codebase specifically, not the CVEs' abstract descriptions:

- None of the CVEs' affected surfaces are used anywhere in `app/`:
  `StaticFiles`, `FileResponse`, `starlette.routing.HTTPEndpoint`, or
  `request.form()` for file/multipart uploads. Confirmed by:
  `grep -rn "StaticFiles\|FileResponse\|HTTPEndpoint\|\.form(\|UploadFile" app/`
  → no matches.
- No code in this app makes a security decision based on `request.url.*`
  (host header reconstruction) — routing goes through FastAPI's router,
  authorization goes through `require_roles`/CSRF dependencies, not string
  comparisons on the URL.
- The app doesn't serve static files or uploaded files at all.

**Re-check when:** upgrading FastAPI (do it as its own dedicated, tested
change — full regression suite, not bundled with anything else), or if a
future CVE in this list turns out to affect a surface the app actually
uses (re-run the grep above against the new CVE's description first).

## Deferred, not ignored: pytest major-version risk

Not a pip-audit finding, but worth recording next to this: pytest's own
past CVE (predictable temp-dir naming on shared multi-user Unix systems) is
irrelevant to this project's CI/Docker execution environment, but the
9.0.3 upgrade was still done and fully tested here (56/56 passing) rather
than skipped, since — unlike the starlette case above — it turned out to
have no compatibility issues once actually tried.
