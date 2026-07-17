#!/usr/bin/env bash
# Spawn wrapper for LiveKit + Grok Voice Agent worker (NF-SPEC-01).
set -euo pipefail
HOME="${HOME:-$(eval echo ~)}"
OPS_RC="$HOME/.grok/agency/ops/rocketchat"
# Prefer ops .venv so `import livekit` works (not Frameworks python3 alone)
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$OPS_RC/.venv/bin/python3" ]]; then
    PYTHON_BIN="$OPS_RC/.venv/bin/python3"
  elif [[ -x /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 ]]; then
    PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
fi
export PATH="$OPS_RC/.venv/bin:${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
exec "$PYTHON_BIN" "$OPS_RC/call/voice_agent_worker.py" "$@"