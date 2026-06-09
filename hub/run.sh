#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# 加载 hub/.env + ../config/local.env
# shellcheck disable=SC1091
source scripts/load-env.sh

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

export PYTHONPATH=.
exec uvicorn app.main:app --host "${UNIFIER_HOST:-0.0.0.0}" --port "${UNIFIER_PORT:-8787}" --reload
