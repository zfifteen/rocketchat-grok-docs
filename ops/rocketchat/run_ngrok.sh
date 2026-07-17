#!/usr/bin/env bash
# Persistent ngrok tunnel for Rocket.Chat (Hobbyist branded domain only).
# Hard-refuses the Charter-Cujo-blocked free domain (*.ngrok-free.dev).
set -euo pipefail
export HOME="${HOME:-/Users/velocityworks}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
NGROK="${NGROK_BIN:-/opt/homebrew/bin/ngrok}"
LOG_DIR="$HOME/logs/ngrok-rocketchat"
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$LOG_DIR"

# Guard: never start a tunnel on the blocked free domain.
if ! bash "$ROOT/scripts/assert_public_domain.sh"; then
  echo "run_ngrok: refusing to start — public domain assertion failed" >&2
  echo "run_ngrok: canonical host is in $ROOT/PUBLIC_DOMAIN (velocityworks-rc.ngrok.app)" >&2
  echo "run_ngrok: do NOT use cash-scalded-enhance.ngrok-free.dev" >&2
  exit 1
fi

# rocketchat = branded public RC domain; hermes-webui = ephemeral HTTPS to local :8787
exec "$NGROK" start rocketchat hermes-webui --config "$HOME/Library/Application Support/ngrok/ngrok.yml" \
  --log=stdout --log-format=logfmt
