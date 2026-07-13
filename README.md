# Rocket.Chat ↔ Grok — documentation map

![Rocket.Chat ↔ Grok — documentation map](docs/assets/hero-banner.jpg)

**What this is:** a read-only documentation project that explains the working
Rocket.Chat + Grok integration on this Mac: how messages flow, which processes
run, and **where every piece lives on disk**.

**What this is not:** the integration code itself. Runtime code, secrets, and
agency continuity still live under `~/.grok/agency/` (and related OS paths).
This repo only documents them so the spread is navigable.

| Field | Value |
| --- | --- |
| **Created** | 2026-07-10 |
| **Status** | Live stack documented as deployed on the principal Mac |
| **Canonical ops runbook (runtime)** | `~/.grok/agency/ops/ROCKETCHAT.md` |
| **This project** | `~/IdeaProjects/rocketchat-grok-docs/` |

---

## Start here

1. **[Filesystem map](docs/filesystem-map.md)** — where everything is  
2. **[Architecture](docs/architecture.md)** — components and responsibilities  
3. **[Message flow](docs/message-flow.md)** — DM / channel / voice / call paths  
4. **[Operations](docs/operations.md)** — status, restart, tests, common fixes  
5. **[Related systems](docs/related-systems.md)** — agency spine, PGS hourly notify, Twilio  
6. **[Improvements backlog](docs/improvements/INDEX.md)** — ranked suggestions; each has requirements + test plan  
7. **[Goal: install refactor → public share](docs/goals/install-refactor-then-public-share.md)** — **parked program** (local config first, package later; not started)  
8. **[Voice call implementation plan](docs/implementation-plan-voice-calls.md)** — Path C fix framing (historical / lab)  
9. **[Voice/media research path](docs/research-voice-media-path.md)** — **recommended** architecture (RC Call → SFU/agent → Grok Voice)  
10. **[Preflight voice test protocol](docs/preflight-voice-test-protocol.md)** — test **before** principal Call (T0–T2 agent-run; T5 you)  
11. **[New features index](new-features/README.md)** — one numbered subfolder per product feature (related docs co-located): **[01 voice Call](new-features/01-true-voice-in-rc-call/)**, **[02 streaming Thinking](new-features/02-streaming-thinking-telemetry/)**, **[03 phone control plane](new-features/03-phone-control-plane/)**, **[04 agy collab](new-features/04-agy-rocketchat-collab/)**, **[10 lead–peer full collab](new-features/10-lead-peer-full-collab/)** (**NF-SPEC-10**), **[05 reading attachments](new-features/05-reading-attachments/)**; docs only

---

## Improvements package

Configuration deep-dive backlog lives under **`docs/improvements/`**:

| Entry | Description |
| --- | --- |
| **[INDEX.md](docs/improvements/INDEX.md)** | All 20 items ranked by impact, phased A–D |
| `docs/improvements/NN-*/README.md` | One-line summary + nav |
| `docs/improvements/NN-*/requirements.md` | Goals, requirements, acceptance |
| `docs/improvements/NN-*/test-plan.md` | Verification cases |

Phase **A (safety)** first: [01 blast radius](docs/improvements/01-cap-blast-radius/), [02 wake lock](docs/improvements/02-wake-lock-ttl/), [07 secrets hygiene](docs/improvements/07-secrets-prompt-hygiene/).

---

## One-screen mental model

```
Phone / browser
    │  HTTPS (ngrok)
    ▼
Rocket.Chat (Docker on localhost:3000)
    │  WebSocket + REST as user "grok"
    ▼
rc_operator_agent.py  (launchd KeepAlive)
    │  Thinking… → spawn Grok CLI → chat.update
    ▼
Grok CLI  (--cwd agency or ~/IdeaProjects/<channel>)
```

**Accounts:** you = `principal`, bot = `grok`.  
**Public URL (phone):** see `~/.grok/agency/ops/ROCKETCHAT.md` (ngrok domain).  
**Local URL:** `http://localhost:3000`.

---

## Why files are spread out

| Kind of thing | Typical home | Why not all in one folder |
| --- | --- | --- |
| Integration code | `~/.grok/agency/ops/rocketchat/` | Built as agency ops, next to continuity |
| Continuity / mandate | `~/.grok/agency/` | Source of truth for the agency program |
| Secrets | `~/.grok/agency/secrets/` | Mode 600; not for git |
| Always-on jobs | `~/Library/LaunchAgents/` | macOS launchd requirement |
| Logs / ledgers | `~/logs/rocketchat-dm-wake/` | Long-running process I/O |
| Channel workspaces | `~/IdeaProjects/<slug>/` | Grok works *in* project dirs |
| This documentation | `~/IdeaProjects/rocketchat-grok-docs/` | Stable map without moving runtime |

A future refactor could move **code** into an IdeaProjects app repo; secrets,
launchd, logs, Docker volumes, and agency state would still stay outside.
See [architecture notes on layout](docs/architecture.md#layout-rationale).

---

## Quick path cheat sheet

| Need | Path |
| --- | --- |
| Ops runbook | `~/.grok/agency/ops/ROCKETCHAT.md` |
| Compose + code root | `~/.grok/agency/ops/rocketchat/` |
| Operator agent | `…/rocketchat/wake/rc_operator_agent.py` |
| Shared lib | `…/rocketchat/wake/wake_lib.py` |
| Secrets | `~/.grok/agency/secrets/rocketchat.env` |
| Operator launchd | `~/Library/LaunchAgents/com.velocityworks.rocketchat-operator.plist` |
| Operator log | `~/logs/rocketchat-dm-wake/operator-agent.log` |
| Agency spine | `~/.grok/agency/START_HERE.md` |

Full inventory: [docs/filesystem-map.md](docs/filesystem-map.md).

---

## Maintaining this project

When the live stack moves (new path, new launchd label, code extract):

1. Update the relevant file under `docs/`.
2. Bump the **Last reviewed** line in that file.
3. Optionally add a one-line note under [CHANGELOG.md](CHANGELOG.md).

Do **not** copy secrets into this repo. Document only *paths* and *variable names*.
