#!/usr/bin/env bash
# Offline tests for scripts/renew_tls_certificate.sh (--install-only path) and the TLS
# nginx template. No CA, domain or network is involved: certbot's output is simulated
# with throwaway self-signed certificates inside a Linux container, and the template is
# checked with `nginx -t` in the proxy's base image. Requires Docker.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

docker run --rm -i -v "$repo_root/scripts:/scripts:ro" -v "$work:/work" alpine:3.20 sh -s <<'IN_CONTAINER'
set -eu
apk add --no-cache bash openssl >/dev/null
domain=app.example.org
le=/work/le; out=/work/installed; live="$le/live/$domain"
mkdir -p "$live" "$out"
make_cert() { # dir name days [san]
    openssl req -x509 -newkey rsa:2048 -nodes -keyout "$1/privkey.pem" -out "$1/fullchain.pem" \
        -days "$2" -subj "/CN=$3" -addext "subjectAltName=DNS:$3" >/dev/null 2>&1
}
run() {
    PUBLIC_DOMAIN=$domain TLS_CERT_DIR=$out LETSENCRYPT_DIR=$le ACME_WEBROOT=/work/acme TLS_KEY_OWNER= \
        RELOAD_COMMAND="touch /work/reloaded" SKIP_SERVED_CHECK=true bash /scripts/renew_tls_certificate.sh --install-only
}
fail() { echo "FAIL $*"; exit 1; }

make_cert "$live" 90 "$domain"
run >/work/log1 || fail "valid certificate was refused: $(cat /work/log1)"
[ "$(stat -c %a "$out/privkey.pem")" = 600 ] || fail "private key mode"
[ "$(stat -c %a "$out/fullchain.pem")" = 644 ] || fail "certificate mode"
[ -e /work/reloaded ] || fail "proxy not reloaded"
grep -q "BEGIN" /work/log1 && fail "key or certificate material printed"
echo "ok   installs a valid certificate, 0600 key, reloads"

rm /work/reloaded
run >/work/log2 || fail "rerun failed"
grep -q "already current" /work/log2 || fail "rerun reinstalled"
[ ! -e /work/reloaded ] || fail "rerun reloaded needlessly"
echo "ok   idempotent when nothing changed"

before=$(sha256sum "$out/fullchain.pem")
make_cert "$live" 90 other.example.org
run >/work/log3 2>&1 && fail "certificate for another name accepted"
grep -q "does not cover" /work/log3 || fail "wrong reason: $(cat /work/log3)"
make_cert "$live" 90 "$domain"; mkdir -p /work/k; make_cert /work/k 90 "$domain"; cp /work/k/privkey.pem "$live/privkey.pem"
run >/work/log4 2>&1 && fail "mismatched key accepted"
grep -q "does not match" /work/log4 || fail "wrong reason: $(cat /work/log4)"
# Valid for 1 day: inside the 24h safety margin, so it must be refused.
make_cert "$live" 1 "$domain"
run >/work/log5 2>&1 && fail "expiring certificate accepted"
[ "$(sha256sum "$out/fullchain.pem")" = "$before" ] || fail "a refused certificate replaced the installed one"
echo "ok   refuses wrong name, mismatched key and expiring certificates without touching the installed one"

PUBLIC_DOMAIN=localhost TLS_CERT_DIR=$out bash /scripts/renew_tls_certificate.sh --install-only >/work/log6 2>&1 && fail "local domain accepted"
echo "ok   refuses a non-public PUBLIC_DOMAIN"
make_cert /work/k 90 "$domain"
IN_CONTAINER

# The TLS template must be valid nginx with a certificate in place.
mkdir -p "$work/tls"
cp "$work/k/fullchain.pem" "$work/k/privkey.pem" "$work/tls/"
chmod 0644 "$work/tls/"*
docker run --rm \
    --add-host backend:127.0.0.1 --add-host frontend:127.0.0.1 \
    -e PUBLIC_DOMAIN=app.example.org \
    -v "$repo_root/proxy/nginx.tls.conf.template.example:/etc/nginx/templates/default.conf.template:ro" \
    -v "$repo_root/proxy/proxy_params:/etc/nginx/proxy_params:ro" \
    -v "$work/tls:/etc/nginx/tls:ro" \
    nginxinc/nginx-unprivileged:1.27-alpine sh -c '/docker-entrypoint.sh nginx -t' >"$work/nginx.log" 2>&1 \
    || { echo "FAIL nginx -t on the TLS template:"; cat "$work/nginx.log"; exit 1; }
echo "ok   TLS template passes nginx -t"

# The served-certificate check, end to end: a real proxy on a private network, a
# shared volume for certificates, and the script reloading it through the Docker CLI.
suffix="$$"
net="tls-renewal-test-${suffix}" vol="tls-renewal-certs-${suffix}" proxy="tls-renewal-proxy-${suffix}"
cleanup_served() {
    docker rm -f "$proxy" >/dev/null 2>&1 || true
    docker network rm "$net" >/dev/null 2>&1 || true
    docker volume rm "$vol" >/dev/null 2>&1 || true
}
trap 'cleanup_served; rm -rf "$work"' EXIT
docker network create "$net" >/dev/null
docker volume create "$vol" >/dev/null
docker run --rm -v "$vol:/served" -v "$work:/work" alpine:3.20 sh -c '
    cp /work/k/fullchain.pem /work/k/privkey.pem /served/ && chown 101:101 /served/privkey.pem && chmod 0600 /served/privkey.pem'
docker run -d --name "$proxy" --network "$net" \
    --add-host backend:127.0.0.1 --add-host frontend:127.0.0.1 -e PUBLIC_DOMAIN=app.example.org \
    -v "$repo_root/proxy/nginx.tls.conf.template.example:/etc/nginx/templates/default.conf.template:ro" \
    -v "$repo_root/proxy/proxy_params:/etc/nginx/proxy_params:ro" \
    -v "$vol:/etc/nginx/tls:ro" nginxinc/nginx-unprivileged:1.27-alpine >/dev/null
sleep 2

docker run --rm -i --network "$net" -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$repo_root/scripts:/scripts:ro" -v "$vol:/served" -e PROXY="$proxy" alpine:3.20 sh -s <<'SERVED'
set -eu
apk add --no-cache bash openssl docker-cli >/dev/null
domain=app.example.org; live=/le/live/$domain
mkdir -p "$live"
new_cert() {
    openssl req -x509 -newkey rsa:2048 -nodes -keyout "$live/privkey.pem" -out "$live/fullchain.pem" \
        -days 90 -subj "/CN=$domain" -addext "subjectAltName=DNS:$domain" >/dev/null 2>&1
}
run() { # reload command
    PUBLIC_DOMAIN=$domain TLS_CERT_DIR=/served LETSENCRYPT_DIR=/le ACME_WEBROOT=/acme TLS_KEY_OWNER=101:101 \
        RELOAD_COMMAND="$1" VERIFY_ENDPOINT="$PROXY:8443" bash /scripts/renew_tls_certificate.sh --install-only
}
new_cert
run "docker exec $PROXY nginx -s reload; sleep 1" >/tmp/ok.log 2>&1 || { echo "FAIL served check after reload: $(cat /tmp/ok.log)"; exit 1; }
grep -q "proxy serves the new certificate" /tmp/ok.log || { echo "FAIL served check did not run"; exit 1; }
echo "ok   reloads the proxy and confirms it serves the installed certificate"
new_cert
if run "true" >/tmp/stale.log 2>&1; then echo "FAIL a proxy still serving the old certificate was accepted"; exit 1; fi
grep -q "does not serve the installed certificate" /tmp/stale.log || { echo "FAIL wrong reason: $(cat /tmp/stale.log)"; exit 1; }
echo "ok   fails when the proxy keeps serving the previous certificate"
SERVED

echo "TLS renewal tests passed."
