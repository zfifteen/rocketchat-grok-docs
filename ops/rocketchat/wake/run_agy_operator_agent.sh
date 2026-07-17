#!/usr/bin/env bash
# KeepAlive entry for agy RC operator (parallel to grok/hermes).
set -euo pipefail
export HOME="${HOME:-/Users/velocityworks}"
OPS_RC="$HOME/.grok/agency/ops/rocketchat"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$OPS_RC/.venv/bin/python3" ]]; then
    PYTHON_BIN="$OPS_RC/.venv/bin/python3"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
fi
export PYTHON_BIN
export PATH="$OPS_RC/.venv/bin:$HOME/.local/bin:$HOME/.grok/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# --- identity isolation (REQUIRED unique values) ---
export RC_SECRETS_PATH="${RC_SECRETS_PATH:-$HOME/.grok/agency/secrets/rocketchat-agy.env}"
export RC_LOG_DIR="${RC_LOG_DIR:-$HOME/logs/rocketchat-agy-wake}"
export RC_STATE_PATH="${RC_STATE_PATH:-$OPS_RC/wake/agy_state.json}"
export RC_REPLY_PROMPT="${RC_REPLY_PROMPT:-$OPS_RC/wake/agy_reply_prompt.txt}"

# --- backend ---
export RC_WAKE_BACKEND="agy"

# --- dual-operator tag-to-talk (REQUIRED for shared channels) ---
export RC_REQUIRE_MENTION="${RC_REQUIRE_MENTION:-1}"
export RC_REQUIRE_MENTION_SCOPE="${RC_REQUIRE_MENTION_SCOPE:-channels}"
export RC_PEER_TAG_WAKE="${RC_PEER_TAG_WAKE:-1}"

# --- safety defaults matching production ---
export RC_WAKE_APPROVAL_MODE="${RC_WAKE_APPROVAL_MODE:-restricted}"
export RC_WAKE_ADMIN_DMS_ONLY="${RC_WAKE_ADMIN_DMS_ONLY:-1}"
export RC_WAKE_MAX_TURNS="${RC_WAKE_MAX_TURNS:-100}"
export RC_WAKE_TIMEOUT_S="${RC_WAKE_TIMEOUT_S:-600}"
export RC_WAKE_LOCK_STALE_S="${RC_WAKE_LOCK_STALE_S:-900}"
export RC_AUTO_CREATE_PROJECTS="${RC_AUTO_CREATE_PROJECTS:-1}"
export RC_WAKE_STREAM="${RC_WAKE_STREAM:-0}"
export RC_CONTROL_PLANE="${RC_CONTROL_PLANE:-1}"

mkdir -p "$RC_LOG_DIR"
exec "$PYTHON_BIN" "$OPS_RC/wake/rc_operator_agent.py" \
  >>"$RC_LOG_DIR/operator-agent.stdout.log" 2>>"$RC_LOG_DIR/operator-agent.stderr.log"
