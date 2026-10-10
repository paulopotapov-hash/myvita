#!/usr/bin/env bash
#
# Obtain or renew the public TLS certificate (Let's Encrypt, HTTP-01 through the
# proxy's ACME webroot), install it for the proxy and reload nginx, then check
# that the proxy actually serves the new certificate. docs/tls-certificates.md.
#
# Run on the production host from the repository root, as root (the private key
# is installed for the proxy's unprivileged user), daily from cron or a systemd
# timer. certbot only renews within 30 days of expiry, so daily runs are cheap.
#
#   PUBLIC_DOMAIN   the approved DNS name (A/AAAA must point at this host)
#   ACME_EMAIL      expiry/revocation contact for the CA account
#   TLS_CERT_DIR    directory mounted at /etc/nginx/tls in the proxy
#   ACME_WEBROOT    shared challenge directory (default /var/lib/myvita/acme)
#   LETSENCRYPT_DIR certbot state, account key and history (default /var/lib/myvita/letsencrypt)
#   CERTBOT_IMAGE   pinned certbot image (default below)
#   COMPOSE_FILES   compose files of the running stack, for the reload
#
# Options:
#   --staging       use the CA's staging environment (untrusted test certificates)
#   --dry-run       test issuance against staging; installs nothing
#   --install-only  skip certbot; (re)install and verify what certbot already produced
#
# Exit codes: 0 installed (or already current), 1 failure. Never prints key material.
set -euo pipefail

staging=() dry_run=false install_only=false
for arg in "$@"; do
    case "$arg" in
        --staging) staging=(--staging) ;;
        --dry-run) dry_run=true ;;
        --install-only) install_only=true ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

: "${PUBLIC_DOMAIN:?Set PUBLIC_DOMAIN}"
: "${TLS_CERT_DIR:?Set TLS_CERT_DIR}"
ACME_WEBROOT="${ACME_WEBROOT:-/var/lib/myvita/acme}"
LETSENCRYPT_DIR="${LETSENCRYPT_DIR:-/var/lib/myvita/letsencrypt}"
CERTBOT_IMAGE="${CERTBOT_IMAGE:-certbot/certbot:v2.11.0}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.prod.yml -f docker-compose.prod-tls.yml}"
# uid:gid of nginx in nginxinc/nginx-unprivileged; empty skips chown (tests only).
TLS_KEY_OWNER="${TLS_KEY_OWNER-101:101}"
RELOAD_COMMAND="${RELOAD_COMMAND:-docker compose ${COMPOSE_FILES} exec -T proxy nginx -s reload}"
VERIFY_ENDPOINT="${VERIFY_ENDPOINT:-127.0.0.1:443}"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) tls-renewal: $*"; }
die() { log "FAILED: $*" >&2; exit 1; }

case "$PUBLIC_DOMAIN" in
    localhost | 127.* | *[!a-zA-Z0-9.-]*) die "PUBLIC_DOMAIN is not a public DNS name" ;;
esac

mkdir -p "$ACME_WEBROOT" "$LETSENCRYPT_DIR" "$TLS_CERT_DIR"
chmod 0755 "$ACME_WEBROOT"

if [ "$install_only" = false ]; then
    : "${ACME_EMAIL:?Set ACME_EMAIL}"
    certbot_args=(certonly --webroot -w /var/www/acme -d "$PUBLIC_DOMAIN" --email "$ACME_EMAIL"
        --agree-tos --no-eff-email --non-interactive --keep-until-expiring "${staging[@]}")
    [ "$dry_run" = false ] || certbot_args+=(--dry-run)
    log "requesting/renewing certificate for ${PUBLIC_DOMAIN} (dry_run=${dry_run})"
    docker run --rm \
        -v "${LETSENCRYPT_DIR}:/etc/letsencrypt" \
        -v "${ACME_WEBROOT}:/var/www/acme" \
        "$CERTBOT_IMAGE" "${certbot_args[@]}" || die "certbot did not obtain/renew the certificate"
    if [ "$dry_run" = true ]; then
        log "dry run succeeded; nothing installed"
        exit 0
    fi
fi

live="${LETSENCRYPT_DIR}/live/${PUBLIC_DOMAIN}"
[ -s "${live}/fullchain.pem" ] && [ -s "${live}/privkey.pem" ] || die "no certificate at ${live}"

# Refuse to install anything that is expired, for another name, or not matching its key.
openssl x509 -in "${live}/fullchain.pem" -noout -checkend 86400 >/dev/null || die "certificate expires within 24h"
openssl x509 -in "${live}/fullchain.pem" -noout -text | grep -o 'DNS:[^,]*' | tr -d ' ' | grep -qxF "DNS:${PUBLIC_DOMAIN}" \
    || die "certificate does not cover ${PUBLIC_DOMAIN}"
cert_key="$(openssl x509 -in "${live}/fullchain.pem" -noout -pubkey | openssl sha256)"
private_key="$(openssl pkey -in "${live}/privkey.pem" -pubout | openssl sha256)"
[ "$cert_key" = "$private_key" ] || die "private key does not match the certificate"

if cmp -s "${live}/fullchain.pem" "${TLS_CERT_DIR}/fullchain.pem" && cmp -s "${live}/privkey.pem" "${TLS_CERT_DIR}/privkey.pem"; then
    log "installed certificate is already current; nothing to do"
    exit 0
fi

# Atomic install: write next to the target, then rename (nginx never sees a half-written file).
install -m 0644 "${live}/fullchain.pem" "${TLS_CERT_DIR}/.fullchain.pem.new"
install -m 0600 "${live}/privkey.pem" "${TLS_CERT_DIR}/.privkey.pem.new"
[ -z "$TLS_KEY_OWNER" ] || chown "$TLS_KEY_OWNER" "${TLS_CERT_DIR}/.privkey.pem.new"
mv -f "${TLS_CERT_DIR}/.privkey.pem.new" "${TLS_CERT_DIR}/privkey.pem"
mv -f "${TLS_CERT_DIR}/.fullchain.pem.new" "${TLS_CERT_DIR}/fullchain.pem"
log "installed new certificate (expires $(openssl x509 -in "${TLS_CERT_DIR}/fullchain.pem" -noout -enddate | cut -d= -f2))"

eval "$RELOAD_COMMAND" || die "proxy reload failed; the previous certificate may still be served"

if [ "${SKIP_SERVED_CHECK:-false}" != true ]; then
    expected="$(openssl x509 -in "${TLS_CERT_DIR}/fullchain.pem" -noout -fingerprint -sha256)"
    served="$(echo | openssl s_client -connect "$VERIFY_ENDPOINT" -servername "$PUBLIC_DOMAIN" 2>/dev/null \
        | openssl x509 -noout -fingerprint -sha256 2>/dev/null || true)"
    [ "$served" = "$expected" ] || die "the proxy does not serve the installed certificate (check the TLS overlay)"
    log "proxy serves the new certificate"
fi
