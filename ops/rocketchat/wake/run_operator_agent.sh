#!/usr/bin/env bash
# KeepAlive launchd entry: always-on grok presence + DM wake.
set -euo pipefail
export HOME="${HOME:-/Users/velocityworks}"
OPS_RC="$HOME/.grok/agency/ops/rocketchat"
# Prefer ops .venv (livekit/websockets for NF-SPEC-01 voice worker spawns)
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
export GROK_BIN="${GROK_BIN:-$HOME/.local/bin/grok}"
# Multi-operator: shared channels/groups only wake on @grok; DMs free-wake.
# Peer tags (other bots/humans @grok) wake when RC_PEER_TAG_WAKE=1 (default on in code).
export RC_REQUIRE_MENTION="${RC_REQUIRE_MENTION:-1}"
export RC_REQUIRE_MENTION_SCOPE="${RC_REQUIRE_MENTION_SCOPE:-channels}"
export RC_PEER_TAG_WAKE="${RC_PEER_TAG_WAKE:-1}"
LOG_DIR="$HOME/logs/rocketchat-dm-wake"
mkdir -p "$LOG_DIR"
exec "$PYTHON_BIN" "$OPS_RC/wake/rc_operator_agent.py" \
  >>"$LOG_DIR/operator-agent.stdout.log" 2>>"$LOG_DIR/operator-agent.stderr.log"
