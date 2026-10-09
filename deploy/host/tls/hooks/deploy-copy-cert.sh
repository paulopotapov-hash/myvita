#!/usr/bin/env bash
# Copy the renewed certificate where the unprivileged nginx (uid 101) can read it.
set -euo pipefail
: "${RENEWED_LINEAGE:?certbot sets RENEWED_LINEAGE}"
DEST=/srv/myvita-data/tls
install -d -m 0750 -o 101 -g 101 "$DEST"
install -m 0444 -o 101 -g 101 "$RENEWED_LINEAGE/fullchain.pem" "$DEST/fullchain.pem.new"
install -m 0400 -o 101 -g 101 "$RENEWED_LINEAGE/privkey.pem"   "$DEST/privkey.pem.new"
mv -f "$DEST/fullchain.pem.new" "$DEST/fullchain.pem"
mv -f "$DEST/privkey.pem.new"   "$DEST/privkey.pem"
logger -t myvita-tls "certificate updated from $RENEWED_LINEAGE"
