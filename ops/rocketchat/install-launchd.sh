#!/usr/bin/env bash
# IMP-11: render launchd plists from templates
set -euo pipefail

# Prefers templates/*.plist.tmpl when present (IMP-11); falls back to heredoc.
ROOT="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="${HOME:-/Users/$(whoami)}"
LAUNCH="$HOME_DIR/Library/LaunchAgents"
LOG_RC="$HOME_DIR/logs/rocketchat-dm-wake"
LOG_NG="$HOME_DIR/logs/ngrok-rocketchat"
mkdir -p "$LAUNCH" "$LOG_RC" "$LOG_NG"
GROK_BIN="${GROK_BIN:-$HOME_DIR/.local/bin/grok}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
VENV_PY="$ROOT/.venv/bin/python"
if [[ -x "$VENV_PY" ]]; then
  PYTHON_BIN="$VENV_PY"
fi
DRY="${1:-}"


render_from_template() {
  local tmpl="$1" out="$2"
  if [[ ! -f "$tmpl" ]]; then
    return 1
  fi
  sed -e "s|@HOME@|${HOME_DIR}|g" \
      -e "s|@ROOT@|${ROOT}|g" \
      -e "s|@GROK_BIN@|${GROK_BIN}|g" \
      -e "s|@PYTHON_BIN@|${PYTHON_BIN}|g" \
      "$tmpl" > "$out"
  echo "wrote $out (from template $(basename "$tmpl"))"
  return 0
}

render() {
  local label="$1" script="$2" outname="$3" keepalive="$4"
  local out="$LAUNCH/$outname"
  local body
  body=$(cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$script</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
PLIST
)
  if [[ "$keepalive" == "1" ]]; then
    body+=$'\n    <key>KeepAlive</key>\n    <true/>'
  fi
  body+=$(cat <<PLIST

    <key>StandardOutPath</key>
    <string>$LOG_RC/${outname%.plist}.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_RC/${outname%.plist}.stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>$HOME_DIR</string>
        <key>PATH</key>
        <string>$HOME_DIR/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>GROK_BIN</key>
        <string>$GROK_BIN</string>
        <key>PYTHON_BIN</key>
        <string>$PYTHON_BIN</string>
        <key>RC_WAKE_APPROVAL_MODE</key>
        <string>restricted</string>
        <key>RC_WAKE_ADMIN_DMS_ONLY</key>
        <string>1</string>
        <key>RC_WAKE_MAX_TURNS</key>
        <string>100</string>
        <key>RC_AUTO_CREATE_PROJECTS</key>
        <string>1</string>
    </dict>
</dict>
</plist>
PLIST
)
  if [[ "$DRY" == "--dry-run" ]]; then
    echo "==== $out ===="
    echo "$body"
  else
    printf '%s\n' "$body" > "$out"
    echo "wrote $out"
  fi
}

OP_OUT="$LAUNCH/com.velocityworks.rocketchat-operator.plist"
if [[ "$DRY" == "--dry-run" ]]; then
  echo "==== template operator ===="
  sed -e "s|@HOME@|${HOME_DIR}|g" -e "s|@ROOT@|${ROOT}|g" -e "s|@GROK_BIN@|${GROK_BIN}|g" -e "s|@PYTHON_BIN@|${PYTHON_BIN}|g"     "$ROOT/templates/com.velocityworks.rocketchat-operator.plist.tmpl" || true
else
  render_from_template "$ROOT/templates/com.velocityworks.rocketchat-operator.plist.tmpl" "$OP_OUT"     || render com.velocityworks.rocketchat-operator          "$ROOT/wake/run_operator_agent.sh"          com.velocityworks.rocketchat-operator.plist 1
fi

# ngrok — prefer template (IMP-11), heredoc fallback only if template missing
NG_OUT="$LAUNCH/com.velocityworks.ngrok-rocketchat.plist"
NG_TMPL="$ROOT/templates/com.velocityworks.ngrok-rocketchat.plist.tmpl"
if [[ "$DRY" == "--dry-run" ]]; then
  echo "==== template ngrok ===="
  if [[ -f "$NG_TMPL" ]]; then
    sed -e "s|@HOME@|${HOME_DIR}|g" -e "s|@ROOT@|${ROOT}|g" \
        -e "s|@GROK_BIN@|${GROK_BIN}|g" -e "s|@PYTHON_BIN@|${PYTHON_BIN}|g" \
        "$NG_TMPL"
  else
    echo "(no ngrok template)"
  fi
else
  if ! render_from_template "$NG_TMPL" "$NG_OUT"; then
    # Fallback heredoc if template absent
    cat > "$NG_OUT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.velocityworks.ngrok-rocketchat</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$ROOT/run_ngrok.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_NG/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_NG/launchd.stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>$HOME_DIR</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
PLIST
    echo "wrote $NG_OUT (heredoc fallback)"
  fi
fi

echo "Note: poll agent is intentionally NOT installed (IMP-18). Primary = WebSocket operator."
echo "Load: launchctl bootstrap gui/\$(id -u) $LAUNCH/com.velocityworks.rocketchat-operator.plist"
