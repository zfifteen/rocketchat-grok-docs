# Rocket.Chat Agents

![Rocket.Chat Agents](docs/assets/hero-banner.jpg)

# Features & benefits

**Turn Rocket.Chat into your always-on, phone-reachable multi-agent command center.**  
Staff a living roster of specialized AI operators—each a first-class chat identity with its own model, tools, and project workspace—then run them as a coordinated team from your laptop or phone. Tag who you need, watch work stream in real time, hand tasks across operators with structured multi-round collaboration, and keep every channel rooted in the real codebase it owns.

This is agent workforce infrastructure on the chat surface you already use: parallel rooms, durable sessions, production-grade deploy discipline, and collaboration built for sustained delivery.

## What makes it stand out

- **First-class operator identities** — Every bot (`grok`, `hermes`, `agy`, peers such as `nie` / `feynman`, …) is a real Rocket.Chat user with its own WebSocket bridge, isolated secrets, state, logs, and launchd KeepAlive. Mentions, reactions, and room membership feel like staffing a team—because you are.

- **Multi-round collaboration as a first-class protocol** — Lead assigns, peers deliver, quality-gated return-notify synthesizes, and a clean `DONE` closes the epoch. Shared rooms become long-horizon multi-agent workspaces that compound.

- **Project-aware execution at the core** — Every channel maps to a real directory (`~/IdeaProjects/<slug>` or your agency spine). Operators spawn with the correct `--cwd` and ship against the tree you care about.

- **A wake UX that matches the pace of real work** — Streaming thinking/working phases in a single answer bubble, busy-aware acknowledgment with ordered follow-up enqueue, per-room serial depth + cross-room parallelism (default **16**), and a strict one-answer-bubble rule.

- **Production-grade ops discipline** — Git is the canonical source (Stage 2). Live host is deploy-only. Pure tests are merge gates, parity checks are automated, and `after-merge-deploy.sh` is a repeatable path from laptop to running system.

- **One repository for product and runtime** — Specs, research, implementation plans, test plans, ranked improvements, heavy reviews, and the integration code live together so intent and implementation stay aligned.

## Core features

| Feature | Benefit |
| --- | --- |
| **Multi-operator roster** | Distinct bots with their own identities, backends, secrets, and launchd processes—ready on day one |
| **Tag-to-talk + peer wake** | `@bot` brings the right mind into the thread; peers can wake each other (`RC_PEER_TAG_WAKE` default on) |
| **Multi-round collaboration** | Structured lead → fan-out → gated return-notify → `DONE` close-out for reliable multi-hop delivery |
| **Streaming activity chrome** | Live thinking / working phases resolve into one polished final reply |
| **Busy-aware UX** | Mid-wake messages receive visible acknowledgment and orderly enqueue so the room stays responsive |
| **Per-room parallel wakes** | Ordered depth inside a room; true cross-room parallelism so DMs, project channels, and Agency all move at once |
| **Project-aware cwd** | Channels map to `~/IdeaProjects/<slug>` (or pinned paths); every wake lands in the matching filesystem |
| **Readable attachments** | Photos and files download under policy and are injected into the wake prompt for grounded `read_file` |
| **Phone-reachable edge** | Local Rocket.Chat + HTTPS (ngrok) puts your entire agent team in your pocket |
| **Git-canonical operations** | Integration code lives here; live host is deploy-only with parity checks and one-command promote |
| **Control plane & health** | In-chat commands and health cards for status and operator control without leaving Rocket.Chat |
| **Feature + improvement packs** | Full research → spec → implementation plan → test plan bundles ship beside the code |

**Voice / RC Call paths are retired.** See [`docs/VOICE_RETIRED.md`](docs/VOICE_RETIRED.md).

## Built for

- **Principals** who want a permanent multi-agent workforce on one Mac, reachable from phone or laptop through Rocket.Chat.
- **Agent builders** who need to add new operators (RC user + secrets + launchd + tag-to-talk + backend) and plug them into an existing roster quickly.
- **Reviewers and operators** who want pure test gates, deploy parity, and confidence when promoting changes to the live host.

---

# Technicals

## Overview

| Field | Value |
| --- | --- |
| **Project** | `rocketchat-agents` |
| **Local path** | `~/IdeaProjects/rocketchat-agents/` |
| **GitHub** | https://github.com/zfifteen/rocketchat-agents |
| **Canonical ops code** | [`ops/rocketchat/`](ops/rocketchat/) |
| **Live deploy target** | `~/.grok/agency/ops/rocketchat/` |
| **Runtime runbook** | `~/.grok/agency/ops/ROCKETCHAT.md` |
| **Stage model** | **Stage 2** — git is write source; live is deploy-only |
| **Call / voice** | Retired — see [`docs/VOICE_RETIRED.md`](docs/VOICE_RETIRED.md) |

**Edit integration code under [`ops/rocketchat/`](ops/rocketchat/).** Deploy with:

```bash
./ops/rocketchat/scripts/after-merge-deploy.sh
```

Secrets, state, logs, venv, and installed LaunchAgents stay on the host under `~/.grok/agency/` (and related OS paths). Never commit them.

## Architecture (one screen)

```
Phone / browser
    │  HTTPS (ngrok)
    ▼
Rocket.Chat (Docker on localhost:3000)
    │  WebSocket + REST as grok | hermes | agy | peers…
    ▼
rc_operator_agent.py  (one launchd KeepAlive PER bot)
    │  👀 + activity bubble → spawn that bot’s CLI → chat.update
    ▼
CLI  (--cwd agency or ~/IdeaProjects/<channel>)
```

| Component | Implementation | Runs as |
| --- | --- | --- |
| Chat server | Docker Compose | containers |
| Public edge | ngrok (multi-tunnel capable) | launchd KeepAlive |
| Operator bridge (×N) | `wake/rc_operator_agent.py` | one launchd per bot |
| Shared helpers | `wake/wake_lib.py`, pure IMP modules | imported |
| Media posts | `wake/rc_post_media.py` | subprocess |
| LLM / tools | Grok / Hermes / Antigravity / … CLIs | child of that bot’s operator |

**Accounts:** principal = human admin; bots = operator usernames.  
**Shared rooms:** tag-to-talk (`@bot`). **Peer tags:** `RC_PEER_TAG_WAKE` (default on).  
**Concurrency:** per-room serial, cross-room parallel (`RC_WAKE_MAX_CONCURRENT`, default **16**).  
**Standing rule:** one answer bubble — see `ops/rocketchat/NO_DUPLICATE_POSTS.md`.

Full component map: [docs/architecture.md](docs/architecture.md).  
Message paths: [docs/message-flow.md](docs/message-flow.md).

## Repository layout

```
rocketchat-agents/
├── README.md                 ← this file
├── CHANGELOG.md
├── LICENSE
├── docs/                     ← architecture, ops, maps, improvements, reviews
│   ├── assets/hero-banner.jpg
│   ├── improvements/         ← ranked IMP backlog (requirements + test plans)
│   ├── goals/
│   └── reviews/
├── new-features/             ← product feature packs (research/spec/TP/IP)
├── ops/rocketchat/           ← Stage 2 canonical integration code
│   ├── wake/                 ← operator agent, wake_lib, collab, pure policy
│   ├── tests/                ← pure + integration suites
│   ├── scripts/              ← deploy, parity, reclaim, digest, backup
│   ├── templates/            ← launchd plist templates
│   ├── docker-compose.yml
│   ├── config.example
│   └── MULTI_OPERATOR.md
└── tests/                    ← repo-level structural / feature-doc tests
```

### Where each kind of thing lives

| Kind | Home | Why |
| --- | --- | --- |
| Integration code (**canonical**) | [`ops/rocketchat/`](ops/rocketchat/) | Write source; PR + review |
| Integration code (**live**) | `~/.grok/agency/ops/rocketchat/` | launchd cwd, state, venv — deploy only |
| Continuity / mandate | `~/.grok/agency/` | Agency program spine |
| Secrets | `~/.grok/agency/secrets/` | Mode 600; never git |
| Always-on jobs | `~/Library/LaunchAgents/` | macOS launchd |
| Logs / ledgers | `~/logs/rocketchat-*-wake/` | Long-running I/O |
| Channel workspaces | `~/IdeaProjects/<slug>/` | CLI `--cwd` |
| This project | `~/IdeaProjects/rocketchat-agents/` | Docs + canonical ops |

Detail: [docs/filesystem-map.md](docs/filesystem-map.md). Ops model: [ops/rocketchat/README.md](ops/rocketchat/README.md).

## Quick start (operators & contributors)

### 1. Read the map

1. [docs/filesystem-map.md](docs/filesystem-map.md) — where everything is  
2. [docs/architecture.md](docs/architecture.md) — components  
3. [docs/message-flow.md](docs/message-flow.md) — DM / channel paths (Call/voice retired)  
4. [docs/operations.md](docs/operations.md) — status, restart, tests, common fixes  
5. [docs/agent-integration-guide.md](docs/agent-integration-guide.md) — add a new RC operator  
6. [docs/multi-round-collab.md](docs/multi-round-collab.md) — lead / return-notify / DONE  
7. [ops/rocketchat/MULTI_OPERATOR.md](ops/rocketchat/MULTI_OPERATOR.md) — live roster notes  

### 2. Develop in git (Stage 2)

```bash
cd ~/IdeaProjects/rocketchat-agents

# edit under ops/rocketchat/
# run pure gates (no RC network)
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py
python3 ops/rocketchat/tests/test_wake_ux_imp23.py
python3 ops/rocketchat/tests/test_wake_denials_imp22.py
python3 ops/rocketchat/tests/test_multi_round_collab.py
python3 ops/rocketchat/tests/test_imp_b_stream_intentional.py

# commit / PR / merge to main
./ops/rocketchat/scripts/after-merge-deploy.sh   # deploy + parity + kickstart
```

`after-merge-deploy.sh` = `deploy-mirror-to-live.sh` + `check-mirror-parity.sh` + operator kickstart.

### 3. Emergency host hotfix only

If you must edit live under fire:

```bash
./ops/rocketchat/scripts/sync-mirror-from-live.sh
git add ops/rocketchat && git commit -m "sync: host emergency fix"
# treat git as truth again immediately
```

Do **not** rsync `.env`, state JSON, PEMs, or `.venv/` into git.

## Configuration surfaces

| Surface | Purpose |
| --- | --- |
| `~/.grok/agency/secrets/rocketchat.env` (+ per-bot env) | URLs, usernames, tokens/passwords |
| `ops/rocketchat/config.example` | Documented knobs (copy/adapt on host) |
| `ops/rocketchat/.env.example` | Compose-related examples |
| `wake/channel_projects.json` | Channel name → project path map |
| `wake/*_state.json` (live only) | Sessions, pending wakes, in-flight, cwd pins |
| LaunchAgent plists | Per-bot KeepAlive + env |

Document **paths and variable names** only in git — never secret values.

### Notable runtime knobs

| Knob | Intent |
| --- | --- |
| `RC_PEER_TAG_WAKE` | Peer @mentions can wake (default on) |
| `RC_WAKE_MAX_CONCURRENT` | Cross-room parallelism (default **16**) |
| `RC_WAKE_STREAM` / stream throttle vars | Activity bubble streaming |
| `RC_MULTI_ROUND_*` | Collab lead-only open, etc. |
| `RC_CALL_ENABLED` / `RC_PUBLIC_VOICE` | **Off** — Call retired |
| `RC_AUTO_CREATE_PROJECTS` | Auto-create missing channel project dirs |

## Testing

| Kind | Where | Notes |
| --- | --- | --- |
| Pure policy (no network) | `ops/rocketchat/tests/test_wake_*.py`, `test_multi_round_collab.py`, `test_imp_b_*.py` | Preferred merge gates |
| Feature / integration | `ops/rocketchat/tests/test_nf*.py`, `test_rc_integration.py` | May need venv + mocks |
| Usability contracts | `ops/rocketchat/tests/test_usability_contracts.py` | Prefer live venv Python |
| Live smoke | `live_four_agent_collab_smoke.py` | Opt-in env flags |
| Doc structure | repo-root `tests/` | Feature pack layout, etc. |

Live operators use `~/.grok/agency/ops/rocketchat/.venv` — bare Framework `python3` may miss deps (e.g. `websocket-client`).

## Operations cheat sheet

| Need | Path / command |
| --- | --- |
| Ops runbook | `~/.grok/agency/ops/ROCKETCHAT.md` |
| After-merge deploy | `./ops/rocketchat/scripts/after-merge-deploy.sh` |
| Parity check | `./ops/rocketchat/scripts/check-mirror-parity.sh` |
| Reclaim stuck wakes | `./ops/rocketchat/scripts/reclaim-stuck-wake-state.sh` |
| Wake digest | `python3 ops/rocketchat/scripts/rc_wake_digest.py --hours 24` |
| Operator agent | `ops/rocketchat/wake/rc_operator_agent.py` |
| Shared lib | `ops/rocketchat/wake/wake_lib.py` |
| Secrets | `~/.grok/agency/secrets/rocketchat.env` |
| Operator logs | `~/logs/rocketchat-*-wake/operator-agent.log` |
| Agency spine | `~/.grok/agency/START_HERE.md` |

Day-to-day ops narrative: [docs/operations.md](docs/operations.md).  
Related adjacency (agency, notify, Twilio): [docs/related-systems.md](docs/related-systems.md).

## Product & backlog indexes

| Index | Contents |
| --- | --- |
| [new-features/README.md](new-features/README.md) | Feature packs 02+ (streaming, control plane, collab, attachments, …). **01 voice Call = RETIRED** |
| [docs/improvements/INDEX.md](docs/improvements/INDEX.md) | Ranked IMP items with requirements + test plans |
| [docs/reviews/](docs/reviews/) | Heavy review findings and phase plans |
| [docs/goals/install-refactor-then-public-share.md](docs/goals/install-refactor-then-public-share.md) | Parked program: local install polish before public package |
| [docs/multi-round-collab.md](docs/multi-round-collab.md) | Multi-round collab protocol + deploy notes |

Improvements layout:

| Entry | Description |
| --- | --- |
| `docs/improvements/INDEX.md` | Ranked list, phased |
| `docs/improvements/NN-*/README.md` | Summary + nav |
| `…/requirements.md` | Goals, requirements, acceptance |
| `…/test-plan.md` | Verification cases |

## Stage history

| Stage | Model |
| --- | --- |
| **0** | Code only under `~/.grok/agency` |
| **1** | Expanded reviewable mirror; live still co-edited |
| **2 (current)** | **Git canonical**; live = deploy target |
| **3** | Run from repo — **rejected** |

## Maintaining this project

When the live stack or product surface moves:

1. Change code under `ops/rocketchat/` (or docs under `docs/` / `new-features/`).
2. Add/adjust pure tests; keep merge gates green.
3. Merge → `./ops/rocketchat/scripts/after-merge-deploy.sh`.
4. Bump **Last reviewed** on touched doc files when practical.
5. Note user-visible shifts in [CHANGELOG.md](CHANGELOG.md).

Keep secrets out of this repo. Document only paths and variable names.

## License

See [LICENSE](LICENSE).
