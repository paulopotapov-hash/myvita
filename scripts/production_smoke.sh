#!/usr/bin/env bash
set -euo pipefail

: "${SMOKE_BASE_URL:?Set SMOKE_BASE_URL to the approved HTTPS origin}"

case "$SMOKE_BASE_URL" in
    https://*) ;;
    *) echo "BLOCKED: SMOKE_BASE_URL must use HTTPS" >&2; exit 1 ;;
esac
base_url="${SMOKE_BASE_URL%/}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/myvita-smoke.XXXXXX")"
trap 'rm -rf "$tmp_dir"' EXIT
headers="$tmp_dir/headers"
cookies="$tmp_dir/cookies"

expect_status() {
    local expected="$1"
    local url="$2"
    local actual
    actual="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$url")"
    if [ "$actual" != "$expected" ]; then
        echo "FAIL: $url returned $actual, expected $expected" >&2
        exit 1
    fi
}

expect_status 200 "$base_url/health"
expect_status 200 "$base_url/ready"
expect_status 200 "$base_url/"
expect_status 404 "$base_url/metrics"
# The SPA fallback answers unknown paths with index.html, so assert the API schema is absent
# (not JSON) rather than a 404 status.
openapi_type="$(curl --silent --output /dev/null --write-out '%{content_type}' "$base_url/openapi.json")"
case "$openapi_type" in
    application/json*) echo "FAIL: $base_url/openapi.json exposes the API schema" >&2; exit 1 ;;
esac

curl --silent --show-error --head --output "$headers" "$base_url/"
for header in content-security-policy x-content-type-options x-frame-options referrer-policy strict-transport-security; do
    grep -qi "^${header}:" "$headers" || {
        echo "FAIL: response is missing $header" >&2
        exit 1
    }
done

if [ -n "${SMOKE_EMAIL:-}" ] || [ -n "${SMOKE_PASSWORD:-}" ]; then
    : "${SMOKE_EMAIL:?Set both SMOKE_EMAIL and SMOKE_PASSWORD}"
    : "${SMOKE_PASSWORD:?Set both SMOKE_EMAIL and SMOKE_PASSWORD}"
    command -v jq >/dev/null || { echo "BLOCKED: jq is required for authenticated smoke tests" >&2; exit 1; }

    jq -n --arg email "$SMOKE_EMAIL" --arg password "$SMOKE_PASSWORD" \
        '{email: $email, password: $password}' | \
        curl --silent --show-error --fail-with-body \
            --header 'Content-Type: application/json' \
            --data-binary @- --cookie-jar "$cookies" --dump-header "$headers" \
            "$base_url/api/v1/auth/login" >/dev/null

    session_cookie_header="$(grep -i '^set-cookie: myvita_session=' "$headers" | tail -n 1)"
    session_cookie_header="$(printf '%s' "$session_cookie_header" | tr '[:upper:]' '[:lower:]')"
    if [[ "$session_cookie_header" != *secure* || "$session_cookie_header" != *httponly* ]]; then
        echo "FAIL: authenticated session cookie is not Secure and HttpOnly" >&2
        exit 1
    fi
    csrf_token="$(awk '$6 == "myvita_csrf" {print $7}' "$cookies" | tail -n 1)"
    [ -n "$csrf_token" ] || { echo "FAIL: CSRF cookie was not issued" >&2; exit 1; }

    curl --silent --show-error --fail-with-body --cookie "$cookies" \
        "$base_url/api/v1/auth/me" >/dev/null

    if [ -n "${SMOKE_FORBIDDEN_URL:-}" ]; then
        actual="$(curl --silent --show-error --cookie "$cookies" --output /dev/null \
            --write-out '%{http_code}' "$SMOKE_FORBIDDEN_URL")"
        [ "$actual" = 403 ] || { echo "FAIL: authorization probe returned $actual, expected 403" >&2; exit 1; }
    fi
    if [ -n "${SMOKE_CROSS_TENANT_URL:-}" ]; then
        actual="$(curl --silent --show-error --cookie "$cookies" --output /dev/null \
            --write-out '%{http_code}' "$SMOKE_CROSS_TENANT_URL")"
        [ "$actual" = 404 ] || { echo "FAIL: tenant-isolation probe returned $actual, expected 404" >&2; exit 1; }
    fi

    curl --silent --show-error --fail-with-body --request POST --cookie "$cookies" \
        --header "X-CSRF-Token: $csrf_token" "$base_url/api/v1/auth/logout" >/dev/null
    actual="$(curl --silent --show-error --cookie "$cookies" --output /dev/null \
        --write-out '%{http_code}' "$base_url/api/v1/auth/me")"
    [ "$actual" = 401 ] || { echo "FAIL: logged-out session returned $actual, expected 401" >&2; exit 1; }
else
    echo "Authenticated smoke checks skipped: no approved synthetic account was supplied."
fi

echo "Production smoke checks passed for $base_url."
