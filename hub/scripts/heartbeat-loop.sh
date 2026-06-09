#!/usr/bin/env bash
# 后台保持设备在线（每 30 秒心跳）
set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
DEVICE_ID="${DEVICE_ID:-$(hostname -s)}"
INTERVAL="${INTERVAL:-30}"

while true; do
  curl -sS -X POST "${HUB_URL}/api/v1/devices/${DEVICE_ID}/heartbeat" >/dev/null \
    && echo "$(date -Iseconds) heartbeat ok" \
    || echo "$(date -Iseconds) heartbeat failed"
  sleep "$INTERVAL"
done
