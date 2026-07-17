#!/usr/bin/env bash
# Reclaim stuck in_flight_ids / fat pending / dead room locks.
# Always backs up under ~/logs/rocketchat-state-reclaim/<stamp>/ first.
#
# Usage:
#   ./reclaim-stuck-wake-state.sh              # clear zombie inflight + dead locks
#   ./reclaim-stuck-wake-state.sh --drop-pending   # also clear grok pending_wakes
#   ./reclaim-stuck-wake-state.sh --kickstart      # restart operators after
#   ./reclaim-stuck-wake-state.sh --dry-run
set -euo pipefail

DROP_PENDING=0
KICKSTART=0
DRY=0
for arg in "$@"; do
  case "$arg" in
    --drop-pending) DROP_PENDING=1 ;;
    --kickstart) KICKSTART=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
  esac
done

export RC_RECLAIM_DROP_PENDING="$DROP_PENDING"
export RC_RECLAIM_DRY="$DRY"

python3 - <<'PY'
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

WAKE = Path.home() / ".grok/agency/ops/rocketchat/wake"
BACKUP = Path.home() / "logs/rocketchat-state-reclaim"
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
dest = BACKUP / stamp
drop_pending = os.environ.get("RC_RECLAIM_DROP_PENDING") == "1"
dry = os.environ.get("RC_RECLAIM_DRY") == "1"

STATE_FILES = [
    "state.json",
    "hermes_state.json",
    "agy_state.json",
    "feynman_state.json",
    "nie_state.json",
]


def alive(pid: str) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


if not dry:
    dest.mkdir(parents=True, exist_ok=True)

report: dict = {"stamp": stamp, "drop_pending": drop_pending, "dry": dry, "files": {}, "locks_cleared": []}

for name in STATE_FILES:
    p = WAKE / name
    if not p.is_file():
        continue
    st = json.loads(p.read_text(encoding="utf-8"))
    before = {
        "in_flight_ids": list(st.get("in_flight_ids") or []),
        "pending": len(st.get("pending_wakes") or []),
        "bubbles": len(st.get("activity_bubbles") or {}),
    }
    if not dry:
        shutil.copy2(p, dest / name)
        pending = list(st.get("pending_wakes") or [])
        if pending:
            (dest / f"{name}.pending_wakes.json").write_text(
                json.dumps(pending, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    inflight = set(str(x) for x in (st.get("in_flight_ids") or []))
    st["in_flight_ids"] = []
    st["in_flight_texts"] = {}
    bubbles = dict(st.get("activity_bubbles") or {})
    if name == "state.json" and drop_pending:
        st["pending_wakes"] = []
        st["activity_bubbles"] = {}
    else:
        for mid in list(bubbles.keys()):
            if mid in inflight:
                bubbles.pop(mid, None)
        st["activity_bubbles"] = bubbles

    if not dry:
        tmp = p.with_suffix(p.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(p)

    after = {
        "in_flight_ids": st.get("in_flight_ids"),
        "pending": len(st.get("pending_wakes") or []),
        "bubbles": len(st.get("activity_bubbles") or {}),
    }
    report["files"][name] = {"before": before, "after": after}
    print(
        f"{'DRY ' if dry else ''}{name}: inflight "
        f"{len(before['in_flight_ids'])}->{len(after['in_flight_ids'] or [])} "
        f"pending {before['pending']}->{after['pending']} "
        f"bubbles {before['bubbles']}->{after['bubbles']}"
    )

# Dead room locks
for logdir in Path.home().glob("logs/rocketchat-*-wake"):
    rooms = logdir / "wake.lock.d" / "rooms"
    if not rooms.is_dir():
        continue
    for room in rooms.iterdir():
        if not room.is_dir():
            continue
        hp = room / "holder.pid"
        if not hp.is_file():
            continue
        pid = hp.read_text().strip()
        if alive(pid):
            print(f"keep live lock {logdir.name}/{room.name} pid={pid}")
            continue
        if not dry:
            for child in list(room.iterdir()):
                try:
                    if child.is_file():
                        child.unlink()
                    else:
                        shutil.rmtree(child, ignore_errors=True)
                except Exception as e:
                    print("lock clear fail", child, e)
        report["locks_cleared"].append(f"{logdir.name}/{room.name} dead_pid={pid}")
        print(f"{'DRY ' if dry else ''}cleared dead lock {logdir.name}/{room.name} pid={pid}")

if not dry:
    (dest / "reclaim_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("backup", dest)
else:
    print("dry-run complete (no files written)")
print(json.dumps({"locks_cleared": len(report["locks_cleared"]), "drop_pending": drop_pending}, indent=2))
PY

if [[ "$KICKSTART" == "1" && "$DRY" != "1" ]]; then
  UID_NUM="$(id -u)"
  for label in operator hermes-operator agy-operator feynman-operator nie-operator; do
    launchctl kickstart -k "gui/${UID_NUM}/com.velocityworks.rocketchat-${label}" 2>/dev/null || true
  done
  echo "kickstarted operators"
fi
