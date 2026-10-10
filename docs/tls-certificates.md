# HTTPS, TLS certificates and renewal

Status: **CONFIGURATION PREPARED, NOT VERIFIED.** The TLS proxy template, the renewal script and certificate monitoring exist and are tested offline. No real domain, certificate or deployed endpoint has been verified. Do not describe production TLS as working until the checks at the end pass against the real host.

## Architecture

- The public proxy (`proxy/`, nginx unprivileged) is the only published component.
- `docker-compose.prod.yml` publishes HTTP (`HTTP_PORT`, default 80). The TLS overlay (`docker-compose.prod-tls.yml.example`) adds port 443 and swaps in `proxy/nginx.tls.conf.template.example`.
- HTTP serves only `/healthz`, ACME challenges (`/.well-known/acme-challenge/`) and a 301 to `https://${PUBLIC_DOMAIN}`. The redirect never uses the client's `Host` header.
- HTTPS: TLS 1.2 and 1.3, no session tickets, HSTS (2 years), CSP, `X-Frame-Options DENY`, `nosniff`, `Referrer-Policy no-referrer`, `Permissions-Policy`. `/metrics` returns 404, like the HTTP template.
- The proxy sets `X-Forwarded-For` to the client address. The backend trusts forwarded headers only from the proxy's fixed address (`TRUSTED_PROXIES`, `--forwarded-allow-ips`). With `ENVIRONMENT=production`, the backend refuses insecure cookies, non-HTTPS CORS origins, wildcard or local hosts (`app/core/config.py`).

## First certificate

Prerequisites: a public DNS name you control, its A/AAAA record pointing at the host, and ports 80 and 443 open.

```bash
# On the host, from the repository root, as root. Values from the deployment secret store.
export PUBLIC_DOMAIN=<approved name> ACME_EMAIL=<team mailbox> TLS_CERT_DIR=/etc/myvita/tls
cp docker-compose.prod-tls.yml.example docker-compose.prod-tls.yml   # not committed
docker compose -f docker-compose.prod.yml up -d proxy                 # HTTP only, serves challenges
# The TLS overlay needs a certificate to start, so the first issuance runs before it:
scripts/renew_tls_certificate.sh --dry-run          # staging CA, installs nothing
scripts/renew_tls_certificate.sh                    # real certificate, installs into TLS_CERT_DIR
docker compose -f docker-compose.prod.yml -f docker-compose.prod-tls.yml up -d proxy
```

Before the overlay is up, the script's reload and served-certificate check target the HTTP-only proxy and fail. That expected first-run failure leaves the certificate installed. Run the script once more after the overlay is up; it reports "already current".

## Renewal

`scripts/renew_tls_certificate.sh` runs certbot (pinned image, `CERTBOT_IMAGE`) with the shared webroot. certbot renews only within 30 days of expiry. The script:

1. refuses a certificate that does not cover `PUBLIC_DOMAIN`, does not match its key or expires within 24 hours;
2. installs it atomically, with the key `0600` and owned by the proxy user (uid 101);
3. reloads nginx, then checks that the proxy serves exactly the installed certificate;
4. exits non-zero on any failure and never prints key material.

Schedule it daily (cron or systemd timer) with output to the system journal:

```cron
17 3 * * * root cd /opt/myvita && PUBLIC_DOMAIN=... ACME_EMAIL=... TLS_CERT_DIR=/etc/myvita/tls scripts/renew_tls_certificate.sh 2>&1 | logger -t myvita-tls
```

Monitoring: the `public-https` Prometheus job probes `https://<PUBLIC_DOMAIN>/healthz` through DNS, TLS and the proxy (target file: `monitoring/targets/README.md`). The following alerts cover it:

- `MyVitaPublicHTTPSDown`;
- `MyVitaTLSCertificateExpiringSoon` (21 days) and `MyVitaTLSCertificateExpiryCritical` (7 days);
- `MyVitaPublicHTTPSProbeMissing`, which fires until the probe is configured.

A renewal that silently stops working is therefore caught weeks before expiry.

## Key compromise or CA incident

Revoke with certbot (`certbot revoke --cert-name <domain>` in the same container setup), remove the old files, issue a new certificate (the script requests a new key), reload, and record the incident. See `incident-response.md`.

## Verification against the real endpoint (not done yet)

Run these from outside the host and record the results:

- `curl -sSI http://<domain>/login` returns `301` to `https://<domain>/login`;
- `curl -sSI https://<domain>/login` shows HSTS, CSP and `nosniff`, and the certificate verifies;
- `/metrics`, `/docs` and `/openapi.json` are not served by the backend at the edge;
- an unknown `Host` header is rejected;
- session cookies are `Secure; HttpOnly; SameSite`;
- an external TLS scanner (for example SSL Labs) shows no protocol below TLS 1.2;
- `scripts/production_smoke.sh` passes;
- the expiry alert is visible in Prometheus.
