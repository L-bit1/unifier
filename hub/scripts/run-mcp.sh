#!/usr/bin/env bash
# 启动联合器 MCP Server（stdio，供 Cursor / Trae 配置）
set -euo pipefail
HUB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${HUB_DIR}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

export PYTHONPATH="${HUB_DIR}:${PYTHONPATH:-}"
export HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
export UNIFIER_DEVICE_ID="${UNIFIER_DEVICE_ID:-${DEVICE_ID:-}}"
export UNIFIER_AGENT_ID="${UNIFIER_AGENT_ID:-${AGENT_ID:-cursor}}"

exec python3 mcp_server/server.py
