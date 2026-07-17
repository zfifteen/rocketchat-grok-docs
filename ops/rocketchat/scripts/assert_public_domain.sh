#!/usr/bin/env bash
# Refuse blocked / free ngrok domains for Rocket.Chat public URL.
# Exit 0 only when every checked surface uses the canonical host.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIN_FILE="${RC_PUBLIC_DOMAIN_FILE:-$ROOT/PUBLIC_DOMAIN}"
NGROK_YML="${NGROK_CONFIG:-$HOME/Library/Application Support/ngrok/ngrok.yml}"
COMPOSE_ENV="${RC_COMPOSE_ENV:-$ROOT/.env}"
SECRETS_RC="${RC_SECRETS_PATH:-$HOME/.grok/agency/secrets/rocketchat.env}"
SECRETS_NG="${NGROK_SECRETS_PATH:-$HOME/.grok/agency/secrets/ngrok.env}"

# Hard-coded retired host — never accept as pin or runtime URL.
FORBIDDEN_HOST="cash-scalded-enhance.ngrok-free.dev"
FORBIDDEN_SUFFIX="ngrok-free.dev"
# Fallback if pin file is missing or poisoned (must match historical fix).
DEFAULT_CANONICAL="velocityworks-rc.ngrok.app"

fail() {
  echo "assert_public_domain: FAIL — $*" >&2
  exit 1
}

host_from_url() {
  local u="$1"
  u="${u#https://}"
  u="${u#http://}"
  u="${u%%/*}"
  u="${u%%:*}"
  printf '%s' "$u"
}

is_forbidden() {
  local host="$1"
  [[ "$host" == "$FORBIDDEN_HOST" || "$host" == *"$FORBIDDEN_HOST"* ]] && return 0
  [[ "$host" == *".$FORBIDDEN_SUFFIX" || "$host" == "$FORBIDDEN_SUFFIX" ]] && return 0
  return 1
}

canonical="$(
  grep -E -v '^\s*(#|$)' "$PIN_FILE" 2>/dev/null | head -1 | tr -d '[:space:]' || true
)"
if [[ -z "$canonical" ]]; then
  echo "assert_public_domain: pin missing — using default $DEFAULT_CANONICAL" >&2
  canonical="$DEFAULT_CANONICAL"
fi
if is_forbidden "$canonical"; then
  fail "PUBLIC_DOMAIN pin is forbidden ($canonical). Restore pin to $DEFAULT_CANONICAL"
fi
if [[ "$canonical" != *".ngrok.app" && "$canonical" != *".ngrok.dev" ]]; then
  # Allow only ngrok branded hosts for this deployment (not free suffix).
  fail "PUBLIC_DOMAIN pin must be a branded ngrok host (*.ngrok.app), got: $canonical"
fi

check_host() {
  local label="$1" host="$2"
  [[ -n "$host" ]] || fail "$label is empty"
  if is_forbidden "$host"; then
    fail "$label uses forbidden blocked/free domain: $host (canonical is $canonical)"
  fi
  if [[ "$host" != "$canonical" ]]; then
    fail "$label host is '$host' but canonical pin is '$canonical'"
  fi
}

# 1) Pin file itself (already validated non-forbidden)
echo "assert_public_domain: pin=$canonical"

# 2) ngrok.yml tunnel url
if [[ -f "$NGROK_YML" ]]; then
  yml_host="$(
    python3 - "$NGROK_YML" <<'PY'
import sys, re
text = open(sys.argv[1], encoding="utf-8").read()
# Prefer tunnels.rocketchat url:
m = re.search(r"(?m)^\s*url:\s*(\S+)\s*$", text)
if m:
    print(m.group(1).strip().strip("\"'"))
PY
  )"
  if [[ -n "$yml_host" ]]; then
    yml_host="$(host_from_url "$yml_host")"
    check_host "ngrok.yml url" "$yml_host"
  else
    fail "ngrok.yml has no tunnel url: field"
  fi
else
  fail "ngrok config missing: $NGROK_YML"
fi

# 3) compose .env ROOT_URL
if [[ -f "$COMPOSE_ENV" ]]; then
  root_url="$(grep -E '^ROOT_URL=' "$COMPOSE_ENV" | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"' | tr -d "'")"
  check_host "compose .env ROOT_URL" "$(host_from_url "$root_url")"
fi

# 4) secrets (if present)
for f in "$SECRETS_RC" "$SECRETS_NG"; do
  [[ -f "$f" ]] || continue
  while IFS= read -r line; do
    case "$line" in
      ROCKETCHAT_ROOT_URL=*|ROCKETCHAT_PUBLIC_URL=*|NGROK_PUBLIC_URL=*|NGROK_PUBLIC_DOMAIN=*|ROOT_URL=*)
        val="${line#*=}"
        val="${val//$'\r'/}"
        host="$(host_from_url "$val")"
        # Allow empty LAN-only keys to skip
        [[ -z "$host" ]] && continue
        check_host "$f:${line%%=*}" "$host"
        ;;
      NGROK_FREE_DOMAIN=*)
        fail "$f still defines NGROK_FREE_DOMAIN (retired). Use NGROK_PUBLIC_DOMAIN=$canonical only."
        ;;
    esac
  done < "$f"
done

# 5) Optional live probes (skip if services down)
if curl -sf --max-time 2 "http://127.0.0.1:4040/api/tunnels" >/dev/null 2>&1; then
  live="$(
    curl -sf --max-time 3 "http://127.0.0.1:4040/api/tunnels" \
      | python3 -c 'import sys,json; d=json.load(sys.stdin); print((d.get("tunnels") or [{}])[0].get("public_url") or "")'
  )"
  if [[ -n "$live" ]]; then
    check_host "live ngrok tunnel" "$(host_from_url "$live")"
  fi
fi
if curl -sf --max-time 2 "http://127.0.0.1:3000/api/info" >/dev/null 2>&1; then
  ws="$(
    curl -sf --max-time 3 "http://127.0.0.1:3000/api/info" \
      | python3 -c 'import sys,json; print(json.load(sys.stdin).get("workspaceUrl") or "")'
  )"
  if [[ -n "$ws" ]]; then
    check_host "live RC workspaceUrl" "$(host_from_url "$ws")"
  fi
fi

echo "assert_public_domain: OK — canonical host $canonical"
