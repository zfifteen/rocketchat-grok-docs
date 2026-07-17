#!/usr/bin/env bash
# IMP-15: backup Mongo volume for agency-rocketchat
set -euo pipefail
DEST="${1:-$HOME/backups/rocketchat-mongo-$(date +%Y%m%d-%H%M%S).tar.gz}"
mkdir -p "$(dirname "$DEST")"
# Prefer docker volume backup via alpine
VOL=$(docker volume ls -q | grep -E 'agency-rocketchat.*mongodb' | head -1 || true)
if [[ -z "${VOL:-}" ]]; then
  VOL=$(docker volume ls -q | grep mongodb_data | head -1 || true)
fi
if [[ -z "${VOL:-}" ]]; then
  echo "no mongodb volume found" >&2
  exit 1
fi
docker run --rm -v "$VOL":/data:ro -v "$(dirname "$DEST")":/backup alpine \
  tar czf "/backup/$(basename "$DEST")" -C /data .
echo "backup=$DEST volume=$VOL"
ls -la "$DEST"
