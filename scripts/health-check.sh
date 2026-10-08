#!/usr/bin/env bash
# 联合器零信任自检：依赖、端口、配置、Hub 连通
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export HUB_URL="${HUB_URL:-http://127.0.0.1:8787}"
cd "${REPO_ROOT}/hub"
if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
exec python3 scripts/unifier-doctor.py
