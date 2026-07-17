#!/usr/bin/env bash
# IMP-18: poll path quarantined — refuse unless RC_POLL_ENABLED=1
set -euo pipefail
if [[ "${RC_POLL_ENABLED:-0}" != "1" ]]; then
  echo "rc_dm_poll disabled (IMP-18). Set RC_POLL_ENABLED=1 only if operator is stopped." >&2
  exit 0
fi
# Launchd entry: one poll cycle for principal → grok DMs.
set -euo pipefail

export HOME="${HOME:-/Users/velocityworks}"
export PATH="$HOME/.local/bin:$HOME/.grok/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export GROK_BIN="${GROK_BIN:-$HOME/.local/bin/grok}"

PYTHON_BIN="${PYTHON_BIN:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

POLL="$HOME/.grok/agency/ops/rocketchat/wake/rc_dm_poll.py"
LOG_DIR="$HOME/logs/rocketchat-dm-wake"
mkdir -p "$LOG_DIR"

exec "$PYTHON_BIN" "$POLL" --once >>"$LOG_DIR/launchd.stdout.log" 2>>"$LOG_DIR/launchd.stderr.log"
