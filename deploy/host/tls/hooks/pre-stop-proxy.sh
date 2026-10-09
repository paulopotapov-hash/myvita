#!/usr/bin/env bash
# Free port 80 for certbot --standalone. No-op if the stack is not running.
if command -v myvita-compose >/dev/null && systemctl is-active --quiet docker; then
    myvita-compose stop proxy || true
fi
