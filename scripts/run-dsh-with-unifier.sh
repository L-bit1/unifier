#!/usr/bin/env bash
# Start DeepSeek Harness Web UI with Unifier plugin (for mobile via Feishu + optional Tailscale).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$ROOT/integrations/dsh-plugin"
PATCH="$PLUGIN_DIR/unifier.cordis.yml"

export UNIFIER_HUB_URL="${UNIFIER_HUB_URL:-${HUB_URL:-http://127.0.0.1:8787}}"
export UNIFIER_DEVICE_ID="${UNIFIER_DEVICE_ID:-${DEVICE_ID:-mac-a}}"
export UNIFIER_AGENT_ID="${UNIFIER_AGENT_ID:-dsh}"

echo "==> Unifier Hub expected at $UNIFIER_HUB_URL"
if ! curl -sf "${UNIFIER_HUB_URL}/health" >/dev/null 2>&1; then
  echo "WARN: Hub not reachable. Start: cd $ROOT/hub && ./scripts/run-hub.sh (or your usual)" >&2
fi

node "$PLUGIN_DIR/scripts/print-cordis-patch.mjs" >/dev/null

# Optional: Tailscale hostname for phone browser (see integrations/dsh-plugin/MOBILE.md)
TRUSTED=()
if [[ -n "${DSH_TRUSTED_HOST:-}" ]]; then
  TRUSTED+=(--trusted-host "$DSH_TRUSTED_HOST")
fi

echo "==> patch: $PATCH"
echo "==> Mobile: Feishu 派活 → Hub; DSH uses unifier_* tools; replies → Feishu on phone"
echo "==> Direct DSH UI on phone: set DSH_TRUSTED_HOST=your.tailnet.ts.net + tailscale serve (see MOBILE.md)"

if command -v pnpm >/dev/null && [[ -n "${DSH_SOURCE_ROOT:-}" && -d "$DSH_SOURCE_ROOT" ]]; then
  cd "$DSH_SOURCE_ROOT"
  exec pnpm dsh web --patch "$PATCH" "${TRUSTED[@]}"
fi

if command -v npx >/dev/null; then
  exec npx @deepseek-ai/dsh@latest web --patch "$PATCH" "${TRUSTED[@]}"
fi

echo "Install Node.js 20+ and run: npx @deepseek-ai/dsh web --patch $PATCH" >&2
exit 1
