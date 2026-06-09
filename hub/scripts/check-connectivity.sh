#!/usr/bin/env bash
# 检查 Hub 可达性 + 各设备在线联通性
# 用法:
#   ./scripts/check-connectivity.sh
#   EXPECTED=mac-a,win-pc DEVICE_ID=mac-a ./scripts/check-connectivity.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/load-env.sh"

HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
EXPECTED="${EXPECTED:-${UNIFIER_EXPECTED_DEVICES:-}}"
DEVICE_ID="${DEVICE_ID:-}"
STRICT="${STRICT:-1}"

fail() {
  echo "❌ $*" >&2
  exit 1
}

echo "== Hub 健康检查 =="
if ! HEALTH=$(curl -sS --connect-timeout 5 "${HUB_URL}/health"); then
  fail "无法连接 Hub: ${HUB_URL}"
fi
echo "$HEALTH" | python3 -m json.tool

if [[ -n "${DEVICE_ID}" ]]; then
  echo ""
  echo "== 本机心跳 (${DEVICE_ID}) =="
  if curl -sS --connect-timeout 5 -X POST "${HUB_URL}/api/v1/devices/${DEVICE_ID}/heartbeat" >/dev/null; then
    echo "heartbeat ok · device_id=${DEVICE_ID}"
  else
    echo "⚠️  心跳失败（设备可能未注册）"
  fi
fi

echo ""
echo "== 设备联通性 =="
QUERY="expected=${EXPECTED}"
REPORT=$(curl -sS --connect-timeout 5 "${HUB_URL}/api/v1/devices/connectivity?${QUERY}")
echo "$REPORT" | python3 -m json.tool

READY=$(echo "$REPORT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ready_for_dispatch', False))")
MSG=$(echo "$REPORT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message',''))")

echo ""
echo "$MSG"
if [[ "${STRICT}" == "1" && "${READY}" != "True" && "${READY}" != "true" ]]; then
  fail "期望设备未全部在线（ready_for_dispatch=false）"
fi
echo "✅ 联通性检查完成"
