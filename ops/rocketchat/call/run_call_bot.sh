#!/usr/bin/env bash
# Launch Path C media bot (join Jitsi as grok + speaking loop).
set -euo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
export PYTHON_BIN="${PYTHON_BIN:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3}"
LOG_DIR="$HOME/logs/rocketchat-dm-wake"
mkdir -p "$LOG_DIR"
exec "$PYTHON_BIN" "$HOME/.grok/agency/ops/rocketchat/call/rc_call_bot.py" "$@" \
  >>"$LOG_DIR/call-bot.stdout.log" 2>>"$LOG_DIR/call-bot.stderr.log"
