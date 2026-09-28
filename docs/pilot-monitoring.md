# Pilot monitoring and alerting

The monitoring overlay provides Prometheus, Grafana, Alertmanager, PostgreSQL/node/container exporters, blackbox probes and an authenticated metrics proxy. Metrics contain bounded operational labels only; users, clinics, patient IDs, request bodies, cookies, tokens and clinical content are forbidden.

## Required checks

- `/health`, `/ready`, proxy and frontend health;
- PostgreSQL reachability/connections;
- HTTP request/status/latency trends without sensitive labels;
- host CPU, memory and disk; container restarts/resources;
- local/off-site backup success and freshness;
- Prometheus configuration/rules and all scrape targets;
- Grafana login/provisioned dashboard;
- controlled alert firing, human receipt and resolved notification.

Critical incidents include proxy/backend/database unavailability, backend not ready, missing/failed/stale backup and critical disk pressure. Warning conditions include sustained 5xx, resource pressure, high connections and repeated restarts. The on-call owner must acknowledge critical alerts within an externally approved target; no response target is invented here.

Current Alertmanager intentionally uses `pending-human-destination` with no integration. Therefore rules/topology are locally testable, but human alert delivery is **CONFIGURATION REQUIRED / BLOCKED BY EXTERNAL DESTINATION**. Before pilot, name primary/secondary recipients, response time, escalation path and maintenance-window procedure, then perform a controlled end-to-end delivery test.
