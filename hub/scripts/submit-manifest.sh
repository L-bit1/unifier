#!/usr/bin/env bash
# 执行者提交 ChangeManifest
# 用法: TASK_ID=1 ./scripts/submit-manifest.sh [summary]
set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
TASK_ID="${TASK_ID:?请设置 TASK_ID}"
DEVICE_ID="${DEVICE_ID:?请设置 DEVICE_ID}"
AGENT_ID="${AGENT_ID:-cursor}"
SUMMARY="${1:-完成改动}"

curl -sS -X POST "${HUB_URL}/api/v1/tasks/${TASK_ID}/manifest" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_id\": \"${AGENT_ID}\",
    \"device_id\": \"${DEVICE_ID}\",
    \"payload\": {
      \"summary\": \"${SUMMARY}\",
      \"files\": [],
      \"timestamp\": \"$(date -Iseconds)\"
    }
  }" | python3 -m json.tool

echo ""
echo "下一步: curl -X POST ${HUB_URL}/api/v1/tasks/${TASK_ID}/submit-review"
