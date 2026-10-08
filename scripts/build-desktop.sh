#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/desktop"
npm install
if [[ "${1:-}" == "win" ]]; then
  npm run build:win
else
  npm run build:mac
fi
