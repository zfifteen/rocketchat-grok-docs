# Rocket.Chat ↔ Grok — documentation map

![Rocket.Chat ↔ Grok — documentation map](docs/assets/hero-banner.jpg)

**Scope:** This is a read-only documentation map of the working Rocket.Chat +
Grok integration on this Mac: message flow, processes, and **where every piece
lives on disk**. Runtime code, secrets, and agency continuity live under
`~/.grok/agency/` (and related OS paths). This repo documents those locations
so the stack stays navigable.

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
3. **[Message flow](docs/message-flow.md)** — DM / channel paths (Call/voice **retired**)  
4. **[Operations](docs/operations.md)** — status, restart, tests, common fixes  
5. **[Related systems](docs/related-systems.md)** — agency spine, PGS hourly notify, Twilio  
6. **[Multi-agent integration guide](docs/agent-integration-guide.md)** — **for other agents:** create RC user, secrets, parallel operator, tag-to-talk, launchd, verify  
6a. **[Multi-round collab](docs/multi-round-collab.md)** — Grok lead, return-notify, principal open = `@grok` only, quality-gated hops (issue [#2](https://github.com/zfifteen/rocketchat-grok-docs/issues/2); mirror [`ops/rocketchat/`](ops/rocketchat/))  
7. **[Improvements backlog](docs/improvements/INDEX.md)** — ranked suggestions; each has requirements + test plan  
8. **[Code review findings (2026-07-14)](docs/reviews/2026-07-14-rc-integration-heavy-review.md)** — Heavy review backlog (crash safety, media, **C1 voice retired 2026-07-17**, docs drift)  
9. **[Goal: install refactor → public share](docs/goals/install-refactor-then-public-share.md)** — **parked program** (local config first, package later; not started)  
10. ~~Voice call plans~~ — **retired**; historical only: [implementation-plan-voice-calls.md](docs/implementation-plan-voice-calls.md), [research-voice-media-path.md](docs/research-voice-media-path.md)  
11. **[New features index](new-features/README.md)** — **01 voice Call = RETIRED**; active product features start at **02+** (streaming, control plane, collab, attachments, …)

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
    │  WebSocket + REST as grok | hermes | agy | claude
    ▼
rc_operator_agent.py  (one launchd KeepAlive PER bot)
    │  👀 + activity → spawn that bot’s CLI → chat.update
    ▼
CLI  (--cwd agency or ~/IdeaProjects/<channel>)
```

**Accounts:** you = `principal`; bots = `grok`, `hermes`, `agy`, `claude`.  
**Shared rooms:** tag-to-talk (`@bot`). **Peer tags:** any author @mention can wake (`RC_PEER_TAG_WAKE=1`).  
**Roster:** `~/.grok/agency/ops/rocketchat/MULTI_OPERATOR.md`.  
**Public URL (phone):** see `~/.grok/agency/ops/ROCKETCHAT.md` (ngrok domain).  
**Local URL:** `http://localhost:3000`.

---

## Where each piece lives

| Kind of thing | Typical home | Why this home |
| --- | --- | --- |
| Integration code (**live**) | `~/.grok/agency/ops/rocketchat/` | launchd cwd, state, venv next to continuity |
| Integration code (**git mirror**, Option 1) | [`ops/rocketchat/`](ops/rocketchat/) in this repo | PR review; deploy via `scripts/deploy-mirror-to-live.sh` |
| Continuity / mandate | `~/.grok/agency/` | Source of truth for the agency program |
| Secrets | `~/.grok/agency/secrets/` | Mode 600; kept out of git |
| Always-on jobs | `~/Library/LaunchAgents/` | macOS launchd requirement |
| Logs / ledgers | `~/logs/rocketchat-dm-wake/` | Long-running process I/O |
| Channel workspaces | `~/IdeaProjects/<slug>/` | Grok works *in* project dirs |
| This documentation | `~/IdeaProjects/rocketchat-grok-docs/` | Stable map; live runtime stays under agency |

**Option 1 (current):** expand the reviewable mirror under `ops/rocketchat/` (code/examples/templates). Live remains agency; sync scripts never copy secrets/state/venv.  
**Option 2 (later decision):** git becomes canonical; deploy only to live.  
**Option 3 (run from repo):** off the table.

Secrets, launchd installs, logs, Docker volumes, and operator state stay out of git.

---

## Quick path cheat sheet

| Need | Path |
| --- | --- |
| Ops runbook | `~/.grok/agency/ops/ROCKETCHAT.md` |
| Compose + code root (live) | `~/.grok/agency/ops/rocketchat/` |
| Compose + code **mirror** | [`ops/rocketchat/`](ops/rocketchat/) |
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

Keep secrets out of this repo. Document only *paths* and *variable names*.
