# Rocket.Chat multi-agent integration guide

**Audience:** another AI agent (or human operator) setting up a **new bot identity** on the Velocity Works Rocket.Chat stack, parallel to `grok` and `hermes`.  
**Last updated:** 2026-07-14 (four live operators: grok, hermes, agy, claude; peer tag wake default on)  
**Runtime home:** `~/.grok/agency/ops/rocketchat/`  
**Docs map:** `~/IdeaProjects/rocketchat-agents/`  
**Ops runbook:** `~/.grok/agency/ops/ROCKETCHAT.md`  
**Live roster hub:** `~/.grok/agency/ops/rocketchat/MULTI_OPERATOR.md`

This guide is the checklist used to add Hermes, Antigravity (`agy`), and Claude. Follow it in order. Do **not** invent a second Rocket.Chat server; join the existing workspace.

---

## 0. Mental model (read first)

```
Principal (phone/desktop)
    │  HTTPS (ngrok) or http://127.0.0.1:3000
    ▼
Rocket.Chat 8.x (Docker)
    │  WebSocket + REST as YOUR bot user
    ▼
rc_operator_agent.py  (one launchd KeepAlive process PER bot)
    │  👀 + activity bubble → spawn YOUR CLI → chat.update same bubble
    ▼
Your agent CLI (headless)  --cwd project  --resume session
```

Hard rules for this install:

1. **One RC username per operator process.** Never run two operators as the same bot user.
2. **Separate secrets, state, logs, and launchd label** per agent.
3. **Shared channels = tag-to-talk** (`@yourbot`). DMs with that bot free-wake.
4. **You do not post the final answer via RC API yourself.** Write a **reply file**; the operator `chat.update`s the activity bubble.
5. **No duplicate posts.** Images only via `wake/rc_post_media.py`. Never double `rooms.mediaConfirm`.
6. **Secrets never enter chat, reply files, or this docs repo.** Document only *paths* and *variable names*.

Existing live bots:

| RC user | Backend | launchd label | Secrets | Logs |
| --- | --- | --- | --- | --- |
| `grok` | Grok Build CLI | `com.velocityworks.rocketchat-operator` | `secrets/rocketchat.env` | `~/logs/rocketchat-dm-wake/` |
| `hermes` | Hermes CLI (`-p idea`) | `com.velocityworks.rocketchat-hermes-operator` | `secrets/rocketchat-hermes.env` | `~/logs/rocketchat-hermes-wake/` |
| `agy` | Antigravity CLI | `com.velocityworks.rocketchat-agy-operator` | `secrets/rocketchat-agy.env` | `~/logs/rocketchat-agy-wake/` |
| `claude` | Antigravity CLI + Claude model pin | `com.velocityworks.rocketchat-claude-operator` | `secrets/rocketchat-claude.env` | `~/logs/rocketchat-claude-wake/` |

Short runbooks: `MULTI_OPERATOR.md`, `HERMES_OPERATOR.md`, `AGY_OPERATOR.md`, `CLAUDE_OPERATOR.md` under `ops/rocketchat/`.

Voice/Call is **out of scope** for new agents until that stack is productized (Grok-only today). Skip videoconf work.

---

## 1. Prerequisites (verify before changing anything)

```bash
# RC up
curl -sS http://127.0.0.1:3000/api/info | head -c 120; echo

# Compose
cd ~/.grok/agency/ops/rocketchat && docker compose ps

# Python venv with websocket-client
~/.grok/agency/ops/rocketchat/.venv/bin/python -c "import websocket; print('ws ok')"

# Your CLI headless one-shot works (example: hermes)
hermes -p idea chat -q "Reply with PONG only." -Q --max-turns 3

# Principal admin secrets exist (do not print values)
test -f ~/.grok/agency/secrets/rocketchat.env && echo secrets_ok
```

If RC is down: see `ROCKETCHAT.md` (Docker + ngrok). If venv missing: `ops/rocketchat/setup-venv.sh`.

---

## 2. Choose identity

Pick:

| Field | Example | Rules |
| --- | --- | --- |
| RC username | `codex`, `agy`, `claude` | lowercase, unique, short |
| Display name | `Codex Operator` | human-visible |
| Email | `codex@localhost.local` | local-only fine |
| launchd label | `com.velocityworks.rocketchat-codex-operator` | unique |
| Log dir | `~/logs/rocketchat-codex-wake/` | unique |
| State file | `wake/codex_state.json` | unique |
| Secrets file | `~/.grok/agency/secrets/rocketchat-codex.env` | mode `600` |
| Reply prompt | `wake/codex_reply_prompt.txt` | unique |
| Backend | `RC_WAKE_BACKEND=…` or dedicated argv builder | see §5 |

**Do not reuse** `grok` / `hermes` usernames or their secrets files.

---

## 3. Create the Rocket.Chat user (admin API)

Run as a local agent with admin access. **Never echo passwords.**

```python
#!/usr/bin/env python3
"""Create or reset an RC bot user. Prints only non-secret status."""
from __future__ import annotations

import json
import secrets
import string
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:3000"
SECRETS = Path.home() / ".grok" / "agency" / "secrets" / "rocketchat.env"
BOT = "YOUR_BOT_USERNAME"  # e.g. codex
BOT_NAME = "Your Bot Operator"
BOT_EMAIL = f"{BOT}@localhost.local"
OUT = Path.home() / ".grok" / "agency" / "secrets" / f"rocketchat-{BOT}.env"


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def api(method: str, path: str, token=None, uid=None, body=None):
    raw = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=raw, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Auth-Token", token)
        req.add_header("X-User-Id", uid)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


env = load_env(SECRETS)
admin_user = env.get("ROCKETCHAT_ADMIN_USERNAME") or "principal"
admin_pw = env["ROCKETCHAT_ADMIN_PASSWORD"]
login = api("POST", "/api/v1/login", body={"user": admin_user, "password": admin_pw})
token, uid = login["data"]["authToken"], login["data"]["userId"]

alphabet = string.ascii_letters + string.digits
bot_pw = "Bot_" + "".join(secrets.choice(alphabet) for _ in range(24))

info = None
try:
    info = api("GET", f"/api/v1/users.info?username={BOT}", token, uid)
except Exception:
    info = {}

if not (info or {}).get("user"):
    created = api(
        "POST",
        "/api/v1/users.create",
        token,
        uid,
        {
            "email": BOT_EMAIL,
            "name": BOT_NAME,
            "password": bot_pw,
            "username": BOT,
            "roles": ["user"],
            "verified": True,
            "requirePasswordChange": False,
            "joinDefaultChannels": True,
            "sendWelcomeEmail": False,
        },
    )
    print("create_success", created.get("success"), "error", created.get("error"))
else:
    user_id = info["user"]["_id"]
    upd = api(
        "POST",
        "/api/v1/users.update",
        token,
        uid,
        {
            "userId": user_id,
            "data": {
                "password": bot_pw,
                "name": BOT_NAME,
                "email": BOT_EMAIL,
                "verified": True,
                "active": True,
            },
        },
    )
    print("update_success", upd.get("success"), "error", upd.get("error"))

# Verify login as bot
blogin = api("POST", "/api/v1/login", body={"user": BOT, "password": bot_pw})
print("bot_login_ok", blogin.get("status") == "success")
print("bot_uid_prefix", blogin["data"]["userId"][:8])

# Open principal↔bot DM
im = api("POST", "/api/v1/im.create", token, uid, {"username": BOT})
print("dm_ok", im.get("success"), "room_prefix", (im.get("room") or {}).get("_id", "")[:8])

# Write dedicated secrets (mode 600). Operator keys MUST be the bot identity.
carry = [
    "ROCKETCHAT_ROOT_URL",
    "ROCKETCHAT_PUBLIC_URL",
    "ROCKETCHAT_LAN_URL",
    "ROCKETCHAT_ADMIN_USERNAME",
    "ROCKETCHAT_ADMIN_PASSWORD",
    "ROCKETCHAT_ADMIN_EMAIL",
    "ROCKETCHAT_COMPOSE_DIR",
]
lines = [f"# Rocket.Chat operator secrets for {BOT} — mode 600; do not commit\n"]
for k in carry:
    if k in env:
        lines.append(f"{k}={env[k]}\n")
lines += [
    f"ROCKETCHAT_OPERATOR_USERNAME={BOT}\n",
    f"ROCKETCHAT_OPERATOR_PASSWORD={bot_pw}\n",
    f"ROCKETCHAT_OPERATOR_EMAIL={BOT_EMAIL}\n",
]
OUT.write_text("".join(lines))
OUT.chmod(0o600)
print("secrets_path", OUT)
print("DONE")
```

Replace `YOUR_BOT_USERNAME` / names, then run with the ops venv if needed.

---

## 4. Secrets contract

The operator loads **one** secrets file via `RC_SECRETS_PATH` (or default `rocketchat.env`).

Required keys in **your** secrets file:

```bash
ROCKETCHAT_OPERATOR_USERNAME=<bot>
ROCKETCHAT_OPERATOR_PASSWORD=<password>
# optional but preferred later:
# ROCKETCHAT_OPERATOR_TOKEN=...
# ROCKETCHAT_OPERATOR_USER_ID=...
```

Usually also carry public/admin keys from the principal `rocketchat.env` so compose/URL helpers keep working. **Never** put bot password into the Grok secrets file.

File mode:

```bash
chmod 600 ~/.grok/agency/secrets/rocketchat-<bot>.env
```

---

## 5. Choose a wake backend

The shared operator is `wake/rc_operator_agent.py`. It currently has first-class backends:

| `RC_WAKE_BACKEND` | CLI | Notes |
| --- | --- | --- |
| `grok` (default) | Grok Build CLI | `--prompt-file`, `--resume`, streaming-json thoughts |
| `hermes` | Hermes Agent CLI | `hermes -p <profile> chat -q … -Q --resume` |
| `agy` | Antigravity CLI | `agy --prompt … --mode accept-edits --conversation …` |

### 5a. Prefer an existing backend

If your agent **is** Hermes: use `RC_WAKE_BACKEND=hermes` + `RC_HERMES_PROFILE=<profile>` + your own username/secrets/logs/launchd (do not share the hermes user).

If your agent **is** Antigravity: use `RC_WAKE_BACKEND=agy` + your own username/secrets/logs/launchd (e.g. for a bot named `claude` using a specific model).

If your agent **is** Grok Build CLI with a different persona: you still need a **separate RC user + operator process**; backend stays `grok` but secrets/username differ. Tag-to-talk uses `@that-username`.

### 5b. Add a new CLI backend (when needed)

Implement in `wake/wake_lib.py` (pattern from Hermes):

1. `build_<bot>_wake_argv(prompt_path, *, resume_session_id, approval_mode, model, …) -> list[str]`
2. Session-id parser from CLI stdout/stderr
3. Optional reply extraction fallback if the model forgets the reply file
4. Wire branch in `rc_operator_agent._run_wake_once` / `wake_grok` behind `RC_WAKE_BACKEND=<name>`
5. Restricted vs admin flags (Hermes: no `--yolo` vs `--yolo`; Grok: `--permission-mode auto` vs `--always-approve`)

Headless contract every backend must satisfy:

- Accept a large system+user inject (file or `-q` text).
- Run non-interactively to completion.
- Prefer writing the **final user-facing answer** to the **Reply file** path in the inject.
- Support session resume across messages in the same RC room when possible.
- Exit 0 on success; leave logs the operator can capture.

If you cannot add a backend to the shared operator, do **not** half-wire REST from your CLI. Either extend the operator or run a dedicated bridge that still owns the single-bubble UX.

---

## 6. Reply prompt

Copy and edit:

```bash
cp ~/.grok/agency/ops/rocketchat/wake/hermes_reply_prompt.txt \
   ~/.grok/agency/ops/rocketchat/wake/<bot>_reply_prompt.txt
```

Must keep:

- Identity: “You are the **&lt;Bot&gt; operator** …”
- **Reply file only** (no `chat.postMessage` for answers)
- **NO DUPLICATE POSTS** + `rc_post_media.py` for images
- Restricted vs admin expectations for **your** CLI flags
- Inbound attachment path rules (`read_file` local paths; never open secrets)
- `{{CONTEXT}}` placeholder for the operator inject

Point launchd/env at it:

```bash
RC_REPLY_PROMPT=~/.grok/agency/ops/rocketchat/wake/<bot>_reply_prompt.txt
```

If `RC_WAKE_BACKEND=hermes` and you do not set `RC_REPLY_PROMPT`, the operator defaults to `hermes_reply_prompt.txt` — override for a non-Hermes persona.

---

## 7. Run wrapper script

Create `wake/run_<bot>_operator_agent.sh` (executable):

```bash
#!/usr/bin/env bash
# KeepAlive entry for <bot> RC operator (parallel to grok/hermes).
set -euo pipefail
export HOME="${HOME:-/Users/velocityworks}"
OPS_RC="$HOME/.grok/agency/ops/rocketchat"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$OPS_RC/.venv/bin/python3" ]]; then
    PYTHON_BIN="$OPS_RC/.venv/bin/python3"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
fi
export PYTHON_BIN
export PATH="$OPS_RC/.venv/bin:$HOME/.local/bin:$HOME/.grok/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# --- identity isolation (REQUIRED unique values) ---
export RC_SECRETS_PATH="${RC_SECRETS_PATH:-$HOME/.grok/agency/secrets/rocketchat-<bot>.env}"
export RC_LOG_DIR="${RC_LOG_DIR:-$HOME/logs/rocketchat-<bot>-wake}"
export RC_STATE_PATH="${RC_STATE_PATH:-$OPS_RC/wake/<bot>_state.json}"
export RC_REPLY_PROMPT="${RC_REPLY_PROMPT:-$OPS_RC/wake/<bot>_reply_prompt.txt}"

# --- backend ---
export RC_WAKE_BACKEND="${RC_WAKE_BACKEND:-hermes}"   # or grok / your backend
export RC_HERMES_PROFILE="${RC_HERMES_PROFILE:-idea}" # if hermes
export HERMES_BIN="${HERMES_BIN:-$HOME/.local/bin/hermes}"
export GROK_BIN="${GROK_BIN:-$HOME/.local/bin/grok}"

# --- dual-operator tag-to-talk (REQUIRED for shared channels) ---
export RC_REQUIRE_MENTION="${RC_REQUIRE_MENTION:-1}"
export RC_REQUIRE_MENTION_SCOPE="${RC_REQUIRE_MENTION_SCOPE:-channels}"

# --- safety defaults matching production ---
export RC_WAKE_APPROVAL_MODE="${RC_WAKE_APPROVAL_MODE:-restricted}"
export RC_WAKE_ADMIN_DMS_ONLY="${RC_WAKE_ADMIN_DMS_ONLY:-1}"
export RC_WAKE_MAX_TURNS="${RC_WAKE_MAX_TURNS:-100}"
export RC_WAKE_TIMEOUT_S="${RC_WAKE_TIMEOUT_S:-600}"
export RC_WAKE_LOCK_STALE_S="${RC_WAKE_LOCK_STALE_S:-900}"
export RC_AUTO_CREATE_PROJECTS="${RC_AUTO_CREATE_PROJECTS:-1}"
export RC_WAKE_STREAM="${RC_WAKE_STREAM:-0}"
export RC_CONTROL_PLANE="${RC_CONTROL_PLANE:-1}"

mkdir -p "$RC_LOG_DIR"
exec "$PYTHON_BIN" "$OPS_RC/wake/rc_operator_agent.py" \
  >>"$RC_LOG_DIR/operator-agent.stdout.log" 2>>"$RC_LOG_DIR/operator-agent.stderr.log"
```

```bash
chmod +x ~/.grok/agency/ops/rocketchat/wake/run_<bot>_operator_agent.sh
mkdir -p ~/logs/rocketchat-<bot>-wake
```

---

## 8. launchd (macOS KeepAlive)

Install `~/Library/LaunchAgents/com.velocityworks.rocketchat-<bot>-operator.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.velocityworks.rocketchat-BOT-operator</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/velocityworks/.grok/agency/ops/rocketchat/wake/run_BOT_operator_agent.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/velocityworks/logs/rocketchat-BOT-wake/operator-launchd.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/velocityworks/logs/rocketchat-BOT-wake/operator-launchd.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>/Users/velocityworks</string>
    <key>PATH</key>
    <string>/Users/velocityworks/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>PYTHON_BIN</key>
    <string>/Users/velocityworks/.grok/agency/ops/rocketchat/.venv/bin/python</string>
    <key>RC_WAKE_BACKEND</key>
    <string>hermes</string>
    <key>RC_SECRETS_PATH</key>
    <string>/Users/velocityworks/.grok/agency/secrets/rocketchat-BOT.env</string>
    <key>RC_LOG_DIR</key>
    <string>/Users/velocityworks/logs/rocketchat-BOT-wake</string>
    <key>RC_REQUIRE_MENTION</key>
    <string>1</string>
    <key>RC_REQUIRE_MENTION_SCOPE</key>
    <string>channels</string>
    <key>RC_WAKE_APPROVAL_MODE</key>
    <string>restricted</string>
    <key>RC_WAKE_ADMIN_DMS_ONLY</key>
    <string>1</string>
    <key>RC_WAKE_MAX_TURNS</key>
    <string>100</string>
    <key>RC_WAKE_TIMEOUT_S</key>
    <string>600</string>
    <key>RC_WAKE_LOCK_STALE_S</key>
    <string>900</string>
    <key>RC_AUTO_CREATE_PROJECTS</key>
    <string>1</string>
    <key>RC_CONTROL_PLANE</key>
    <string>1</string>
  </dict>
</dict>
</plist>
```

Load / restart:

```bash
launchctl bootout gui/$(id -u)/com.velocityworks.rocketchat-BOT-operator 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.velocityworks.rocketchat-BOT-operator.plist
launchctl enable gui/$(id -u)/com.velocityworks.rocketchat-BOT-operator
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-BOT-operator
```

Healthy log lines to expect:

```text
config applied ... operator=BOT require_mention=1 require_mention_scope=channels ...
watch rooms: dm:principal(d), ...
login OK — setting online + subscribe
subscribed stream-room-messages room=dm:principal ...
```

If you hit HTTP 429, wait and let KeepAlive reconnect (do not thrash kickstart).

---

## 9. Tag-to-talk (mandatory for shared rooms)

Production multi-operator settings:

```bash
RC_REQUIRE_MENTION=1
RC_REQUIRE_MENTION_SCOPE=channels
RC_PEER_TAG_WAKE=1
```

| Room type | Behavior |
| --- | --- |
| DM principal↔bot | Free-wake (no @ required) |
| Channel (`c`) / private group (`p`) | Wake **only** if message `@mentions` **this** operator username |
| Non-principal author (peer bot / other human) | With `RC_PEER_TAG_WAKE=1` (default **on**): same @mention rule — **any** author who tags this bot can wake it |
| Self-posts | Never wake (loop prevention) |
| Control plane `!help` / `!status` / … | Mention-exempt (handled before LLM wake) |

Code entrypoint: `wake_lib.should_enqueue_llm_wake` (prefer over legacy principal-only `should_handle_dm_message`).

Untagged channel noise must log like:

```text
skip no_operator_mention operator=<bot> room=<name> room_type=c
```

Tagged wake:

```text
principal msg in <room>: @bot ...
wake enqueued ...
```

Principal usage:

- Talk to Hermes: `@hermes …`
- Talk to Grok: `@grok …`
- Talk to you: `@<bot> …`

Grok’s launchd also sets mention mode so both bots do not double-answer untagged channel chatter.

To require @ even in DMs (usually wrong): `RC_REQUIRE_MENTION_SCOPE=all`.

---

## 10. Rooms, cwd, and invites

| Room | Default project cwd |
| --- | --- |
| DM | `~/.grok/agency` |
| Channel/group | `~/IdeaProjects/<slug>` (auto-create if `RC_AUTO_CREATE_PROJECTS=1`) |
| Overrides | `wake/channel_projects.json` |

Invite the bot into channels the principal wants (admin/UI or API `channels.invite` / `groups.invite`). Operator re-scans membership ~every 60s.

Do **not** join every room by default if you want a quiet bot—join only where needed; still use tag-to-talk.

---

## 11. Principal UX (what “working” looks like)

For each waking message:

1. 👀 reaction on the principal message (kept)
2. One activity bubble as the bot (`…` / Working meta)
3. Headless CLI run with inject + reply file
4. `chat.update` that bubble → final answer only (no second text bubble)

Control plane (principal, `!` prefix — RC steals leading `/`):

`!help` `!status` `!health` `!new` `!cwd` `!mode` `!model` `!effort` `!goal` `!admin once|on|off` `!cancel` `!retry` `!wake` `!ask`

---

## 12. Verification checklist (do not skip)

### A. Process

```bash
launchctl print gui/$(id -u)/com.velocityworks.rocketchat-BOT-operator | head -40
tail -30 ~/logs/rocketchat-BOT-wake/operator-agent.log
```

Confirm: `operator=<bot>`, `require_mention=1`, `login OK`, DM subscribed.

### B. DM free-wake

As principal, DM the bot: `smoke: reply EXACTLY SMOKE_OK`.  
Expect one final bubble containing `SMOKE_OK`.

### C. Channel tag-to-talk

In a shared channel both bots can see:

1. Untagged: `noise — bots must ignore`  
   - Your log: `skip no_operator_mention`  
   - No activity bubble from you
2. Tagged: `@BOT reply exactly TAG_OK`  
   - Your log: `wake enqueued`  
   - Final bubble: `TAG_OK`

### D. Isolation

```bash
# Must still be running independently
launchctl print gui/$(id -u)/com.velocityworks.rocketchat-operator | rg "state ="
launchctl print gui/$(id -u)/com.velocityworks.rocketchat-hermes-operator | rg "state ="
```

Grok/Hermes must not stop when you start. Your secrets file must not be the Grok file.

### E. Security

- [ ] Secrets mode `600`
- [ ] No passwords in logs/docs/chat
- [ ] Restricted mode default (no full yolo/always-approve in channels)
- [ ] Reply prompt forbids opening `rocketchat.env` / secrets

---

## 13. Ops cheat sheet

```bash
# Restart your bot only
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-BOT-operator

# Logs
tail -f ~/logs/rocketchat-BOT-wake/operator-agent.log

# Public workspace (phone)
# host only: velocityworks-rc.ngrok.app  (see ROCKETCHAT.md)

# Local
open http://127.0.0.1:3000
```

---

## 14. Pitfalls (learned the hard way)

| Pitfall | What happens | Fix |
| --- | --- | --- |
| Two operators, one RC user | Token/session fights, missing messages | Unique username + secrets per process |
| Shared secrets file | Wrong bot posts / auth thrash | `RC_SECRETS_PATH` dedicated file |
| Shared `state.json` | Session/cwd pin corruption | `RC_STATE_PATH` or backend default separate file |
| `RC_REQUIRE_MENTION` off in dual-bot channels | Both bots answer every line | Set `1` + scope `channels` on **all** bots in shared rooms |
| Using Grok `acceptEdits` headless | Empty reply file / Cancelled | Grok restricted uses `--permission-mode auto` |
| Hermes without `-Q` | Noisy UI capture | Use quiet headless flags |
| Posting answer via REST from the model | Duplicate bubbles | Reply file only |
| Double `rooms.mediaConfirm` | Two image bubbles on RC 8.6 | Only `rc_post_media.py` |
| Thrashing `kickstart` | HTTP 429 from RC | Wait; KeepAlive reconnects |
| Leading `/` commands in app | rocket.cat steals them | Use `!` prefix |
| Printing secrets in agent chat | Credential leak | Paths/names only |

---

## 15. Reference paths

| Need | Path |
| --- | --- |
| Runtime compose + code | `~/.grok/agency/ops/rocketchat/` |
| Shared operator | `…/wake/rc_operator_agent.py` |
| Shared helpers | `…/wake/wake_lib.py` |
| Media helper | `…/wake/rc_post_media.py` |
| Control plane | `…/wake/rc_commands.py` |
| Channel→cwd map | `…/wake/channel_projects.json` |
| Grok reply prompt | `…/wake/reply_prompt.txt` |
| Hermes reply prompt | `…/wake/hermes_reply_prompt.txt` |
| Hermes runbook | `…/HERMES_OPERATOR.md` |
| No-dup rule | `…/NO_DUPLICATE_POSTS.md` |
| Canonical ops runbook | `~/.grok/agency/ops/ROCKETCHAT.md` |
| This docs repo | `~/IdeaProjects/rocketchat-agents/` |
| Config example env names | `…/config.example` |

---

## 16. Minimal success definition

You are done when **all** of the following are true:

1. RC user `<bot>` exists and logs in.
2. Dedicated secrets file mode `600`; operator process uses it.
3. launchd KeepAlive process online; log shows `operator=<bot>` and `require_mention=1`.
4. Principal DM free-wake returns a correct one-bubble answer.
5. Untagged channel message → `skip no_operator_mention` (no bubble).
6. `@bot` channel message → one bubble final answer.
7. Grok and Hermes operators still healthy.

---

## 17. What not to promise

- Native Hermes Gateway Rocket.Chat adapter (unsupported; this custom operator is the path).
- Drop-in voice/Call parity (WIP; leave alone unless principal scopes it).
- Multi-bot collab routing beyond simple @mention free-for-all (agy dual-peer is a separate NF-SPEC).
- Sharing one Grok session / Hermes session across bot users.

---

## 18. Hand-off blurb (paste to the next agent)

```text
Set up as a Rocket.Chat bot on the Velocity Works stack.
Follow: ~/IdeaProjects/rocketchat-agents/docs/agent-integration-guide.md
Runtime: ~/.grok/agency/ops/rocketchat/
Create unique RC user + secrets (mode 600) + logs + state + launchd.
Use rc_operator_agent.py with isolated RC_SECRETS_PATH / RC_LOG_DIR / RC_STATE_PATH.
Enable RC_REQUIRE_MENTION=1 and RC_REQUIRE_MENTION_SCOPE=channels.
Do not touch Grok/Hermes secrets or kill their launchd agents.
Skip Voice/Call. Verify DM smoke + channel untagged-skip + @bot tagged wake.
Never print secrets. Never double-post answers; reply file + operator chat.update only.
```

*End of guide.*
