#!/usr/bin/env bash
# Trae / 备用：后台监听 transcript 并自动推送 AI 回复到飞书
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${HOME}/.unifier/auto-reply-push.log"
mkdir -p "${HOME}/.unifier"

export HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
export UNIFIER_DEVICE_ID="${UNIFIER_DEVICE_ID:-${DEVICE_ID:-}}"
export UNIFIER_AGENT_ID="${UNIFIER_AGENT_ID:-${AGENT_ID:-cursor}}"
export UNIFIER_AUTO_PUSH="${UNIFIER_AUTO_PUSH:-1}"

nohup python3 "${SCRIPT_DIR}/reply-auto-push.py" --interval 8 \
  >>"${LOG}" 2>&1 &
echo "auto-reply-push pid=$! log=${LOG}"
