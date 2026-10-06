#!/usr/bin/env bash
set -euo pipefail

required=(POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB APP_DB_ROLE APP_DB_PASSWORD JWT_SECRET_KEY MFA_ENCRYPTION_KEY PRIVACY_FINGERPRINT_KEY PUBLIC_DOMAIN ALLOWED_HOSTS CORS_ORIGINS METRICS_TOKEN GRAFANA_ADMIN_PASSWORD)
failed=0
for name in "${required[@]}"; do
    value="${!name:-}"
    if [ -z "$value" ] || [[ "$value" == *"<INJECT_"* ]]; then
        echo "BLOCKED: $name is missing or still a placeholder" >&2
        failed=1
    fi
done
[ "$failed" -eq 0 ] || exit 1

[[ "$PUBLIC_DOMAIN" != "localhost" && "$PUBLIC_DOMAIN" != "127.0.0.1" ]] || {
    echo "BLOCKED: PUBLIC_DOMAIN is local" >&2; exit 1;
}
[[ "$CORS_ORIGINS" == *"https://"* && "$CORS_ORIGINS" != *'"*"'* ]] || {
    echo "BLOCKED: CORS_ORIGINS must contain explicit HTTPS origins" >&2; exit 1;
}
[[ "$ALLOWED_HOSTS" != *'"*"'* ]] || {
    echo "BLOCKED: ALLOWED_HOSTS must not contain a wildcard" >&2; exit 1;
}
[ "${#JWT_SECRET_KEY}" -ge 32 ] || {
    echo "BLOCKED: JWT_SECRET_KEY is shorter than 32 characters" >&2; exit 1;
}
[ "$APP_DB_ROLE" != "$POSTGRES_USER" ] || {
    echo "BLOCKED: APP_DB_ROLE must differ from the schema owner POSTGRES_USER" >&2; exit 1;
}
[ "${#APP_DB_PASSWORD}" -ge 16 ] || {
    echo "BLOCKED: APP_DB_PASSWORD is shorter than 16 characters" >&2; exit 1;
}
[ "$MFA_ENCRYPTION_KEY" != "$JWT_SECRET_KEY" ] || {
    echo "BLOCKED: MFA_ENCRYPTION_KEY must differ from JWT_SECRET_KEY" >&2; exit 1;
}
[ "${#PRIVACY_FINGERPRINT_KEY}" -ge 32 ] || {
    echo "BLOCKED: PRIVACY_FINGERPRINT_KEY is shorter than 32 characters" >&2; exit 1;
}
[ "$PRIVACY_FINGERPRINT_KEY" != "$JWT_SECRET_KEY" ] && [ "$PRIVACY_FINGERPRINT_KEY" != "$MFA_ENCRYPTION_KEY" ] || {
    echo "BLOCKED: PRIVACY_FINGERPRINT_KEY must differ from JWT_SECRET_KEY and MFA_ENCRYPTION_KEY" >&2; exit 1;
}

docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml config --quiet
docker run --rm --entrypoint /bin/promtool \
    -v "$PWD/monitoring:/etc/prometheus:ro" prom/prometheus:v3.5.0 \
    check config /etc/prometheus/prometheus.yml >/dev/null
docker run --rm --entrypoint /bin/promtool \
    -v "$PWD/monitoring:/etc/prometheus:ro" prom/prometheus:v3.5.0 \
    test rules /etc/prometheus/alerts.test.yml >/dev/null

echo "Preflight configuration checks passed. External TLS, backups, alerts, owners and privacy gates still require evidence."
