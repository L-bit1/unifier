#!/usr/bin/env bash
set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"

json() { python3 -m json.tool; }

echo "== health =="
curl -sS "${HUB_URL}/health" | json

echo "== register devices =="
for id in device-a device-b; do
  curl -sS -X POST "${HUB_URL}/api/v1/devices/register" \
    -H "Content-Type: application/json" \
    -d "{\"device_id\":\"${id}\",\"name\":\"${id}\",\"agents\":[\"cursor\"]}" | json
done

echo "== create project =="
PROJECT=$(curl -sS -X POST "${HUB_URL}/api/v1/projects" \
  -H "Content-Type: application/json" \
  -d '{"github_owner":"demo","github_repo":"unifier-test"}')
echo "$PROJECT" | json
PID=$(echo "$PROJECT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "== create task =="
TASK=$(curl -sS -X POST "${HUB_URL}/api/v1/tasks" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\":${PID},\"title\":\"smoke\",\"branch\":\"feature/smoke\",\"required_reviewers\":[\"agent-2\",\"agent-3\"]}")
echo "$TASK" | json
TID=$(echo "$TASK" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -sS -X POST "${HUB_URL}/api/v1/tasks/${TID}/assign" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"device-a","agent_id":"cursor"}' | json

curl -sS -X POST "${HUB_URL}/api/v1/tasks/${TID}/manifest" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"cursor","device_id":"device-a","payload":{"summary":"smoke test change"}}' | json

curl -sS -X POST "${HUB_URL}/api/v1/tasks/${TID}/submit-review" | json

curl -sS -X POST "${HUB_URL}/api/v1/tasks/${TID}/reviews" \
  -H "Content-Type: application/json" \
  -d '{"reviewer_agent_id":"agent-2","status":"approved"}' | json

curl -sS -X POST "${HUB_URL}/api/v1/tasks/${TID}/reviews" \
  -H "Content-Type: application/json" \
  -d '{"reviewer_agent_id":"agent-3","status":"approved"}' | json

echo "== merge-ready =="
curl -sS "${HUB_URL}/api/v1/tasks/${TID}/merge-ready" | json

echo "== online devices =="
curl -sS "${HUB_URL}/api/v1/devices?online_only=true" | json

echo "smoke test done"
