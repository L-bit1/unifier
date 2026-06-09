#!/usr/bin/env bash
# 在每台设备上执行，向 Hub 注册并发送心跳
# 用法: HUB_URL=http://192.168.1.10:8787 ./scripts/register-device.sh mac-home "我的 Mac"

set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
DEVICE_ID="${DEVICE_ID:-$(hostname -s)}"
NAME="${1:-$DEVICE_ID}"
AGENTS="${AGENTS:-cursor,trae}"

IFS=',' read -ra AGENT_ARR <<< "$AGENTS"
AGENTS_JSON=$(printf '"%s",' "${AGENT_ARR[@]}")
AGENTS_JSON="[${AGENTS_JSON%,}]"

curl -sS -X POST "${HUB_URL}/api/v1/devices/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"device_id\": \"${DEVICE_ID}\",
    \"name\": \"${NAME}\",
    \"hostname\": \"$(hostname)\",
    \"os_name\": \"$(uname -s)\",
    \"agents\": ${AGENTS_JSON}
  }" | python3 -m json.tool

echo ""
echo "已注册 device_id=${DEVICE_ID}，Hub=${HUB_URL}"
