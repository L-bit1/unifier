#!/usr/bin/env bash
# 单机模拟四端（Win Cursor/Trae + Mac Cursor/Trae）全流程
set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HUB_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

json() { python3 -m json.tool; }

wait_hub() {
  for _ in $(seq 1 30); do
    if curl -sS "${HUB_URL}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Hub 未就绪: ${HUB_URL}" >&2
  exit 1
}

echo "== 等待 Hub =="
wait_hub

echo "== 注册两台设备（四 Agent） =="
register() {
  local id="$1" name="$2" os="$3"
  curl -sS -X POST "${HUB_URL}/api/v1/devices/register" \
    -H "Content-Type: application/json" \
    -d "{\"device_id\":\"${id}\",\"name\":\"${name}\",\"os_name\":\"${os}\",\"agents\":[\"cursor\",\"trae\"]}" >/dev/null
}
register mac-a "Mac 主力机" Darwin
register win-pc "Windows 副机" Windows

echo "== 模拟手机下达命令 =="
DISPATCH=$(curl -sS -X POST "${HUB_URL}/api/v1/orchestrate/dispatch" \
  -H "Content-Type: application/json" \
  -d '{
    "github_owner": "demo-org",
    "github_repo": "unifier-demo",
    "title": "四端联调示例任务",
    "description": "e2e-four-agents 自动测试",
    "branch": "feature/e2e-four-agents",
    "implementer_device_id": "mac-a",
    "implementer_agent_id": "cursor",
    "required_reviewers": ["win-pc:cursor", "win-pc:trae", "mac-a:trae"]
  }')
echo "$DISPATCH" | json
TID=$(echo "$DISPATCH" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")

echo "== 启动 4 个 Device Agent（demo 自动模式，各跑一轮） =="
agents=(
  "mac-a cursor"
  "mac-a trae"
  "win-pc cursor"
  "win-pc trae"
)
for pair in "${agents[@]}"; do
  read -r dev ag <<< "$pair"
  python3 "${SCRIPT_DIR}/device-agent.py" \
    --hub "${HUB_URL}" \
    --device-id "${dev}" \
    --agent-id "${ag}" \
    --demo-auto \
    --once
done

echo "== 手机端反馈（轮询状态） =="
curl -sS "${HUB_URL}/api/v1/orchestrate/tasks/${TID}/status" | json

echo "== merge-ready =="
curl -sS "${HUB_URL}/api/v1/tasks/${TID}/merge-ready" | json

MR=$(curl -sS "${HUB_URL}/api/v1/tasks/${TID}/merge-ready")
READY=$(echo "$MR" | python3 -c "import sys,json; print(json.load(sys.stdin)['merge_ready'])")
if [[ "$READY" != "True" && "$READY" != "true" ]]; then
  echo "e2e 失败: merge_ready=false" >&2
  exit 1
fi

echo ""
echo "✅ 四端流程跑通 · task #${TID} · 可去 GitHub merge 分支 feature/e2e-four-agents"
