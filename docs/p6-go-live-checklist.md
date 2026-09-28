# P6 go-live checklist

Statuses reflect repository evidence on 2026-09-28. Re-evaluate against the exact release/environment.

| Area | Check | Status | Evidence / missing input |
|---|---|---|---|
| A Code | tests, types, lint, builds, reviewed release | PASS | full suites and Docker builds |
| A Code | immutable image registry/provenance/SBOM | PARTIAL | local images only; registry/signing absent |
| B Security | auth, CSRF, P4.1 RBAC, IDOR, rate limits | PASS | automated negative suite |
| B Security | MFA and recovery | BLOCKED | provider/policy and implementation absent |
| C Database | migrations/check/rollback compatibility | PASS | disposable PostgreSQL validation |
| C Database | least-privilege production DB role | PARTIAL | topology ready; real grants/user absent |
| C Database | composite tenant constraints everywhere | PARTIAL | API isolation tested; defense-in-depth gaps documented |
| D Infrastructure | hardened Compose/private networks | PASS | rendered and simulated locally |
| D Infrastructure | real encrypted host/firewall | BLOCKED | no provider/host |
| E TLS/DNS | HTTPS proxy template/HSTS/secure cookies | PASS | configuration/templates |
| E TLS/DNS | real DNS/certificate/renewal test | BLOCKED | external infrastructure |
| F Secrets | inventory/fail-closed validation/preflight | PASS | template, validators, preflight |
| F Secrets | approved manager/rotation/custodians | BLOCKED | external organization/infrastructure |
| G Backups | automatic local/checksum/failure detection | PASS | scripts and simulation |
| G Backups | real encrypted immutable off-site restore | BLOCKED | provider credentials/evidence absent |
| H Monitoring | Prometheus/Grafana/exporters/probes | PASS | production simulation |
| I Alerting | aggregate auth/authz and operational rules | PASS | promtool rules |
| I Alerting | staffed human delivery/resolution | BLOCKED | receiver/contact absent |
| J Operations | runbooks/preflight/rollback | PASS | repository docs/scripts |
| J Operations | named owners/on-call/support exercise | BLOCKED | placeholders only |
| K Privacy/legal | technical flows/access/audit inventory | PASS | P4.1/P5/P6 documentation |
| K Privacy/legal | DPIA, basis, contracts, retention, notices | BLOCKED | human legal/controller review |
| L Clinical pilot | synthetic technical dry-run | PASS | isolated simulation |
| L Clinical pilot | real participant/data approval | BLOCKED | infrastructure and privacy gates |

