# P7-A go-live checklist

Every PASS requires evidence from the exact release and target environment.

| Area | Gate | Status |
|---|---|---|
| Code | CI, tests, audits and reviewed immutable commit | PASS locally / environment evidence pending |
| Host | qualified capacity, encryption, patching, NTP, access | BLOCKED — real host required |
| Firewall | 443 public; 80 redirect optional; DB/admin private | BLOCKED — real firewall required |
| Registry | SHA tags/digests, private pull, retention/scanning | PARTIAL — workflow/overlay ready |
| DNS | approved hostname and authoritative records | BLOCKED — real domain required |
| TLS | trusted certificate, redirect, renewal and external test | BLOCKED — real TLS certificate required |
| Secrets | approved manager, least privilege, rotation owners | BLOCKED — manager and custodians required |
| PostgreSQL | private encrypted storage, role/grants, migrations | PARTIAL — topology ready; instance absent |
| Backup | encrypted immutable off-site upload | BLOCKED — real storage required |
| Restore | timed restore from real provider | BLOCKED — real drill required |
| Monitoring | all targets up, retention/capacity, protected admin | PARTIAL — config ready; deployment absent |
| Alerting | staffed receiver, ack and resolved-message exercise | BLOCKED — human destination required |
| MFA | mandatory privileged-user factor | BLOCKED — implementation/provider/policy absent |
| Recovery | verified delivery/identity flow and support policy | BLOCKED — implementation/provider absent |
| Operations | named release/on-call/security/backup/privacy owners | BLOCKED — assignments required |
| Privacy/legal | DPIA, basis, retention, notices and contracts | BLOCKED — human review required |
| Smoke | HTTPS and approved synthetic authenticated run | BLOCKED — environment/account required |

Human alerting must define severity routing, primary/backup recipients, acknowledgement time, escalation and after-hours coverage. No webhook, address or person is invented here.
