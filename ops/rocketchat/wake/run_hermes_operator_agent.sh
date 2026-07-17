#!/usr/bin/env bash
# KeepAlive launchd entry: always-on Hermes presence + DM wake (parallel to Grok operator).
set -euo pipefail
export HOME="${HOME:-/Users/velocityworks}"
OPS_RC="$HOME/.grok/agency/ops/rocketchat"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$OPS_RC/.venv/bin/python3" ]]; then
    PYTHON_BIN="$OPS_RC/.venv/bin/python3"
  elif [[ -x /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 ]]; then
    PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
fi
export PYTHON_BIN
export PATH="$OPS_RC/.venv/bin:$HOME/.local/bin:$HOME/.grok/bin:/Library/Frameworks/Python.framework/Versions/3.13/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export HERMES_BIN="${HERMES_BIN:-$HOME/.local/bin/hermes}"
export GROK_BIN="${GROK_BIN:-$HOME/.local/bin/grok}"
export RC_WAKE_BACKEND=hermes
export RC_SECRETS_PATH="${RC_SECRETS_PATH:-$HOME/.grok/agency/secrets/rocketchat-hermes.env}"
export RC_LOG_DIR="${RC_LOG_DIR:-$HOME/logs/rocketchat-hermes-wake}"
export RC_HERMES_PROFILE="${RC_HERMES_PROFILE:-idea}"
export RC_WAKE_STREAM="${RC_WAKE_STREAM:-0}"
# Dual-operator: shared channels/groups only wake on @hermes; DMs free-wake.
export RC_REQUIRE_MENTION="${RC_REQUIRE_MENTION:-1}"
export RC_REQUIRE_MENTION_SCOPE="${RC_REQUIRE_MENTION_SCOPE:-channels}"
mkdir -p "$RC_LOG_DIR"
exec "$PYTHON_BIN" "$OPS_RC/wake/rc_operator_agent.py" \
  >>"$RC_LOG_DIR/operator-agent.stdout.log" 2>>"$RC_LOG_DIR/operator-agent.stderr.log"
