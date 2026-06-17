#!/usr/bin/env bash
# 在 Hub 所在机器一键启动：Hub + 飞书消息桥 + 飞书卡片桥
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HUB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${HOME}/.unifier/logs"
mkdir -p "${LOG_DIR}"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/load-env.sh"

cd "${HUB_DIR}"

if lsof -i :"${UNIFIER_PORT:-8787}" >/dev/null 2>&1; then
  echo "Hub 已在端口 ${UNIFIER_PORT:-8787} 运行，跳过启动"
else
  echo "启动 Hub → ${LOG_DIR}/hub.log"
  nohup ./run.sh >"${LOG_DIR}/hub.log" 2>&1 &
  sleep 2
fi

if pgrep -f "scripts/feishu-bridge.py" >/dev/null 2>&1; then
  echo "feishu-bridge 已在运行"
else
  echo "启动 feishu-bridge → ${LOG_DIR}/feishu-bridge.log"
  nohup python3 scripts/feishu-bridge.py >"${LOG_DIR}/feishu-bridge.log" 2>&1 &
fi

if pgrep -f "scripts/feishu-card-bridge.py" >/dev/null 2>&1; then
  echo "feishu-card-bridge 已在运行"
else
  if [[ -z "${FEISHU_APP_ID:-}" || -z "${FEISHU_APP_SECRET:-}" ]]; then
    echo "跳过 feishu-card-bridge（未配置 FEISHU_APP_ID/SECRET）"
  else
    echo "启动 feishu-card-bridge → ${LOG_DIR}/feishu-card-bridge.log"
    nohup .venv/bin/python3 scripts/feishu-card-bridge.py >"${LOG_DIR}/feishu-card-bridge.log" 2>&1 &
  fi
fi

# n8n 自动化（可选：hub/.env 设 N8N_ENABLED=true）
if [[ "${N8N_ENABLED:-false}" == "true" ]]; then
  if docker compose -f "${HUB_DIR}/docker-compose.yml" ps n8n 2>/dev/null | grep -q "running"; then
    echo "n8n 已在运行"
  elif command -v docker >/dev/null 2>&1; then
    echo "启动 n8n → docker compose (端口 ${N8N_PORT:-5678})"
    docker compose -f "${HUB_DIR}/docker-compose.yml" up -d n8n
  else
    echo "跳过 n8n（未安装 docker；可手动运行 n8n 并设 N8N_URL）"
  fi
else
  echo "n8n 未启用（hub/.env 设 N8N_ENABLED=true 可随 Hub 一起启动）"
fi

echo ""
echo "✅ 服务已启动"
echo "  Hub:    http://127.0.0.1:${UNIFIER_PORT:-8787}/docs"
if [[ "${N8N_ENABLED:-false}" == "true" ]]; then
  echo "  n8n:    http://127.0.0.1:${N8N_PORT:-5678}"
fi
echo "  日志:   ${LOG_DIR}/"
echo "  工作站: DEVICE_ID=<你的设备> AGENT_ID=cursor ./scripts/start-workstation.sh"
