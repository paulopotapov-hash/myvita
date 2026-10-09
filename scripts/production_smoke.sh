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

# ---------------------------------------------------------------------------
# Authenticated checks (optional; approved synthetic account only).
#
# Contract (docs/security/account-lifecycle.md):
# - POST /auth/login answers 200 + session when the account has no second
#   factor, or 202 {"mfa_required": true} with NO session — only a
#   path-scoped challenge cookie — when it has one. The session then comes
#   from POST /auth/mfa/verify with a TOTP code.
# - Staff and clinic admins must have MFA in production. Until they enrol,
#   the session exists but every endpoint except /auth/me, logout and
#   enrolment answers 403 + X-Account-Action-Required.
#
# Second factor for an MFA-enabled synthetic account, one of:
#   SMOKE_MFA_CODE      current 6-digit code, typed just before the run
#   SMOKE_TOTP_SECRET   the account's base32 TOTP seed (code is computed
#                       with oathtool or python3; keep it in the secret manager)
# A code is accepted once per 30 s step: wait for a new code between runs.
#
# Optional: SMOKE_EXPECTED_ROLE (patient|staff|clinic_admin),
# SMOKE_FORBIDDEN_URL (must answer a genuine 403 authorization denial),
# SMOKE_CROSS_TENANT_URL (must answer 404). The probes are only meaningful
# for an account with no pending action, so they are refused otherwise.
# ---------------------------------------------------------------------------

set_cookie_line() {
    { grep -i "^set-cookie: $1=" "$2" || true; } | tail -n 1 | tr -d '\r' | tr '[:upper:]' '[:lower:]'
}

require_cookie_flags() {
    local name="$1" file="$2" line flag
    shift 2
    line="$(set_cookie_line "$name" "$file")"
    [ -n "$line" ] || { echo "FAIL: $name cookie was not issued" >&2; exit 1; }
    for flag in "$@"; do
        [[ "$line" == *"$flag"* ]] || { echo "FAIL: $name cookie lacks '$flag'" >&2; exit 1; }
    done
}

totp_code() {
    if [ -n "${SMOKE_MFA_CODE:-}" ]; then
        printf '%s' "$SMOKE_MFA_CODE"
    elif [ -n "${SMOKE_TOTP_SECRET:-}" ]; then
        if command -v oathtool >/dev/null; then
            oathtool --totp --base32 "$SMOKE_TOTP_SECRET"
        elif command -v python3 >/dev/null; then
            SECRET="$SMOKE_TOTP_SECRET" python3 -c '
import base64, hmac, os, struct, time
s = os.environ["SECRET"].upper().replace(" ", "")
key = base64.b32decode(s + "=" * (-len(s) % 8))
mac = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), "sha1").digest()
o = mac[-1] & 0x0F
print(str((struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6), end="")'
        else
            echo "BLOCKED: SMOKE_TOTP_SECRET needs oathtool or python3" >&2
            exit 1
        fi
    else
        echo "BLOCKED: the account requires MFA; set SMOKE_MFA_CODE or SMOKE_TOTP_SECRET" >&2
        exit 1
    fi
}

if [ -n "${SMOKE_EMAIL:-}" ] || [ -n "${SMOKE_PASSWORD:-}" ]; then
    : "${SMOKE_EMAIL:?Set both SMOKE_EMAIL and SMOKE_PASSWORD}"
    : "${SMOKE_PASSWORD:?Set both SMOKE_EMAIL and SMOKE_PASSWORD}"
    command -v jq >/dev/null || { echo "BLOCKED: jq is required for authenticated smoke tests" >&2; exit 1; }
    body="$tmp_dir/body"

    login_status="$(jq -n --arg email "$SMOKE_EMAIL" --arg password "$SMOKE_PASSWORD" \
        '{email: $email, password: $password}' | \
        curl --silent --show-error \
            --header 'Content-Type: application/json' \
            --data-binary @- --cookie-jar "$cookies" --dump-header "$headers" \
            --output "$body" --write-out '%{http_code}' \
            "$base_url/api/v1/auth/login")"

    case "$login_status" in
        200)
            echo "Login: session issued without a second factor."
            ;;
        202)
            [ "$(jq -r '.mfa_required' "$body")" = true ] || {
                echo "FAIL: login answered 202 without the MFA challenge contract" >&2; exit 1;
            }
            [ -z "$(set_cookie_line myvita_session "$headers")" ] || {
                echo "FAIL: a session cookie was issued before the second factor" >&2; exit 1;
            }
            require_cookie_flags myvita_mfa_challenge "$headers" secure httponly "samesite=strict" "path=/api/v1/auth/mfa"
            code="$(totp_code)"
            verify_status="$(jq -n --arg code "$code" '{code: $code}' | \
                curl --silent --show-error \
                    --header 'Content-Type: application/json' \
                    --data-binary @- --cookie "$cookies" --cookie-jar "$cookies" --dump-header "$headers" \
                    --output "$body" --write-out '%{http_code}' \
                    "$base_url/api/v1/auth/mfa/verify")"
            [ "$verify_status" = 200 ] || {
                echo "FAIL: MFA verification returned $verify_status (wrong/reused code, lockout or expired challenge)" >&2
                exit 1
            }
            echo "Login: MFA challenge verified."
            ;;
        *)
            echo "FAIL: login returned $login_status, expected 200 or 202" >&2
            exit 1
            ;;
    esac

    require_cookie_flags myvita_session "$headers" secure httponly
    csrf_token="$(awk '$6 == "myvita_csrf" {print $7}' "$cookies" | tail -n 1)"
    [ -n "$csrf_token" ] || { echo "FAIL: CSRF cookie was not issued" >&2; exit 1; }

    curl --silent --show-error --fail-with-body --cookie "$cookies" --output "$body" \
        "$base_url/api/v1/auth/me"
    role="$(jq -r '.role' "$body")"
    pending_action="$(jq -r '.pending_action // empty' "$body")"
    mfa_required="$(jq -r '.mfa_required' "$body")"
    if [ -n "${SMOKE_EXPECTED_ROLE:-}" ] && [ "$role" != "$SMOKE_EXPECTED_ROLE" ]; then
        echo "FAIL: authenticated role is $role, expected $SMOKE_EXPECTED_ROLE" >&2
        exit 1
    fi
    if [ "$role" != patient ] && [ "$mfa_required" != true ]; then
        echo "FAIL: MFA is not mandatory for role $role" >&2
        exit 1
    fi
    echo "Authenticated as role=$role pending_action=${pending_action:-none}."

    if [ -n "$pending_action" ]; then
        # The gate itself is part of the contract: any ordinary endpoint must
        # refuse with the pending action named in the header.
        probe_status="$(curl --silent --show-error --cookie "$cookies" --output /dev/null \
            --dump-header "$headers" --write-out '%{http_code}' "$base_url/api/v1/appointments")"
        gate_action="$({ grep -i '^x-account-action-required:' "$headers" || true; } | tail -n 1 | cut -d: -f2 | tr -d ' \r')"
        [ "$probe_status" = 403 ] && [ "$gate_action" = "$pending_action" ] || {
            echo "FAIL: pending action '$pending_action' is not enforced (got $probe_status, header '$gate_action')" >&2
            exit 1
        }
        if [ -n "${SMOKE_FORBIDDEN_URL:-}" ] || [ -n "${SMOKE_CROSS_TENANT_URL:-}" ]; then
            echo "BLOCKED: authorization/tenant probes need an account with no pending action (has '$pending_action')" >&2
            exit 1
        fi
        echo "WARNING: synthetic account has pending action '$pending_action'; only the account gate was verified."
    fi

    if [ -n "${SMOKE_FORBIDDEN_URL:-}" ]; then
        actual="$(curl --silent --show-error --cookie "$cookies" --output /dev/null \
            --dump-header "$headers" --write-out '%{http_code}' "$SMOKE_FORBIDDEN_URL")"
        [ "$actual" = 403 ] || { echo "FAIL: authorization probe returned $actual, expected 403" >&2; exit 1; }
        ! grep -qi '^x-account-action-required:' "$headers" || {
            echo "FAIL: authorization probe was refused by the account gate, not by authorization" >&2; exit 1;
        }
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
    echo "Authenticated smoke checks passed."
else
    echo "Authenticated smoke checks skipped: no approved synthetic account was supplied."
fi
