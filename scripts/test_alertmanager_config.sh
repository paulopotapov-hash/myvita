#!/usr/bin/env bash
# Tests monitoring/alertmanager/render-and-run.sh without any real destination:
# renders every delivery mode with throwaway secret files, checks that
# misconfigurations are refused, and validates the rendered files with amtool
# (from the pinned Alertmanager image) when Docker is available.
# REQUIRE_AMTOOL=1 makes a missing Docker a failure instead of a skip.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
render="${repo_root}/monitoring/alertmanager/render-and-run.sh"
image="prom/alertmanager:v0.28.1"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failures=0

secrets="$work/secrets"
mkdir -p "$secrets"
printf 'not-a-real-password\n' >"$secrets/smtp_password"
printf 'https://hooks.invalid/alerts\n' >"$secrets/webhook_url"
printf 'https://heartbeat.invalid/ping\n' >"$secrets/heartbeat_url"

run_render() { # name, then env assignments
    local name="$1"
    shift
    env -i PATH="$PATH" ALERT_SECRETS_DIR="$secrets" ALERTMANAGER_CONFIG_OUT="$work/$name.yml" \
        ALERTMANAGER_RENDER_ONLY=true "$@" sh "$render" 2>"$work/$name.log"
}

expect_ok() {
    local name="$1"
    shift
    if run_render "$name" "$@"; then
        echo "ok   render $name"
    else
        echo "FAIL render $name: $(cat "$work/$name.log")"
        failures=$((failures + 1))
    fi
}

expect_refused() {
    local name="$1"
    shift
    if run_render "$name" "$@"; then
        echo "FAIL $name: misconfiguration was accepted"
        failures=$((failures + 1))
    else
        echo "ok   refused $name"
    fi
}

email_env=(ALERT_EMAIL_TO=oncall@example.org ALERT_EMAIL_FROM=alerts@example.org ALERT_SMTP_SMARTHOST=smtp.example.org:587 ALERT_SMTP_USERNAME=alerts)

expect_ok email ALERT_DELIVERY=email "${email_env[@]}"
expect_ok webhook ALERT_DELIVERY=webhook
expect_ok both ALERT_DELIVERY=email+webhook "${email_env[@]}"
expect_ok unconfigured ALERT_DELIVERY=unconfigured

grep -q "alerts reach NO human" "$work/unconfigured.log" || { echo "FAIL unconfigured mode is not loud"; failures=$((failures + 1)); }
grep -q "receiver: blackhole" "$work/unconfigured.yml" || { echo "FAIL unconfigured mode routes somewhere"; failures=$((failures + 1)); }
grep -q "url_file: \"$secrets/heartbeat_url\"" "$work/email.yml" || { echo "FAIL heartbeat not routed"; failures=$((failures + 1)); }
for file in email webhook both; do
    if grep -q "not-a-real-password\|hooks.invalid\|heartbeat.invalid" "$work/$file.yml"; then
        echo "FAIL $file: a secret value leaked into the rendered config"
        failures=$((failures + 1))
    fi
done

expect_refused unknown-mode ALERT_DELIVERY=pager
expect_refused email-without-recipient ALERT_DELIVERY=email ALERT_EMAIL_FROM=a@example.org ALERT_SMTP_SMARTHOST=smtp.example.org:587
expect_refused smarthost-without-port ALERT_DELIVERY=email ALERT_EMAIL_TO=a@example.org ALERT_EMAIL_FROM=b@example.org ALERT_SMTP_SMARTHOST=smtp.example.org
expect_refused injection ALERT_DELIVERY=email 'ALERT_EMAIL_TO=a@example.org"
  - evil: 1' ALERT_EMAIL_FROM=b@example.org ALERT_SMTP_SMARTHOST=smtp.example.org:587
rm "$secrets/webhook_url"
expect_refused webhook-without-secret ALERT_DELIVERY=webhook
printf 'https://hooks.invalid/alerts\n' >"$secrets/webhook_url"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    for file in email webhook both unconfigured; do
        if docker run --rm --entrypoint /bin/amtool -v "$work:/work:ro" -v "$secrets:$secrets:ro" "$image" \
            check-config "/work/$file.yml" >"$work/$file.amtool" 2>&1; then
            echo "ok   amtool $file"
        else
            echo "FAIL amtool $file: $(cat "$work/$file.amtool")"
            failures=$((failures + 1))
        fi
    done
elif [ "${REQUIRE_AMTOOL:-0}" = "1" ]; then
    echo "FAIL Docker is required to validate with amtool"
    failures=$((failures + 1))
else
    echo "skip amtool validation (Docker unavailable)"
fi

[ "$failures" -eq 0 ] && echo "Alertmanager configuration tests passed." || { echo "$failures failure(s)"; exit 1; }
