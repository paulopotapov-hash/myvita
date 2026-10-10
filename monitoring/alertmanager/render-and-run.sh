#!/bin/sh
# Renders the Alertmanager configuration from the environment and secret files,
# validates it, then runs Alertmanager (docs/operations.md, "Human alert delivery").
#
# Nothing deployment-specific lives in Git: recipient addresses and the SMTP
# relay come from the environment; the SMTP password, webhook URL and heartbeat
# URL come from files in $ALERT_SECRETS_DIR (mounted read-only), so they never
# appear in `docker inspect`, the rendered file or the logs.
#
#   ALERT_DELIVERY        email | webhook | email+webhook | unconfigured
#   ALERT_EMAIL_TO        comma-separated recipients (email)
#   ALERT_EMAIL_FROM      sender address (email)
#   ALERT_SMTP_SMARTHOST  relay host:port, TLS required (email)
#   ALERT_SMTP_USERNAME   relay user; needs secret file smtp_password (email, optional)
#   secret webhook_url    incident/chat webhook (webhook)
#   secret heartbeat_url  external dead man's switch, pinged every minute by the
#                         always-firing Watchdog alert (strongly recommended;
#                         required by scripts/production_preflight.sh)
#
# "unconfigured" starts Alertmanager with no human receiver and says so loudly;
# the production preflight refuses it. Any other misconfiguration exits non-zero
# so the container never runs with a silently broken receiver.
set -eu

SECRETS_DIR="${ALERT_SECRETS_DIR:-/run/secrets/alerting}"
DELIVERY="${ALERT_DELIVERY:-unconfigured}"
OUT="${ALERTMANAGER_CONFIG_OUT:-/tmp/alertmanager.yml}"

fail() {
    echo "alertmanager-config: $*" >&2
    exit 64
}

# A value goes into a double-quoted YAML scalar: one non-empty line, no quote or backslash.
plain() {
    case "$2" in
        "" | *'"'* | *\\* | *"
"*) fail "$1 is missing or contains a quote, backslash or newline" ;;
    esac
}

secret() {
    [ -s "$SECRETS_DIR/$1" ] || fail "secret file '$1' is missing or empty in $SECRETS_DIR"
}

email=false
webhook=false
case "$DELIVERY" in
    email) email=true ;;
    webhook) webhook=true ;;
    email+webhook) email=true webhook=true ;;
    unconfigured)
        echo "alertmanager-config: WARNING ALERT_DELIVERY=unconfigured — alerts reach NO human. Not acceptable in production." >&2
        ;;
    *) fail "ALERT_DELIVERY must be email, webhook, email+webhook or unconfigured (got '$DELIVERY')" ;;
esac

if [ "$email" = true ]; then
    plain ALERT_EMAIL_TO "${ALERT_EMAIL_TO:-}"
    plain ALERT_EMAIL_FROM "${ALERT_EMAIL_FROM:-}"
    plain ALERT_SMTP_SMARTHOST "${ALERT_SMTP_SMARTHOST:-}"
    case "$ALERT_SMTP_SMARTHOST" in *:[0-9]*) ;; *) fail "ALERT_SMTP_SMARTHOST must be host:port" ;; esac
    if [ -n "${ALERT_SMTP_USERNAME:-}" ]; then
        plain ALERT_SMTP_USERNAME "$ALERT_SMTP_USERNAME"
        secret smtp_password
    fi
fi
[ "$webhook" = false ] || secret webhook_url

heartbeat=false
if [ -s "$SECRETS_DIR/heartbeat_url" ]; then
    heartbeat=true
else
    echo "alertmanager-config: WARNING no heartbeat_url secret — a dead alerting pipeline would go unnoticed." >&2
fi

human=human
[ "$email" = true ] || [ "$webhook" = true ] || human=blackhole
watchdog=blackhole
[ "$heartbeat" = false ] || watchdog=heartbeat

umask 077
{
    cat <<YAML
# Rendered by render-and-run.sh at container start. Do not edit; set the environment instead.
route:
  receiver: ${human}
  group_by: [alertname, severity]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - receiver: ${watchdog}
      matchers: ['alertname="Watchdog"']
      group_wait: 0s
      group_interval: 1m
      repeat_interval: 1m
    - receiver: ${human}
      matchers: ['severity="critical"']
      repeat_interval: 1h

inhibit_rules:
  # A critical disk alert makes the matching warning redundant.
  - source_matchers: ['alertname="HostDiskUsageCritical"']
    target_matchers: ['alertname="HostDiskUsageHigh"']
    equal: [instance]

receivers:
  - name: blackhole
YAML
    if [ "$heartbeat" = true ]; then
        cat <<YAML
  - name: heartbeat
    webhook_configs:
      - url_file: "${SECRETS_DIR}/heartbeat_url"
        send_resolved: false
YAML
    fi
    if [ "$human" = human ]; then
        echo "  - name: human"
        if [ "$email" = true ]; then
            cat <<YAML
    email_configs:
      - to: "${ALERT_EMAIL_TO}"
        from: "${ALERT_EMAIL_FROM}"
        smarthost: "${ALERT_SMTP_SMARTHOST}"
        require_tls: true
        send_resolved: true
        headers:
          Subject: '[myVita {{ .Status | toUpper }}] {{ .CommonLabels.alertname }} ({{ .CommonLabels.severity }})'
YAML
            if [ -n "${ALERT_SMTP_USERNAME:-}" ]; then
                cat <<YAML
        auth_username: "${ALERT_SMTP_USERNAME}"
        auth_password_file: "${SECRETS_DIR}/smtp_password"
YAML
            fi
        fi
        if [ "$webhook" = true ]; then
            cat <<YAML
    webhook_configs:
      - url_file: "${SECRETS_DIR}/webhook_url"
        send_resolved: true
        max_alerts: 20
YAML
        fi
    fi
} >"$OUT"

if command -v amtool >/dev/null 2>&1; then
    amtool check-config "$OUT" >/dev/null || fail "rendered configuration is invalid"
fi
echo "alertmanager-config: delivery=${DELIVERY} heartbeat=${heartbeat}" >&2

[ "${ALERTMANAGER_RENDER_ONLY:-false}" = true ] && exit 0
exec /bin/alertmanager --config.file="$OUT" --storage.path=/alertmanager "$@"
