#!/usr/bin/env bash
# 决策项验收冒烟：Hub 健康 + 关键 API + 向量检索 + OA + executors
set -euo pipefail
HUB="${HUB_URL:-http://127.0.0.1:8787}"
echo "== Hub health =="
curl -sf "$HUB/health" | head -c 200
echo
echo "== executors (含 continue/opencode) =="
curl -sf "$HUB/api/v1/executors" | python3 -c "import sys,json; d=json.load(sys.stdin); print([e['name'] for e in d.get('executors',[])])"
echo "== OA skeleton =="
curl -sf "$HUB/api/v1/feishu/oa/status" | python3 -c "import sys,json; print(json.load(sys.stdin).get('implemented'))"
echo "== audit search (vector-lite) =="
curl -sf "$HUB/api/v1/audit/manifests?q=login&limit=3" | python3 -c "import sys,json; d=json.load(sys.stdin); print('count', d.get('count', len(d.get('items',[]))))"
echo "== mobile updates =="
curl -sf "$HUB/api/v1/mobile/updates?session_id=default&since_id=0" | python3 -c "import sys,json; print('ok', json.load(sys.stdin).get('count'))"
echo "== exec-confirm pending =="
curl -sf "$HUB/api/v1/mobile/exec-confirm/pending" | python3 -c "import sys,json; print('pending', len(json.load(sys.stdin).get('items',[])))"
echo "✅ e2e-decision-smoke 通过（API 层）"
echo "真机闭环仍需：App 派活 → 确认执行 → Cursor 回传"
