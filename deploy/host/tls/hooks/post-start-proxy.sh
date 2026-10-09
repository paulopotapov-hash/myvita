#!/usr/bin/env bash
# Bring the proxy back after certbot. No-op if the stack was never started.
if command -v myvita-compose >/dev/null && systemctl is-active --quiet docker; then
    if [ -n "$(myvita-compose ps -a -q proxy 2>/dev/null)" ]; then
        myvita-compose start proxy
    fi
fi
