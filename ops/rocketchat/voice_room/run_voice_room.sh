#!/usr/bin/env bash
# Lobby-free voice room for RC Call (VideoConf URL target).
# macOS-safe single instance (no util-linux flock): mkdir lock + orphan takeover.
set -euo pipefail
export HOME="${HOME:-/Users/velocityworks}"
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${RC_VOICE_ROOM_LOG_DIR:-$HOME/logs/rocketchat-dm-wake}"
mkdir -p "$LOG_DIR"
cd "$DIR"

HOST="${RC_VOICE_ROOM_HOST:-127.0.0.1}"
PORT="${RC_VOICE_ROOM_PORT:-8090}"
HEALTH_URL="http://127.0.0.1:${PORT}/health"
LOCKDIR="${LOG_DIR}/voice-room.lockdir"
PIDFILE="${LOG_DIR}/voice-room.pid"

PY="${RC_VOICE_ROOM_PYTHON:-}"
if [[ -z "$PY" && -x "$DIR/../.venv/bin/python" ]]; then
  PY="$DIR/../.venv/bin/python"
fi
if [[ -z "$PY" ]]; then
  PY="$(command -v python3)"
fi

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >>"$LOG_DIR/voice-room.log"; }

healthy() {
  curl -sf --max-time 2 "$HEALTH_URL" >/dev/null 2>&1
}

listener_pids() {
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null \
    | awk 'NR>1 {print $2}' \
    | sort -u
}

is_our_server_pid() {
  local pid="$1"
  [[ -n "$pid" ]] || return 1
  local cmd
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$cmd" == *voice_room/server.py* ]] || [[ "$cmd" == *server.py* && "$cmd" == *8090* ]]
}

kill_our_listeners() {
  local pid
  for pid in $(listener_pids); do
    if is_our_server_pid "$pid"; then
      log "killing voice_room listener pid=$pid"
      kill "$pid" 2>/dev/null || true
      sleep 0.2
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    local left=0
    for pid in $(listener_pids); do
      if is_our_server_pid "$pid"; then left=1; fi
    done
    [[ "$left" -eq 0 ]] && return 0
    sleep 0.3
  done
}

# Atomic lock via mkdir (works on macOS without flock)
acquire_lock() {
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ >"$LOCKDIR/pid"
    return 0
  fi
  # Stale lock? owner dead
  local owner
  owner="$(cat "$LOCKDIR/pid" 2>/dev/null || true)"
  if [[ -n "$owner" ]] && ! kill -0 "$owner" 2>/dev/null; then
    log "removing stale lockdir owner=$owner"
    rm -rf "$LOCKDIR"
    if mkdir "$LOCKDIR" 2>/dev/null; then
      echo $$ >"$LOCKDIR/pid"
      return 0
    fi
  fi
  return 1
}

release_lock() {
  rm -rf "$LOCKDIR" 2>/dev/null || true
}

cleanup() {
  # Only release if we still own the lockdir
  local owner
  owner="$(cat "$LOCKDIR/pid" 2>/dev/null || true)"
  if [[ "$owner" == "$$" ]]; then
    release_lock
  fi
}

monitor_while_healthy() {
  log "voice room monitoring healthy instance on :${PORT} (no lock)"
  while healthy; do
    sleep 15
  done
  log "voice room health lost — exiting for KeepAlive restart"
  exit 1
}

if ! acquire_lock; then
  if healthy; then
    monitor_while_healthy
  fi
  # Unhealthy but lock held by live owner — wait briefly then exit for KeepAlive
  log "lock held and not healthy — exit for retry"
  exit 1
fi

trap cleanup EXIT

# We own the lock: ensure we are the only server.
if healthy || [[ -n "$(listener_pids)" ]]; then
  log "lock acquired; taking over listeners on :${PORT}"
  kill_our_listeners || true
  sleep 0.4
fi

if healthy; then
  log "port still healthy under foreign process — release lock and monitor"
  release_lock
  trap - EXIT
  monitor_while_healthy
fi

log "starting voice room host=${HOST} port=${PORT} py=${PY} pid=$$"
echo $$ >"$PIDFILE"
# Replace this process with the server so launchd tracks the real service.
# Keep lockdir alive for the server PID (same $$ after exec? No — exec replaces
# image but keeps PID, so lockdir/pid stays valid).
exec "$PY" "$DIR/server.py" \
  --host "$HOST" \
  --port "$PORT" \
  ${RC_VOICE_ROOM_CERT:+--cert "$RC_VOICE_ROOM_CERT"} \
  ${RC_VOICE_ROOM_KEY:+--key "$RC_VOICE_ROOM_KEY"} \
  >>"$LOG_DIR/voice-room.log" 2>&1
