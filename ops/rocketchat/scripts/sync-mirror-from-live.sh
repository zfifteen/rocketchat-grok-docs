#!/usr/bin/env bash
# Option 1: pull reviewable runtime files from live agency tree into this git mirror.
# Never copies secrets, state, venv, or caches.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIVE="${RC_LIVE_ROOT:-$HOME/.grok/agency/ops/rocketchat}"
MIRROR="${RC_MIRROR_ROOT:-$ROOT}"

if [[ ! -d "$LIVE" ]]; then
  echo "live tree missing: $LIVE" >&2
  exit 1
fi

echo "sync LIVE → MIRROR"
echo "  live:   $LIVE"
echo "  mirror: $MIRROR"

rsync -a \
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
  "$LIVE/" "$MIRROR/"

if [[ -f "$MIRROR/.env" ]]; then
  echo "ERROR: .env appeared in mirror — removing" >&2
  rm -f "$MIRROR/.env"
  exit 1
fi

echo "done. review git status before commit."
