#!/usr/bin/env bash
# Public reverse proxy: ngrok → :9080 → RC(:3000) + voice_room(:8090)
set -euo pipefail
export HOME="${HOME:-/Users/velocityworks}"
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${RC_PUBLIC_PROXY_LOG_DIR:-$HOME/logs/rocketchat-dm-wake}"
mkdir -p "$LOG_DIR"
HOST="${RC_PUBLIC_PROXY_HOST:-127.0.0.1}"
PORT="${RC_PUBLIC_PROXY_PORT:-9080}"
PY="${RC_PUBLIC_PROXY_PYTHON:-}"
if [[ -z "$PY" && -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
fi
if [[ -z "$PY" ]]; then
  PY="$(command -v python3)"
fi
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] starting public proxy :${PORT}" >>"$LOG_DIR/public-proxy.log"
exec "$PY" "$ROOT/public_proxy.py" \
  --host "$HOST" \
  --port "$PORT" \
  >>"$LOG_DIR/public-proxy.log" 2>&1
