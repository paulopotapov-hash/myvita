#!/usr/bin/env bash
# One-time: format an attached block volume with LUKS2 and mount it at
# /srv/myvita-data. Everything with patient data lives there: Docker data-root
# (PostgreSQL, documents, local backups, Prometheus), secrets and TLS keys.
#
# Hetzner Cloud volumes are not encrypted by the provider, so encryption at
# rest is done here. Trade-off: after every reboot an operator must run
# unlock_and_start.sh and type the passphrase. Store the passphrase in the
# team's password manager; losing it means losing the data (restore from
# off-site backup).
#
# Usage: sudo ./setup_encrypted_storage.sh /dev/disk/by-id/scsi-0HC_Volume_<id>
set -euo pipefail
DEVICE="${1:?Usage: $0 /dev/disk/by-id/<volume>}"
NAME=myvita_data
MOUNT=/srv/myvita-data

[ "$(id -u)" = 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
[ -b "$DEVICE" ] || { echo "ERROR: $DEVICE is not a block device." >&2; exit 1; }
if findmnt -S "$DEVICE" >/dev/null 2>&1; then
    echo "ERROR: $DEVICE is mounted (Hetzner auto-mount?). Unmount it and remove its /etc/fstab line first." >&2
    exit 1
fi
if mountpoint -q "$MOUNT"; then echo "ERROR: $MOUNT already mounted." >&2; exit 1; fi
if systemctl is-active --quiet docker; then echo "ERROR: stop Docker first." >&2; exit 1; fi

echo "This ERASES everything on $DEVICE."
read -r -p "Type ERASE to continue: " answer
[ "$answer" = ERASE ] || { echo "Aborted."; exit 1; }

cryptsetup luksFormat --type luks2 --pbkdf argon2id "$DEVICE"
cryptsetup open "$DEVICE" "$NAME"
mkfs.ext4 -L myvita-data "/dev/mapper/$NAME"
mkdir -p "$MOUNT"
mount "/dev/mapper/$NAME" "$MOUNT"
chmod 0700 "$MOUNT"

install -d -m 0755 "$MOUNT/docker"
install -d -m 0700 -o myvita-ops -g myvita-ops "$MOUNT/config"
install -d -m 0750 -o 101 -g 101 "$MOUNT/tls"
install -d -m 0700 "$MOUNT/letsencrypt"

# certbot keeps keys/config on the encrypted volume.
if [ -e /etc/letsencrypt ] && [ ! -L /etc/letsencrypt ]; then
    cp -a /etc/letsencrypt/. "$MOUNT/letsencrypt/" 2>/dev/null || true
    rm -rf /etc/letsencrypt
fi
ln -sfn "$MOUNT/letsencrypt" /etc/letsencrypt

echo "$DEVICE" > /etc/myvita-data-device
echo
echo "Done. Volume UUID: $(cryptsetup luksUUID "$DEVICE")"
echo "Next: put .env.production in $MOUNT/config/ (chmod 600), then run unlock_and_start.sh."
echo "Save a LUKS header backup off the server:"
echo "  sudo cryptsetup luksHeaderBackup $DEVICE --header-backup-file myvita-luks-header.img"
