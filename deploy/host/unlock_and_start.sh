#!/usr/bin/env bash
# Run after every reboot: unlock the encrypted volume, mount it, start Docker.
# Containers have restart: always, so the stack comes back by itself.
set -euo pipefail
NAME=myvita_data
MOUNT=/srv/myvita-data
[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
DEVICE="$(cat /etc/myvita-data-device 2>/dev/null || true)"
[ -n "$DEVICE" ] || { echo "ERROR: run setup_encrypted_storage.sh first." >&2; exit 1; }

[ -e "/dev/mapper/$NAME" ] || cryptsetup open "$DEVICE" "$NAME"
mountpoint -q "$MOUNT" || mount "/dev/mapper/$NAME" "$MOUNT"
ln -sfn "$MOUNT/letsencrypt" /etc/letsencrypt
systemctl start docker.socket docker.service
sleep 5
docker ps --format 'table {{.Names}}\t{{.Status}}'
echo "If the stack was never started, run: myvita-compose up -d"
