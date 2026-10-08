#!/usr/bin/env bash
# 手机遥控闭环：常驻轮询 Hub 收件箱 → HANDOFF / 唤醒 / 可选飞书 ack
# 用法：
#   HUB_URL=http://127.0.0.1:8787 DEVICE_ID=mac-a ./scripts/run-inbox-auto.sh
#   INBOX_AUTO_AGENTS=cursor,dsh ./scripts/run-inbox-auto.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
[[ -f "${SCRIPT_DIR}/load-env.sh" ]] && source "${SCRIPT_DIR}/load-env.sh" || true

HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
DEVICE_ID="${DEVICE_ID:-${UNIFIER_DEVICE_ID:-$(hostname -s)}}"
AGENTS="${INBOX_AUTO_AGENTS:-cursor,trae,dsh}"
INTERVAL="${INBOX_AUTO_INTERVAL:-8}"
HOME_DIR="${UNIFIER_HOME:-$HOME/.unifier}"

mkdir -p "${HOME_DIR}"

echo "==> Inbox Auto-Runner"
echo "    hub=${HUB_URL}"
echo "    device=${DEVICE_ID}"
echo "    agents=${AGENTS}"
echo "    （手机飞书派活 → 本机收件 → 干完回飞书）"

if ! curl -sf "${HUB_URL}/health" >/dev/null 2>&1; then
  echo "WARN: Hub 不可达 ${HUB_URL} — 请先启动 Hub" >&2
fi

# 确保设备已注册（忽略已存在）
"${SCRIPT_DIR}/register-device.sh" "${DEVICE_ID}" 2>/dev/null || true

exec python3 "${SCRIPT_DIR}/inbox-auto-runner.py" \
  --hub "${HUB_URL}" \
  --device-id "${DEVICE_ID}" \
  --agents "${AGENTS}" \
  --home "${HOME_DIR}" \
  --interval "${INTERVAL}"
