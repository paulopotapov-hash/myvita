# P7-A production host and network requirements

Status: **BLOCKED — REAL PRODUCTION HOST AND DOMAIN REQUIRED**.

## Capacity derived from the stack

The deployment runs PostgreSQL 16, backend, migration job, frontend, two proxies, backup, Prometheus, Grafana, Alertmanager and five exporters. The repository defines no container resource limits and contains no production load profile, so it cannot honestly establish a contractual hardware minimum.

For the first capacity test, use no less than **2 vCPU and 4 GiB RAM**; **4 vCPU and 8 GiB RAM** is the provisional single-host pilot baseline because PostgreSQL, Prometheus/Grafana and image builds compete for memory and CPU. This is an engineering qualification baseline, not measured sizing. Before real traffic, run representative synthetic load, observe saturation and add container limits. Failure to meet latency, backup-window or 30% free-memory headroom blocks go-live.

Storage must be encrypted, SSD-backed and separately monitored. Size it from: operating system and immutable images (at least 20 GiB free) + PostgreSQL peak data/index size + WAL/headroom + Prometheus retention + local backup retention + 30% free-space reserve. Database, monitoring and backup growth must be measured; an unmeasured disk allocation is not production evidence.

## Host requirements

- 64-bit Linux supported by current Docker Engine and Compose v2; Docker daemon and host security patches maintained.
- UTC at OS/container level with NTP synchronization. User-facing timezone conversion belongs at the application boundary.
- Persistent encrypted filesystems for Docker volumes; no database on ephemeral root storage.
- Root/admin access limited to named operators; SSH keys/MFA and audit logging controlled outside this repository.
- Docker log rotation and host log retention configured without clinical payload collection.
- Outbound HTTPS/DNS/NTP plus only the approved registry, certificate, backup and alert providers.

## Network and firewall

Flow: Internet → TCP 443 TLS reverse proxy → frontend and `/api` backend. TCP 80 is optional and redirect-only. Backend/frontend → PostgreSQL occurs exclusively on the internal Compose `data` network.

| Port | Exposure | Purpose |
|---|---|---|
| 443/tcp | public | HTTPS only |
| 80/tcp | optional public | HTTP→HTTPS redirect only |
| 22/tcp | restricted admin CIDRs/VPN | host administration, if used |
| 5432/tcp | internal only | PostgreSQL |
| 8000/8080 | internal only | backend/frontend/proxies |
| 9090/9093/9100/9115/9187 | internal only | monitoring/exporters |
| 3000/tcp | loopback/VPN/tunnel only | Grafana administration |

Default-deny inbound and outbound rules must be recorded. Prometheus, Alertmanager and exporters have no host ports; Grafana binds loopback. `PUBLIC_DOMAIN`, `ALLOWED_HOSTS` and `CORS_ORIGINS` must use the approved DNS name. Health endpoints may be reached by the load balancer/monitoring plane but must not bypass TLS or trusted-host validation.

## External acceptance evidence

Host inventory, encryption proof, firewall export, Docker versions, disk/backup mount layout, NTP state, capacity test and monitoring screenshots are required. None exists yet.
