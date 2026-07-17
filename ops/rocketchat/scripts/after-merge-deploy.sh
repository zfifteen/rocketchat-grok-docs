#!/usr/bin/env bash
# Stage 2 default: after merge to main, deploy git → live, verify parity, kickstart.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$REPO"

SKIP_KICK="${RC_DEPLOY_SKIP_KICKSTART:-0}"
SKIP_PARITY="${RC_DEPLOY_SKIP_PARITY:-0}"

echo "=== Stage 2 after-merge deploy ==="
echo "repo: $REPO"
echo "mirror: $ROOT"

"$ROOT/scripts/deploy-mirror-to-live.sh"

if [[ "$SKIP_PARITY" != "1" ]]; then
  echo
  "$ROOT/scripts/check-mirror-parity.sh"
fi

if [[ "$SKIP_KICK" == "1" ]]; then
  echo "skip kickstart (RC_DEPLOY_SKIP_KICKSTART=1)"
  exit 0
fi

echo
echo "=== kickstart operators ==="
UID_NUM="$(id -u)"
for label in operator hermes-operator agy-operator feynman-operator nie-operator; do
  if launchctl kickstart -k "gui/${UID_NUM}/com.velocityworks.rocketchat-${label}" 2>/dev/null; then
    echo "  kicked com.velocityworks.rocketchat-${label}"
  else
    echo "  warn: kickstart failed com.velocityworks.rocketchat-${label}" >&2
  fi
done

sleep 5
python3 - <<'PY'
import json, os, time
from pathlib import Path

def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False

bots = (
    "rocketchat-dm-wake",
    "rocketchat-hermes-wake",
    "rocketchat-agy-wake",
    "rocketchat-feynman-wake",
    "rocketchat-nie-wake",
)

# WS may take a few seconds after kickstart
for _ in range(6):
    rows = []
    for b in bots:
        p = Path.home() / "logs" / b / "health.json"
        if not p.is_file():
            rows.append((b, None, False, False))
            continue
        h = json.loads(p.read_text())
        pid = h.get("pid")
        rows.append((b, pid, alive(pid) if pid else False, bool(h.get("ws_connected"))))
    if all(a and ws for _, _, a, ws in rows):
        break
    time.sleep(2)

print("=== health ===")
ok_alive = True
for b, pid, a, ws in rows:
    status = "OK" if a and ws else ("WARN" if a else "FAIL")
    if not a:
        ok_alive = False
    print(f"{status} {b}: pid={pid} alive={a} ws={ws}")
# Alive is required; ws may still be connecting — warn only
raise SystemExit(0 if ok_alive else 1)
PY
