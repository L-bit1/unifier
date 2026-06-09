#!/usr/bin/env bash
# Cursor/Trae 回复上报到 Hub，并转发飞书群
set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"

if [[ $# -ge 4 ]]; then
  TASK_ID="$1"
  DEVICE_ID="$2"
  AGENT_ID="$3"
  shift 3
  CONTENT="$*"
else
  TASK_ID="${TASK_ID:?请设置 TASK_ID 或使用: submit-agent-reply.sh 1 mac-a cursor \"内容\"}"
  DEVICE_ID="${DEVICE_ID:?请设置 DEVICE_ID}"
  AGENT_ID="${AGENT_ID:-cursor}"
  CONTENT="${1:?请提供回复内容}"
fi

PAYLOAD=$(TASK_ID="$TASK_ID" DEVICE_ID="$DEVICE_ID" AGENT_ID="$AGENT_ID" CONTENT="$CONTENT" python3 -c '
import json, os
print(json.dumps({
    "device_id": os.environ["DEVICE_ID"],
    "agent_id": os.environ["AGENT_ID"],
    "content": os.environ["CONTENT"],
    "source": "agent",
    "notify_feishu": True,
}, ensure_ascii=False))
')

curl -sS -X POST "${HUB_URL}/api/v1/tasks/${TASK_ID}/agent-replies" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" | python3 -m json.tool

echo ""
echo "已上报 task #${TASK_ID} · ${DEVICE_ID}/${AGENT_ID} → 飞书群"
