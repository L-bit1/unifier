#!/usr/bin/env bash
# Optional hook: open latest HANDOFF in default editor when inbox arrives.
# Set: export UNIFIER_ON_INBOX_HOOK="$PWD/hub/scripts/hooks/open-handoff.sh"
set -euo pipefail
if [[ -n "${UNIFIER_HANDOFF:-}" && -f "${UNIFIER_HANDOFF}" ]]; then
  echo "[open-handoff] ${UNIFIER_HANDOFF}"
  if command -v open >/dev/null 2>&1; then
    open "${UNIFIER_HANDOFF}"
  else
    ${EDITOR:-nano} "${UNIFIER_HANDOFF}"
  fi
fi
