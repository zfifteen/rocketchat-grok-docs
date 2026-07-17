#!/usr/bin/env bash
# Option 1 polish: report SHA parity of critical files live ↔ mirror.
# Exit 0 if match, 1 if any critical mismatch, 2 if live/mirror missing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIVE="${RC_LIVE_ROOT:-$HOME/.grok/agency/ops/rocketchat}"
MIRROR="${RC_MIRROR_ROOT:-$ROOT}"

CRITICAL=(
  wake/wake_inflight_ux.py
  wake/wake_ux_imp23.py
  wake/wake_denials.py
  wake/rc_multi_round_collab.py
  wake/wake_lib.py
  wake/wake_telemetry.py
  wake/rc_operator_agent.py
  wake/rc_collab.py
  wake/rc_commands.py
  wake/rc_config.py
  scripts/rc_wake_digest.py
)

if [[ ! -d "$LIVE/wake" ]]; then
  echo "live missing: $LIVE" >&2
  exit 2
fi
if [[ ! -d "$MIRROR/wake" ]]; then
  echo "mirror missing: $MIRROR" >&2
  exit 2
fi

echo "check LIVE ↔ MIRROR parity"
echo "  live:   $LIVE"
echo "  mirror: $MIRROR"
echo

mism=0
miss=0
for rel in "${CRITICAL[@]}"; do
  a="$LIVE/$rel"
  b="$MIRROR/$rel"
  if [[ ! -f "$a" ]]; then
    echo "MISS live   $rel"
    miss=$((miss + 1))
    continue
  fi
  if [[ ! -f "$b" ]]; then
    echo "MISS mirror $rel"
    miss=$((miss + 1))
    continue
  fi
  ha=$(shasum -a 256 "$a" | awk '{print $1}')
  hb=$(shasum -a 256 "$b" | awk '{print $1}')
  if [[ "$ha" == "$hb" ]]; then
    echo "OK   $rel"
  else
    echo "DIFF $rel"
    echo "     live=$ha"
    echo "     mirror=$hb"
    mism=$((mism + 1))
  fi
done

echo
if [[ $miss -gt 0 || $mism -gt 0 ]]; then
  echo "RESULT: miss=$miss mismatch=$mism"
  echo "  host edits → ./scripts/sync-mirror-from-live.sh && git commit"
  echo "  git edits  → ./scripts/deploy-mirror-to-live.sh && kickstart"
  exit 1
fi
echo "RESULT: all critical files match"
exit 0
