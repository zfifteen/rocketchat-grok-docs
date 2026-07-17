#!/usr/bin/env bash
# IMP-12: exit 0 if operator health.json is fresh and ws_connected
set -euo pipefail
HEALTH="${RC_HEALTH_PATH:-$HOME/logs/rocketchat-dm-wake/health.json}"
MAX_AGE="${RC_HEALTH_MAX_AGE_S:-120}"
python3 - "$HEALTH" "$MAX_AGE" <<'PY'
import json, sys, time
from datetime import datetime, timezone
path, max_age = sys.argv[1], float(sys.argv[2])
try:
    data = json.loads(open(path, encoding="utf-8").read())
    ts = data.get("ts") or ""
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - t).total_seconds()
    ok = age <= max_age and bool(data.get("ws_connected"))
    sys.exit(0 if ok else 1)
except Exception:
    sys.exit(1)
PY
