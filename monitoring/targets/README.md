# Prometheus file-based targets (deployment-specific, not committed)

`public_https.yml` tells Prometheus which public URL to probe through DNS, TLS and
the proxy. It contains the real domain, so it is created on the server and never
committed (this directory only holds the example and this README).

```bash
sed "s/<PUBLIC_DOMAIN>/${PUBLIC_DOMAIN}/" monitoring/targets/public_https.yml.example \
  > "${MONITORING_TARGETS_DIR:-monitoring/targets}/public_https.yml"
```

Prometheus re-reads the file automatically. Until it exists,
`MyVitaPublicHTTPSProbeMissing` fires, and the certificate-expiry alerts cannot work.
