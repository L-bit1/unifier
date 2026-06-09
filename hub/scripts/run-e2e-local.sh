#!/usr/bin/env bash
# 本地一键：启动 Hub + 跑四端 e2e
set -euo pipefail
HUB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
LOG="${HUB_DIR}/data/hub-e2e.log"
PIDFILE="${HUB_DIR}/data/hub.pid"

mkdir -p "${HUB_DIR}/data"

if curl -sS "${HUB_URL}/health" >/dev/null 2>&1; then
  echo "Hub 已在运行: ${HUB_URL}"
else
  echo "启动 Hub..."
  cd "${HUB_DIR}"
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -r requirements.txt
  export PYTHONPATH=.
  nohup uvicorn app.main:app --host 0.0.0.0 --port "${UNIFIER_PORT:-8787}" \
    >"${LOG}" 2>&1 &
  echo $! >"${PIDFILE}"
  echo "Hub pid=$(cat "${PIDFILE}") log=${LOG}"
  sleep 2
fi

chmod +x "${HUB_DIR}/scripts/"*.sh "${HUB_DIR}/scripts/"*.py 2>/dev/null || true
"${HUB_DIR}/scripts/e2e-four-agents.sh"
