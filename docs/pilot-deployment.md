# Controlled pilot deployment readiness

No public deployment is authorized by this document.

## Required real infrastructure inputs

1. Approved production host/network with encrypted storage and least-privilege administration.
2. DNS name and renewable TLS certificate/automation.
3. Approved secret manager and unique production values.
4. Exact `PUBLIC_DOMAIN`, `ALLOWED_HOSTS` and `CORS_ORIGINS`.
5. Private PostgreSQL network, off-site backup provider and staffed alert destination.
6. Reviewed release commit/images and rollback owner.

Production Compose forces production mode, secure cookies, no direct staff creation, internal PostgreSQL, migration gating, read-only backend and dropped capabilities. Only the reverse proxy is published. The HTTP overlay is local validation only and must never be the clinical endpoint.

## TLS/domain activation

- keep private keys outside Git;
- terminate TLS at the proxy and redirect HTTP to HTTPS;
- expose only the approved hostname and HTTPS port;
- confirm secure cookie attributes, certificate chain/renewal and untrusted Host rejection;
- set exact CORS origin(s); never use wildcard with credentials;
- keep `/metrics`, database, backend, frontend, Prometheus and Alertmanager off the public network;
- verify health/readiness and a synthetic invitation flow before enabling traffic.

Domain purchase, DNS, certificate issuance, production host, secret injection and network policy are **BLOCKED — EXTERNAL INFRASTRUCTURE**.
