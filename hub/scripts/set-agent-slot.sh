#!/usr/bin/env bash
# 选配：控制某台设备的 cursor/trae 是否参与执行/审查
# 用法:
#   ./scripts/set-agent-slot.sh win-pc trae off
#   ./scripts/set-agent-slot.sh mac-a cursor on
#   ./scripts/set-agent-slot.sh win-pc cursor review off
#   ./scripts/set-agent-slot.sh list
set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"

if [[ "${1:-}" == "list" || "${1:-}" == "ls" ]]; then
  curl -sS "${HUB_URL}/api/v1/agent-slots" | python3 -m json.tool
  exit 0
fi

DEVICE_ID="${1:?用法: set-agent-slot.sh <device> <cursor|trae> on|off [implement|review]}"
AGENT_ID="${2:?}"
ACTION="${3:?on|off}"
SCOPE="${4:-all}"

PAYLOAD='{}'
case "${SCOPE}:${ACTION}" in
  all:on)  PAYLOAD='{"enabled":true,"can_implement":true,"can_review":true}' ;;
  all:off) PAYLOAD='{"enabled":false}' ;;
  implement:on)  PAYLOAD='{"enabled":true,"can_implement":true}' ;;
  implement:off) PAYLOAD='{"enabled":true,"can_implement":false}' ;;
  review:on)  PAYLOAD='{"enabled":true,"can_review":true}' ;;
  review:off) PAYLOAD='{"enabled":true,"can_review":false}' ;;
  *) echo "scope 应为 all|implement|review" >&2; exit 1 ;;
esac

curl -sS -X PATCH "${HUB_URL}/api/v1/agent-slots/${DEVICE_ID}/${AGENT_ID}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" | python3 -m json.tool
