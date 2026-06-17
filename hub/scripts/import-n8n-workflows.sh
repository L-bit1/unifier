#!/usr/bin/env bash
# 将 hub/workflows/*.json 导入本机 n8n（需 n8n 已启动且配置 N8N_API_KEY）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HUB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WF_DIR="${HUB_DIR}/workflows"

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/load-env.sh"

N8N_BASE="${N8N_URL:-http://127.0.0.1:5678}"
API_KEY="${N8N_API_KEY:-}"

if [[ -z "${API_KEY}" ]]; then
  echo "请先在 hub/.env 设置 N8N_API_KEY（n8n 设置 → API）"
  echo "或手动在 n8n 面板导入: ${WF_DIR}/unifier-events.json"
  exit 1
fi

for f in "${WF_DIR}"/*.json; do
  [[ -f "$f" ]] || continue
  name="$(basename "$f")"
  echo "→ 导入 ${name}"
  curl -sS -X POST "${N8N_BASE}/api/v1/workflows" \
    -H "Content-Type: application/json" \
    -H "X-N8N-API-KEY: ${API_KEY}" \
    -d @"${f}" | python3 -m json.tool
  echo ""
done

echo "✅ 工作流已导入。请在 n8n 面板激活「联合器 · 事件接收」。"
