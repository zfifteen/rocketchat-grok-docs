# Filesystem map

**Last reviewed:** 2026-07-17  
**Machine:** principal Mac (`HOME=/Users/velocityworks`)  
**Code model:** **Stage 2** — canonical source in git `ops/rocketchat/`; live = deploy target

Paths use `~` for the principal home. Expand to absolute form in launchd plists.

---

## 1. Documentation + canonical ops (this project)

| Path | Role |
| --- | --- |
| `~/IdeaProjects/rocketchat-agents/` | Docs map + **Stage 2 canonical** integration code |
| `…/README.md` | Entry point |
| `…/ops/rocketchat/` | **Write source** for operators, compose examples, tests |
| `…/ops/rocketchat/scripts/after-merge-deploy.sh` | Deploy git → live + kickstart |
| `…/docs/` | Architecture, map, ops, related systems |
| `…/docs/improvements/` | Ranked backlog; per-item requirements + test plans ([INDEX](improvements/INDEX.md)) |

---

## 2. Agency spine (continuity, not RC-specific)

| Path | Role |
| --- | --- |
| `~/.grok/agency/` | Canonical agency continuity home |
| `…/START_HERE.md` | Bootstrap for “resume agency” |
| `…/STATE.md` | Live mandate / next action |
| `…/CHARTER.md`, `LEDGER.md`, `INVALIDATED.md`, `OFFER.md` | Program rules & history |
| `…/ops/ROCKETCHAT.md` | **Runtime** RC + mobile runbook (ops status) |
| `…/ops/NGROK.md` | Tunnel plan / domain notes |
| `…/ops/PATHS.md` | Monetization path notes (not filesystem paths) |
| `…/ops/OPERATOR_LOOP.md` | Operator work style |

DM default Grok `--cwd` is `~/.grok/agency`.

---

## 3. Integration software (live deploy target)

**Canonical edit path:** `~/IdeaProjects/rocketchat-agents/ops/rocketchat/`  
**Live root (deploy only):** `~/.grok/agency/ops/rocketchat/`

Do **not** day-to-day edit live; use `after-merge-deploy.sh` after git merge.

| Path | Role |
| --- | --- |
| `docker-compose.yml` | Rocket.Chat 8.6 + MongoDB replica set (`agency-rocketchat`) |
| `.env` | Compose secrets/overrides (mode restricted; not for git) |
| `run_ngrok.sh` | Tunnel launcher used by launchd |
| `enable_conference_calls.sh` | Jitsi / VideoConf admin settings |
| `NO_DUPLICATE_POSTS.md` | Hard rule: one bubble, one media confirm |
| **`wake/`** | Text/media operator bridge |
| `wake/rc_operator_agent.py` | **Primary** WebSocket operator (presence + wake) |
| `wake/wake_lib.py` | Shared env load, room→cwd mapping, helpers |
| `wake/rc_post_media.py` | Idempotent image/file post helper |
| `wake/rc_dm_poll.py` | Optional poll-based wake (backup; usually off) |
| `wake/run_operator_agent.sh` | launchd entry for operator |
| `wake/run_poll.sh` | launchd entry for poll backup |
| `wake/reply_prompt.txt` | System prompt injected into every Grok wake |
| `wake/channel_projects.json` | Channel name → project path overrides |
| `wake/state.json` | Runtime pins (e.g. `grok_cwds` session cwd pins) |
| **`call/`** | Path C: Jitsi / speak-as-Grok call bot |
| `call/rc_call_bot.py` | Join conference as `grok`, TTS/STT loop |
| `call/run_call_bot.sh` | Wrapper |
| `call/README.md` | Call bot notes |
| **`tests/`** | Integration + usability contracts |
| `tests/test_rc_integration.py` | Env, wake safety, optional live smoke |
| `tests/test_usability_contracts.py` | Contract tests (incl. IMP-15 generate/backup) |
| `tests/USABILITY_CONTRACTS.md` | Written contracts (incl. no-duplicate) |
| **`scripts/`** | Ops helpers (IMP-15 and others) |
| `scripts/generate_compose_env.sh` | Secrets → compose `.env` (mode 600) |
| `scripts/backup_mongo.sh` | Mongo Docker volume backup tarball |
| `scripts/prune_logs.py` | Aged wake/call log prune |
| `scripts/rc_health_check.sh` | Operator health.json gate |
| `config.example` / `.env.example` | Placeholder templates (no real secrets) |
| `install-launchd.sh` | Render launchd from `templates/*.plist.tmpl` |

Hard-coded defaults in Python (overridable only where env vars exist):

- Agency: `~/.grok/agency`
- Secrets: `~/.grok/agency/secrets/rocketchat.env`
- Logs: `~/logs/rocketchat-dm-wake`
- Grok binary: `~/.local/bin/grok` (or `GROK_BIN`)
- IdeaProjects: `~/IdeaProjects`

---

## 4. Secrets

| Path | Role |
| --- | --- |
| `~/.grok/agency/secrets/` | Local secrets directory (mode 700) |
| `…/README.md` | What each file is for |
| `…/rocketchat.env` | RC base URL, `principal` / `grok` credentials, related keys |
| `…/ngrok.env` | Domain + authtoken mirror |
| `…/twilio.env` | SMS bridge (adjacent, not RC core) |
| `…/moltbook.env` | Unrelated agency product secrets |

**Rules:** never commit, never paste into chat, never copy into this docs repo.

Also:

| Path | Role |
| --- | --- |
| `~/Library/Application Support/ngrok/ngrok.yml` | ngrok agent config (authtoken) |
| `~/.grok/agency/ops/rocketchat/.env` | Docker Compose env for first-run admin |

---

## 5. Always-on processes (launchd)

| Plist | Label | Starts | Default |
| --- | --- | --- | --- |
| `~/Library/LaunchAgents/com.velocityworks.rocketchat-operator.plist` | `com.velocityworks.rocketchat-operator` | `wake/run_operator_agent.sh` → grok | **KeepAlive on** |
| `~/Library/LaunchAgents/com.velocityworks.rocketchat-hermes-operator.plist` | `…-hermes-operator` | `wake/run_hermes_operator_agent.sh` | **KeepAlive on** |
| `~/Library/LaunchAgents/com.velocityworks.rocketchat-agy-operator.plist` | `…-agy-operator` | `wake/run_agy_operator_agent.sh` | **KeepAlive on** |
| `~/Library/LaunchAgents/com.velocityworks.rocketchat-claude-operator.plist` | `…-claude-operator` | `wake/run_claude_operator_agent.sh` | **KeepAlive on** |
| `~/Library/LaunchAgents/com.velocityworks.ngrok-rocketchat.plist` | `com.velocityworks.ngrok-rocketchat` | `run_ngrok.sh` | **KeepAlive on** |
| `~/Library/LaunchAgents/com.velocityworks.rocketchat-dm-wake.plist` | `com.velocityworks.rocketchat-dm-wake` | poll path | **Disabled by default** (backup; was lag source) |

Plists currently hardcode absolute paths under `/Users/velocityworks/…`.

---

## 6. Logs and runtime ledgers

| Path | Role |
| --- | --- |
| `~/logs/rocketchat-dm-wake/` | Grok operator / poll / call / media root |
| `~/logs/rocketchat-hermes-wake/` | Hermes operator logs |
| `~/logs/rocketchat-agy-wake/` | Antigravity (`agy`) operator logs |
| `~/logs/rocketchat-claude-wake/` | Claude operator logs |
| `…/operator-agent.log` | Main operator application log (per log dir) |
| `…/operator-agent.stdout.log` / `.stderr.log` | Process streams |
| `…/operator-launchd.*.log` | launchd wrapper streams |
| `…/media-post-ledger.json` | Idempotency ledger for media posts |
| `…/audio/` | Voice-note STT cache (Path A) |
| `…/call-bot.log`, `call-bot.spawn.log` | Call bot |
| `…/call-media/` | Call audio chunks |
| `…/wake.lock.d/` | Single-flight wake locks |
| `…/wake-prompt-*.txt` | Debug captures of wake prompts |
| `…/poll.log` | Poll backup log |
| `~/logs/ngrok-rocketchat/` | Tunnel launchd logs |

---

## 7. Docker / data plane

| Item | Role |
| --- | --- |
| Compose project name | `agency-rocketchat` |
| Working directory for compose | `~/.grok/agency/ops/rocketchat/` |
| Image | `registry.rocket.chat/rocketchat/rocket.chat:8.6.0` |
| Mongo volume | Docker named volume `mongodb_data` (see compose) |
| Host port | `3000` → RC |

---

## 8. External binaries (dependencies)

| Path / tool | Role |
| --- | --- |
| `~/.local/bin/grok` | Grok CLI invoked on each wake (`GROK_BIN`) |
| `~/.grok/bin/` | On PATH for operator shell |
| `/opt/homebrew/bin/ngrok` | Tunnel agent |
| `whisper` (or `RC_WHISPER_BIN`) | Local STT for voice notes |
| Docker Desktop | Runs RC + Mongo |

---

## 9. Channel → project workspaces

| Rule | Path |
| --- | --- |
| DMs only | `~/.grok/agency` |
| Channel/group default | `~/IdeaProjects/<slug>` (created if missing) |
| Overrides | `…/wake/channel_projects.json` |
| Session pins | `…/wake/state.json` → `grok_cwds` |

Example override (live): `Prime-Gap-Structure` → `prime-gap-structure`  
→ `~/IdeaProjects/prime-gap-structure/`.

Auto-created channel folders may only contain a small README until work lands there
(e.g. `~/IdeaProjects/agency/`, `~/IdeaProjects/general/`).

---

## 10. Related consumers (not the bridge)

| Path | Role |
| --- | --- |
| `~/IdeaProjects/prime-gap-structure/scripts/pgs_hourly_rocketchat_notify.py` | Posts hourly research memos to RC as `grok` |
| Same secrets file | `~/.grok/agency/secrets/rocketchat.env` |
| Contract | `…/prime-gap-structure/research/00-index/continuity/HOURLY_RELAY_CONTRACT.md` |

PGS must not wake the operator path for notify; it is a separate REST poster.

---

## 11. Tree sketch (runtime only)

```
~/.grok/agency/
├── START_HERE.md, STATE.md, …
├── secrets/
│   ├── rocketchat.env
│   └── ngrok.env
└── ops/
    ├── ROCKETCHAT.md
    ├── NGROK.md
    └── rocketchat/
        ├── docker-compose.yml
        ├── run_ngrok.sh
        ├── wake/          # operator + media
        ├── call/          # Jitsi bot
        └── tests/

~/Library/LaunchAgents/
├── com.velocityworks.rocketchat-operator.plist
├── com.velocityworks.rocketchat-hermes-operator.plist
├── com.velocityworks.rocketchat-agy-operator.plist
├── com.velocityworks.rocketchat-claude-operator.plist
├── com.velocityworks.ngrok-rocketchat.plist
└── com.velocityworks.rocketchat-dm-wake.plist   # usually off

~/logs/rocketchat-dm-wake/     # grok + media + call
~/logs/rocketchat-hermes-wake/
~/logs/rocketchat-agy-wake/
~/logs/rocketchat-claude-wake/
~/logs/ngrok-rocketchat/       # tunnel

~/IdeaProjects/
├── rocketchat-agents/      # THIS documentation project
├── prime-gap-structure/       # example channel project + hourly notify
└── <other channel slugs>/
```
