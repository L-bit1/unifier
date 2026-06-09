#!/usr/bin/env bash
# 在一台工作站上启动：注册 + 心跳 + Device Agent
# 用法:
#   HUB_URL=http://192.168.1.10:8787 DEVICE_ID=mac-a AGENT_ID=cursor ./scripts/start-workstation.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
DEVICE_ID="${DEVICE_ID:-$(hostname -s)}"
AGENT_ID="${AGENT_ID:-cursor}"
NAME="${WORKSTATION_NAME:-$DEVICE_ID}"

"${SCRIPT_DIR}/register-device.sh" "${NAME}"

echo "启动心跳（后台）..."
nohup env HUB_URL="${HUB_URL}" DEVICE_ID="${DEVICE_ID}" \
  "${SCRIPT_DIR}/heartbeat-loop.sh" >"${HOME}/.unifier/heartbeat-${DEVICE_ID}.log" 2>&1 &
echo "heartbeat pid=$! log=${HOME}/.unifier/heartbeat-${DEVICE_ID}.log"

echo "启动 Device Agent（前台，Ctrl+C 停止）..."
exec python3 "${SCRIPT_DIR}/device-agent.py" \
  --hub "${HUB_URL}" \
  --device-id "${DEVICE_ID}" \
  --agent-id "${AGENT_ID}"
