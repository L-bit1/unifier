#!/usr/bin/env bash
# 模拟手机飞书下达命令
# 用法: ./scripts/dispatch-command.sh "任务标题" [branch]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/load-env.sh"

HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
GITHUB_OWNER="${GITHUB_OWNER:-${FEISHU_DEFAULT_GITHUB_OWNER:-your-org}}"
GITHUB_REPO="${GITHUB_REPO:-${FEISHU_DEFAULT_GITHUB_REPO:-your-repo}}"
IMPLEMENTER_DEVICE="${IMPLEMENTER_DEVICE:-${FEISHU_DEFAULT_IMPLEMENTER_DEVICE:-${UNIFIER_DEVICE_ID:-device-a}}}"
IMPLEMENTER_AGENT="${IMPLEMENTER_AGENT:-${FEISHU_DEFAULT_IMPLEMENTER_AGENT:-cursor}}"
EXPECTED="${EXPECTED:-${UNIFIER_EXPECTED_DEVICES:-}}"
REQUIRE_CONNECTIVITY="${REQUIRE_CONNECTIVITY:-0}"
TITLE="${1:?用法: dispatch-command.sh \"任务标题\" [branch]}"
BRANCH="${2:-feature/$(date +%Y%m%d-%H%M)}"

if [[ -n "${EXPECTED}" ]]; then
  echo "== 派活前联通性检查 =="
  STRICT=0 EXPECTED="${EXPECTED}" "${SCRIPT_DIR}/check-connectivity.sh" || true
  REQUIRE_CONNECTIVITY="${REQUIRE_CONNECTIVITY:-1}"
fi

REVIEWERS_RAW="${FEISHU_DEFAULT_REVIEWERS:-}"
export REVIEWERS_RAW
REVIEWERS_JSON=$(python3 -c "
import json, os
raw = os.environ.get('REVIEWERS_RAW', '')
items = [x.strip() for x in raw.split(',') if x.strip()]
print(json.dumps(items))
")
export EXPECTED
REQUIRE_JSON="false"
if [[ "${REQUIRE_CONNECTIVITY}" == "1" ]]; then
  REQUIRE_JSON="true"
fi
EXPECTED_JSON=$(python3 -c "import json, os; print(json.dumps([x.strip() for x in os.environ.get('EXPECTED','').split(',') if x.strip()]))")

RESP=$(curl -sS -X POST "${HUB_URL}/api/v1/orchestrate/dispatch" \
  -H "Content-Type: application/json" \
  -d "{
    \"github_owner\": \"${GITHUB_OWNER}\",
    \"github_repo\": \"${GITHUB_REPO}\",
    \"title\": \"${TITLE}\",
    \"description\": \"来自 dispatch-command（模拟飞书指令）\",
    \"branch\": \"${BRANCH}\",
    \"implementer_device_id\": \"${IMPLEMENTER_DEVICE}\",
    \"implementer_agent_id\": \"${IMPLEMENTER_AGENT}\",
    \"required_reviewers\": ${REVIEWERS_JSON},
    \"require_connectivity\": ${REQUIRE_JSON},
    \"expected_devices\": ${EXPECTED_JSON}
  }")

echo "$RESP" | python3 -m json.tool
TASK_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
echo ""
echo "任务已创建: #${TASK_ID}"
echo "手机轮询状态: curl -s ${HUB_URL}/api/v1/orchestrate/tasks/${TASK_ID}/status | python3 -m json.tool"
