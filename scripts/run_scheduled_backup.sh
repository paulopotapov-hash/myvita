#!/usr/bin/env bash
set -euo pipefail

/opt/myvita/backup_db.sh /backups
/opt/myvita/prune_backups.sh /backups
