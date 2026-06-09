#!/usr/bin/env bash
# 审查者投票
# 用法: TASK_ID=1 REVIEWER_ID=win-pc:cursor ./scripts/submit-review-vote.sh [approved|changes_requested]
set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
TASK_ID="${TASK_ID:?请设置 TASK_ID}"
REVIEWER_ID="${REVIEWER_ID:?请设置 REVIEWER_ID（如 win-pc:cursor）}"
STATUS="${1:-approved}"

curl -sS -X POST "${HUB_URL}/api/v1/tasks/${TASK_ID}/reviews" \
  -H "Content-Type: application/json" \
  -d "{
    \"reviewer_agent_id\": \"${REVIEWER_ID}\",
    \"status\": \"${STATUS}\"
  }" | python3 -m json.tool
