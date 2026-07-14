# Architecture

**Last reviewed:** 2026-07-14

---

## Purpose

Give the principal a phone- and desktop-reachable Rocket.Chat workspace where
messages to **`grok`**, **`hermes`**, **`agy`**, or **`claude`** wake that bot’s
local CLI, with project-aware working directories, optional voice notes, and
optional conference call answer (Grok Call path).

---

## Components

```
┌─────────────────┐     HTTPS      ┌──────────────────┐
│ Phone / browser │ ─────────────► │ ngrok tunnel     │
└─────────────────┘                │ launchd KeepAlive│
                                   └────────┬─────────┘
                                            │ localhost:3000
                                   ┌────────▼─────────┐
                                   │ Rocket.Chat 8.6  │
                                   │ + Mongo (Docker) │
                                   └────────┬─────────┘
                          REST + WebSocket  │
                                   ┌────────▼─────────┐
                                   │ rc_operator_agent│
                                   │ user: grok       │
                                   │ launchd KeepAlive│
                                   └────────┬─────────┘
                    Thinking… / chat.update │
                                   ┌────────▼─────────┐
                                   │ Grok CLI         │
                                   │ --cwd project    │
                                   │ --resume session │
                                   └──────────────────┘
```

| Component | Implementation | Runs as |
| --- | --- | --- |
| Chat server | Docker Compose `agency-rocketchat` | containers |
| Public edge | ngrok Hobbyist domain | `com.velocityworks.ngrok-rocketchat` |
| Operator bridge (×N) | `wake/rc_operator_agent.py` | One launchd per bot (`…-operator`, `…-hermes-operator`, `…-agy-operator`, `…-claude-operator`) |
| Shared helpers | `wake/wake_lib.py` | imported |
| Media posts | `wake/rc_post_media.py` | subprocess from any bot wake |
| Call bot | `call/rc_call_bot.py` | Grok conference path only |
| LLM / tools | Grok / Hermes / Antigravity CLIs | child of that bot’s operator |
| Continuity cwd (DMs) | `~/.grok/agency` | bot CLI `--cwd` |
| Channel cwd | `~/IdeaProjects/<slug>` | bot CLI `--cwd` |

Roster: `ops/rocketchat/MULTI_OPERATOR.md`.

---

## Accounts and trust

| Role | RC username | Purpose |
| --- | --- | --- |
| Principal (you) | `principal` | Admin + human; free-wake DMs; tags bots in channels |
| Operator | `grok` | Grok Build CLI; media; Call join |
| Operator | `hermes` | Hermes CLI |
| Operator | `agy` | Antigravity (Gemini) CLI |
| Operator | `claude` | Antigravity backend + Claude model pin |

Credentials: **one secrets file per bot** under `~/.grok/agency/secrets/` (mode 600). Never share usernames across processes.

Wake filter (`should_enqueue_llm_wake`): not self; principal free-wake in DMs; shared rooms need `@bot`; **peer tag wake** (`RC_PEER_TAG_WAKE`, default on) allows any author who @mentions the bot. Same room → same session resume key per bot.

---

## Transport choices

| Path | Mechanism | Notes |
| --- | --- | --- |
| Primary wake | WebSocket realtime | Low latency; room membership re-scan ~60s |
| Backup wake | HTTP poll (`rc_dm_poll.py`) | launchd exists; **off by default** (lag) |
| Replies | 👀 on triggering msg + activity bubble (thought stream) then `chat.update` | **One answer bubble** — never a second answer post |
| Images | `rc_post_media.py` + ledger | Never double `rooms.mediaConfirm` |

Standing rule: `ops/rocketchat/NO_DUPLICATE_POSTS.md`.

---

## Project cwd policy

| Room type | Default cwd |
| --- | --- |
| Direct message | `~/.grok/agency` |
| Channel / group | `~/IdeaProjects/<slug>` (create if missing) |

Overrides: `wake/channel_projects.json`  
Pins: `wake/state.json` → `grok_cwds`

This is why “the integration” touches many IdeaProjects folders without living
inside each of them.

---

## Voice and call (feature paths)

| Path | Status (as of runbook) | Entry |
| --- | --- | --- |
| **A** Voice notes in DM | Wired: audio → Whisper → text wake | operator + `RC_WHISPER_*` |
| **B** Twilio phone bridge | Partial; not full STT/TTS into Grok | `ops/twilio/`, `secrets/twilio.env` |
| **C** RC Call media bot | **Live path:** VideoConf → lobby-free `voice_room` (`:8090`) + Playwright TTS/STT | `call/rc_call_bot.py`, `voice_room/` |
| **D (research / next)** | Native Grok Voice / LiveKit agent under same Call button | [research-voice-media-path.md](research-voice-media-path.md) |

Conference enable: `enable_conference_calls.sh` (Jitsi app + VideoConf settings).  
Production voice media strategy: **do not** treat Path C as the target — see research doc.

---

## Configuration surfaces

| Surface | What it configures |
| --- | --- |
| `secrets/rocketchat.env` | URLs, usernames, passwords / tokens |
| `ops/rocketchat/.env` | Compose `ADMIN_*`, `ROOT_URL` |
| `wake/reply_prompt.txt` | Operator behavior every wake |
| `wake/channel_projects.json` | Channel → path map |
| Env on operator process | `GROK_BIN`, `RC_BASE`, Whisper vars, room refresh |
| launchd plists | Absolute paths to scripts + log files |
| ngrok config | Public hostname |

There is no single config file for the whole system; see [filesystem-map](filesystem-map.md).

---

## Layout rationale

**Why under `~/.grok/agency`?**

- Built as road messaging for the **agency** program.
- DM work should land in the continuity spine by default.
- Secrets and ops docs already lived there.

**Why not only that tree?**

- launchd plists must sit in `~/Library/LaunchAgents/`.
- Logs for KeepAlive services belong under `~/logs/` (or similar), not mixed
  into agent state.
- Channel work is intentionally **other projects** under IdeaProjects.
- Docker volumes are owned by Docker.

**Is a dedicated app repo better later?**

Yes for *code versioning* (operator, call bot, compose, tests). No for stuffing
secrets + STATE + Mongo + all channel folders into one git tree. Hybrid:

- App repo = portable software + install script  
- `~/.grok/agency` = continuity + secrets + pointer docs  
- OS paths = launchd + logs  

This documentation project records the **current** layout until such a move.

**Tracked improvements:** [improvements/INDEX.md](improvements/INDEX.md)  
(including [IMP-16 extract code](improvements/16-extract-code-project/) and [IMP-03 single config](improvements/03-single-config-surface/)).

---

## Failure domains (what breaks what)

| If this is down… | Symptom |
| --- | --- |
| Docker / RC | Login fails; operator cannot connect |
| ngrok | Phone/public URL dies; localhost still works |
| Operator launchd | Messages sit unread; no Thinking… |
| Grok CLI / API | Thinking… stuck or error text in bubble |
| Whisper | Voice notes fail STT; text still works |
| Secrets file missing | Operator exits / cannot login as grok |

RC notify from PGS can fail independently of the operator (by design: non-fatal
to research jobs).
