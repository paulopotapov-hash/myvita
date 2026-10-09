#!/usr/bin/env bash
# Issue the first Let's Encrypt certificate and install automatic renewal.
#
# Renewal uses certbot's built-in systemd timer (moved to 04:17 UTC) with
# --standalone: when a renewal is due (~every 60 days) the proxy is stopped
# for ~15-30 s, the certificate is renewed, copied to /srv/myvita-data/tls
# and the proxy restarted. Simple and robust for a single-host pilot.
#
# Usage: sudo ./issue_certificate.sh app.example.pt ops@example.pt [--staging]
# Prerequisite: the DNS A/AAAA record already points at this server.
set -euo pipefail
DOMAIN="${1:?Usage: $0 <domain> <email> [--staging]}"
EMAIL="${2:?Usage: $0 <domain> <email> [--staging]}"
STAGING="${3:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
mountpoint -q /srv/myvita-data || { echo "ERROR: unlock the encrypted volume first." >&2; exit 1; }
[ -L /etc/letsencrypt ] || { echo "ERROR: /etc/letsencrypt must link to the encrypted volume (run setup_encrypted_storage.sh)." >&2; exit 1; }

resolved="$(getent ahosts "$DOMAIN" | awk '{print $1}' | sort -u | tr '\n' ' ')"
echo "DNS for $DOMAIN -> ${resolved:-<none>}"
[ -n "$resolved" ] || { echo "ERROR: $DOMAIN does not resolve yet." >&2; exit 1; }

# Renewal hooks (run only when a renewal is actually attempted).
install -d /etc/letsencrypt/renewal-hooks/pre /etc/letsencrypt/renewal-hooks/deploy /etc/letsencrypt/renewal-hooks/post
install -m 0755 "$HERE/hooks/pre-stop-proxy.sh"   /etc/letsencrypt/renewal-hooks/pre/myvita-stop-proxy.sh
install -m 0755 "$HERE/hooks/deploy-copy-cert.sh" /etc/letsencrypt/renewal-hooks/deploy/myvita-copy-cert.sh
install -m 0755 "$HERE/hooks/post-start-proxy.sh" /etc/letsencrypt/renewal-hooks/post/myvita-start-proxy.sh

# Run renewals at a quiet hour instead of the package default (twice daily, random).
install -d /etc/systemd/system/certbot.timer.d
install -m 0644 "$HERE/certbot.timer.override.conf" /etc/systemd/system/certbot.timer.d/override.conf
systemctl daemon-reload
systemctl enable --now certbot.timer

extra=()
[ "$STAGING" = "--staging" ] && extra+=(--staging)

# Port 80 must be free for the first issuance.
/etc/letsencrypt/renewal-hooks/pre/myvita-stop-proxy.sh || true
set +e
certbot certonly --standalone --non-interactive --agree-tos --no-eff-email \
    --email "$EMAIL" -d "$DOMAIN" --key-type ecdsa "${extra[@]}"
rc=$?
set -e
if [ $rc -eq 0 ]; then
    RENEWED_LINEAGE="/etc/letsencrypt/live/$DOMAIN" /etc/letsencrypt/renewal-hooks/deploy/myvita-copy-cert.sh
fi
/etc/letsencrypt/renewal-hooks/post/myvita-start-proxy.sh || true
[ $rc -eq 0 ] || { echo "ERROR: certbot failed (exit $rc)." >&2; exit $rc; }

echo "Certificate installed in /srv/myvita-data/tls. Test renewal with:"
echo "  sudo certbot renew --dry-run"
