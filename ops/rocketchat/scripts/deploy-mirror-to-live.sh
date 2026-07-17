#!/usr/bin/env bash
# Option 1: deploy reviewable mirror → live agency tree.
# Does NOT overwrite secrets, state, venv, or caches on the host.
# After deploy: kickstart operators (Python reload).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIVE="${RC_LIVE_ROOT:-$HOME/.grok/agency/ops/rocketchat}"
MIRROR="${RC_MIRROR_ROOT:-$ROOT}"
DRY="${1:-}"

if [[ ! -d "$MIRROR/wake" ]]; then
  echo "mirror wake/ missing: $MIRROR" >&2
  exit 1
fi
if [[ ! -d "$LIVE" ]]; then
  echo "live tree missing: $LIVE" >&2
  exit 1
fi

echo "deploy MIRROR → LIVE"
echo "  mirror: $MIRROR"
echo "  live:   $LIVE"

RSYNC=(rsync -a)
if [[ "$DRY" == "--dry-run" ]]; then
  RSYNC+=(-n -v)
  echo "(dry-run)"
fi

"${RSYNC[@]}" \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.benchmarks/' \
  --exclude '*.pyc' \
  --exclude 'wake/*_state.json' \
  --exclude 'wake/*_state.json.lock' \
  --exclude 'wake/state.json' \
  --exclude 'wake/multi_round_collab_state.json' \
  --exclude 'wake/multi_round_collab_state.json.lock' \
  --exclude '.DS_Store' \
  --exclude '.git/' \
  "$MIRROR/" "$LIVE/"

echo "done."
if [[ "$DRY" != "--dry-run" ]]; then
  echo "Kickstart operators to reload Python:"
  echo "  UID_NUM=\$(id -u)"
  echo "  for label in operator hermes-operator agy-operator feynman-operator nie-operator; do"
  echo "    launchctl kickstart -k \"gui/\${UID_NUM}/com.velocityworks.rocketchat-\${label}\""
  echo "  done"
fi
