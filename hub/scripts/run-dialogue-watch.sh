#!/usr/bin/env bash
# 圆桌自动 poll：同时代 cursor + trae
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
export DIALOGUE_PROJECT_KEY="${DIALOGUE_PROJECT_KEY:-maotai}"
export DIALOGUE_WATCH_AGENTS="${DIALOGUE_WATCH_AGENTS:-cursor,trae}"
export DIALOGUE_WATCH_INTERVAL="${DIALOGUE_WATCH_INTERVAL:-2}"
export DIALOGUE_WATCH_GRACE="${DIALOGUE_WATCH_GRACE:-2}"
export UNIFIER_HOME="${UNIFIER_HOME:-$HOME/.unifier}"
export PYTHONUNBUFFERED=1
mkdir -p "$UNIFIER_HOME/dialogue"
exec python3 -u "$ROOT/scripts/dialogue-watch.py" "$@"
