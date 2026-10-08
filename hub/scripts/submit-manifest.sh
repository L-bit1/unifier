#!/usr/bin/env bash
# 执行者提交 ChangeManifest（含意图记忆字段）
# 用法:
#   TASK_ID=1 INTENT="修复登录超时" COT="用户报5s超时，改为10s" ./scripts/submit-manifest.sh "调整 nginx upstream"
set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
TASK_ID="${TASK_ID:?请设置 TASK_ID}"
DEVICE_ID="${DEVICE_ID:?请设置 DEVICE_ID}"
AGENT_ID="${AGENT_ID:-cursor}"
SUMMARY="${1:-完成改动}"
INTENT="${INTENT:-}"
COT="${COT:-${COT_SUMMARY:-}}"
FEISHU_MSG="${FEISHU_MESSAGE_ID:-}"
export SUMMARY INTENT COT FEISHU_MSG

python3 - <<PY
import json
import os
import urllib.request

body = {
    "agent_id": os.environ["AGENT_ID"],
    "device_id": os.environ["DEVICE_ID"],
    "payload": {"summary": os.environ.get("SUMMARY", "完成改动"), "files": []},
}
intent = os.environ.get("INTENT", "").strip()
cot = os.environ.get("COT", "").strip()
msg = os.environ.get("FEISHU_MSG", "").strip()
if intent:
    body["intent"] = intent
if cot:
    body["cot_summary"] = cot
if msg:
    body["feishu_message_id"] = msg

url = f"{os.environ['HUB_URL']}/api/v1/tasks/{os.environ['TASK_ID']}/manifest"
req = urllib.request.Request(
    url,
    data=json.dumps(body, ensure_ascii=False).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    print(json.dumps(json.load(resp), ensure_ascii=False, indent=2))
PY

echo ""
echo "审计检索: curl '${HUB_URL}/api/v1/audit/manifests?q=关键词'"
echo "下一步: curl -X POST ${HUB_URL}/api/v1/tasks/${TASK_ID}/submit-review"
