#!/usr/bin/env bash
# 双身份模拟 Cursor + Trae 圆桌冒烟（不依赖 IDE）
set -euo pipefail
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! curl -sf "$HUB_URL/health" >/dev/null; then
  echo "Hub 未启动：请先 cd hub && ./run.sh"
  exit 1
fi

echo "== open room =="
OPEN=$(curl -sf -X POST "$HUB_URL/api/v1/dialogue/rooms" \
  -H 'Content-Type: application/json' \
  -d '{"title":"茅台冒烟","topic":"7/17 零单主因是不是 19:58 online=0？","project_key":"maotai","participants":["cursor","trae"]}')
echo "$OPEN" | python3 -m json.tool
ROOM=$(echo "$OPEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['room']['id'])")

echo "== cursor poll =="
curl -sf "$HUB_URL/api/v1/dialogue/rooms/$ROOM/poll?participant=cursor&since_id=0" | python3 -m json.tool | head -40

echo "== both reply =="
curl -sf -X POST "$HUB_URL/api/v1/dialogue/rooms/$ROOM/reply" \
  -H 'Content-Type: application/json' \
  -d '{"participant":"cursor","body":"同意：心跳与 AutoRush 解耦是 P0，应装 1.9.128 验 online。"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('cursor round_complete=', d.get('round_complete'))"

curl -sf -X POST "$HUB_URL/api/v1/dialogue/rooms/$ROOM/reply" \
  -H 'Content-Type: application/json' \
  -d '{"participant":"trae","body":"补充：窗外 4030 熔断应排在 online 稳住之后。"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('trae round_complete=', d.get('round_complete'))"

echo "== cursor sees peer =="
curl -sf "$HUB_URL/api/v1/dialogue/rooms/$ROOM/poll?participant=cursor&since_id=0" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('hint=', d.get('hint')); print('peers=', [m['participant']+':'+m['body'][:40] for m in d.get('new_peer_messages',[])])"

echo "== end =="
END=$(curl -sf -X POST "$HUB_URL/api/v1/dialogue/rooms/$ROOM/end")
echo "$END" | python3 -m json.tool
echo "✅ smoke-dialogue-maotai OK room=$ROOM"
