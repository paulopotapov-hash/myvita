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
if [ "${OFFSITE_BACKUP_ENABLED:-false}" = "true" ]; then
    [[ "${OFFSITE_AGE_RECIPIENT:-}" =~ age1[02-9ac-hj-np-z]{58} ]] || {
        echo "BLOCKED: OFFSITE_AGE_RECIPIENT must hold the age public key used to encrypt off-site backups" >&2; exit 1;
    }
    [ "${OFFSITE_ALLOW_PLAINTEXT:-false}" != "true" ] || {
        echo "BLOCKED: OFFSITE_ALLOW_PLAINTEXT must not be enabled in production" >&2; exit 1;
    }
fi

# Human alerting: a real receiver and an external heartbeat (dead man's switch).
case "${ALERT_DELIVERY:-unconfigured}" in
    email | webhook | email+webhook) ;;
    *) echo "BLOCKED: ALERT_DELIVERY must name a real human destination (email, webhook or email+webhook)" >&2; exit 1 ;;
esac
[ -n "${ALERT_SECRETS_DIR:-}" ] && [ -s "${ALERT_SECRETS_DIR}/heartbeat_url" ] || {
    echo "BLOCKED: ALERT_SECRETS_DIR must contain heartbeat_url (external dead man's switch)" >&2; exit 1;
}
targets_dir="${MONITORING_TARGETS_DIR:-monitoring/targets}"
grep -q "https://${PUBLIC_DOMAIN}/" "${targets_dir}/public_https.yml" 2>/dev/null || {
    echo "BLOCKED: ${targets_dir}/public_https.yml must probe https://${PUBLIC_DOMAIN}/healthz (monitoring/targets/README.md)" >&2; exit 1;
}
docker run --rm --entrypoint /bin/sh \
    -e ALERT_DELIVERY -e ALERT_EMAIL_TO -e ALERT_EMAIL_FROM -e ALERT_SMTP_SMARTHOST -e ALERT_SMTP_USERNAME \
    -e ALERTMANAGER_RENDER_ONLY=true \
    -v "$PWD/monitoring/alertmanager/render-and-run.sh:/render.sh:ro" \
    -v "${ALERT_SECRETS_DIR}:/run/secrets/alerting:ro" \
    prom/alertmanager:v0.28.1 /render.sh >/dev/null || {
    echo "BLOCKED: the Alertmanager receiver configuration does not render or validate" >&2; exit 1;
}

# Transactional e-mail (optional; when enabled it must be complete and use HTTPS links).
if [ "${EMAIL_DELIVERY_ENABLED:-false}" = "true" ]; then
    for name in SMTP_HOST SMTP_USERNAME SMTP_PASSWORD EMAIL_FROM PUBLIC_APP_URL; do
        value="${!name:-}"
        if [ -z "$value" ] || [[ "$value" == *"<INJECT_"* ]]; then
            echo "BLOCKED: EMAIL_DELIVERY_ENABLED=true but $name is missing or a placeholder" >&2; exit 1
        fi
    done
    [[ "$PUBLIC_APP_URL" == "https://${PUBLIC_DOMAIN}" || "$PUBLIC_APP_URL" == "https://${PUBLIC_DOMAIN}/" ]] || {
        echo "BLOCKED: PUBLIC_APP_URL must be https://${PUBLIC_DOMAIN}" >&2; exit 1;
    }
fi
if [ "${SELF_SERVICE_PASSWORD_RESET_ENABLED:-false}" = "true" ]; then
    [ "${EMAIL_DELIVERY_ENABLED:-false}" = "true" ] || {
        echo "BLOCKED: SELF_SERVICE_PASSWORD_RESET_ENABLED requires EMAIL_DELIVERY_ENABLED" >&2; exit 1;
    }
    echo "NOTE: self-service password reset is enabled; it requires the approved identity-verification policy (docs/email-delivery.md)." >&2
fi

docker compose -f docker-compose.prod.yml -f docker-compose.monitoring.yml config --quiet
docker run --rm --entrypoint /bin/promtool \
    -v "$PWD/monitoring:/etc/prometheus:ro" prom/prometheus:v3.5.0 \
    check config /etc/prometheus/prometheus.yml >/dev/null
docker run --rm --entrypoint /bin/promtool \
    -v "$PWD/monitoring:/etc/prometheus:ro" prom/prometheus:v3.5.0 \
    test rules /etc/prometheus/alerts.test.yml >/dev/null

echo "Preflight configuration checks passed. External TLS, backups, alert delivery, e-mail delivery, owners and privacy gates still require evidence (docs/operations.md)."
