#!/usr/bin/env bash
# Opt-in: restore pending_wakes from a reclaim backup into live grok state.json.
# Does NOT kickstart or force drain — next operator boot/drain will process them.
#
# Usage:
#   ./restore-pending-wakes.sh LIST
#   ./restore-pending-wakes.sh PATH/TO/state.json.pending_wakes.json
#   ./restore-pending-wakes.sh PATH/TO/state.json.pending_wakes.json --replace
#
# Default merges by mid (skip mids already pending). --replace overwrites pending list.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WAKE="${RC_LIVE_ROOT:-$HOME/.grok/agency/ops/rocketchat}/wake"
STATE="$WAKE/state.json"
BACKUP_ROOT="$HOME/logs/rocketchat-state-reclaim"
REPLACE=0

if [[ "${1:-}" == "LIST" || "${1:-}" == "--list" || $# -eq 0 ]]; then
  echo "Available pending backups:"
  find "$BACKUP_ROOT" -name 'state.json.pending_wakes.json' 2>/dev/null | sort || true
  exit 0
fi

SRC=""
for arg in "$@"; do
  case "$arg" in
    --replace) REPLACE=1 ;;
    *) SRC="$arg" ;;
  esac
done

if [[ -z "$SRC" || ! -f "$SRC" ]]; then
  echo "usage: $0 <pending_wakes.json> [--replace]" >&2
  echo "       $0 LIST" >&2
  exit 1
fi

python3 - "$SRC" "$STATE" "$REPLACE" <<'PY'
import json, os, sys, shutil
from pathlib import Path
from datetime import datetime, timezone

src, state_path, replace = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == "1"
items = json.loads(src.read_text(encoding="utf-8"))
if not isinstance(items, list):
    raise SystemExit("backup must be a JSON list")
st = json.loads(state_path.read_text(encoding="utf-8"))
pending = list(st.get("pending_wakes") or [])
# backup current state
bak = state_path.with_suffix(
    state_path.suffix + f".pre-restore.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
)
shutil.copy2(state_path, bak)
if replace:
    st["pending_wakes"] = items
    print(f"replaced pending with {len(items)} items")
else:
    have = {str(p.get("mid")) for p in pending if isinstance(p, dict)}
    added = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        mid = str(it.get("mid") or "")
        if mid and mid in have:
            continue
        pending.append(it)
        if mid:
            have.add(mid)
        added += 1
    st["pending_wakes"] = pending
    print(f"merged +{added} (total pending={len(pending)})")
tmp = state_path.with_suffix(state_path.suffix + f".tmp.{os.getpid()}")
tmp.write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
tmp.replace(state_path)
print("wrote", state_path)
print("pre-restore backup", bak)
print("kickstart grok to drain, or wait for next drain cycle")
PY
