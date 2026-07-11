# Technical Specification: Antigravity (agy) dual-peer collab via Rocket.Chat channel

| Field | Value |
| --- | --- |
| **Spec ID** | NF-SPEC-04 |
| **Version** | 1.0 |
| **Status** | Specification documentation only — **implementation of this feature in the operator / call bot / launchd stack is out of scope for this document package** |
| **Date** | 2026-07-10 · **Last reviewed:** 2026-07-10 |
| **Prior research** | [`./research.md`](./research.md) · folder [`./`](./) |
| **Draft identity profiles** | [`./profiles/`](./profiles/) |
| **Test plan** | [`./test-plan.md`](./test-plan.md) (**NF-TP-04**) |
| **Implementation plan** | *(not yet — NF-IP-04 deferred; no implementation-plan.md in bundle yet)* |
| **Related** | NF-SPEC-02 (streaming per bubble), NF-SPEC-03 (control plane `/pause` `/status`), IMP-01 approval, `agy-cli-collab` skill, `NO_DUPLICATE_POSTS.md` |
| **Owner surface** | Collab-room mention dispatcher + dual RC identities + dual backends (Grok CLI + local `agy` CLI) |

---

## 1. Problem and context

### 1.1 Problem statement

The live Rocket.Chat ↔ Grok integration is a strong **principal → Grok** wake bridge. Separately, the global skill `agy-cli-collab` enables **Grok → Gemini** sticky CLI collaboration. There is no product surface where **Grok and Antigravity (Gemini) collaborate as peers over many turns** on a phone-visible Rocket.Chat floor, with attributable history, durable sessions, and principal supervision without sitting every hop.

Short nested “ask Gemini once” flows do not deliver the intended value. The feature exists to facilitate **long-horizon inter-agent collaboration** (tens to hundreds of turns over hours or days).

### 1.2 Context (live stack)

| Element | Current fact |
| --- | --- |
| Operator | `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` |
| Trust filter | Only RC username `principal` triggers wakes (`user != PRINCIPAL` → drop) |
| Bot identity | Single poster: `grok` (Thinking… → reply file → `chat.update`) |
| Continuity | Per-room Grok session pin + cwd via `wake/state.json` + `channel_projects.json` |
| Approval | IMP-01: restricted default (`--permission-mode auto`); channels often non-admin |
| Gemini path | Local `agy` CLI + skill `~/.grok/skills/agy-cli-collab/` (CLI-only; no MCP `agy_*`) |
| One-bubble rule | `NO_DUPLICATE_POSTS.md` — one answer bubble per answer wake for `grok` today |
| Gaps | No RC user `agy`; no mention-target routing; no durable agy conversation UUID in operator state; no dual-peer social contract loaded into Gemini |

### 1.3 Spec purpose

Define the **normative engineering contract** for dual-peer RC collab (research approach **C3** preferred), including mention wake, long-horizon durability, anti-runaway (not anti-depth), identity profiles, and integration with the live operator — **without implementing runtime code in this package**.

### 1.4 Builds on research

This specification **shall** be read with:

- Research: dual accounts + @mention turns; long-horizon value; C3 preferred over mediated monologue (C1).  
- Profiles: `agy-rc-collab.agent.md`, `agy-rc-collab.AGENTS.md`, `grok-rc-collab.inject.md` (L2 social contract drafts).

Where research options conflict, **this spec wins** for implementable requirements (C3 dual-peer presentation is normative).

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
| --- | --- |
| G1 | Principal can start and join a long multi-turn Grok↔agy dialogue from a private RC channel on phone. |
| G2 | Each agent posts **as its own RC identity** (`grok` vs `agy`); Gemini is never only a nested dump inside Grok. |
| G3 | **Tag-to-talk**: a wake occurs when a message **@mentions** the target agent (from principal or peer bot). |
| G4 | Bot↔bot auto-handoff works for **many, many turns** without principal re-prompting every hop. |
| G5 | Sessions (Grok pin + agy conversation UUID) and collab counters **survive** operator restart and Mac sleep. |
| G6 | Safety stops **runaway spin / cost**, not productive depth (soft epoch budgets + pause, not tiny hard hop caps). |
| G7 | Gemini backend remains **local `agy` CLI only** (skill contract; never MCP `agy_*`). |
| G8 | Durable identity profiles (L2) + per-turn inject (L3) + domain AGENTS (L1) load consistently. |

### 2.2 Non-goals

| ID | Non-goal |
| --- | --- |
| NG1 | Implementing this feature in the present documentation package. |
| NG2 | Multi-tenant public channels or non-allowlisted authors waking bots. |
| NG3 | MCP `agy_*` as a transport or fallback. |
| NG4 | Faking two voices from the single `grok` account (research C3-C). |
| NG5 | Nesting `agy` CLI inside Grok wakes as the **primary** collab UX in dual-account rooms. |
| NG6 | Replacing project domain `AGENTS.md` (e.g. PGS Lead Scientist) with RC transport rules. |
| NG7 | Full Apps-Engine slash UX as a v1 blocker (align Feature 3 operator-native first). |
| NG8 | Voice/Call dual-agent mode (Feature 1 orthogonal). |
| NG9 | Shipping Feature 4 test-plan / impl-plan as part of this specification goal. |

---

## 3. Normative requirements

### 3.1 Feature gate and room scope

| ID | Requirement |
| --- | --- |
| **FR-A0** | When collab mode is disabled for a room (no profile / master flag off), the operator **shall** retain today’s principal-only wake behavior for that room. |
| **FR-A1** | A room **shall** be treated as a collab room only when explicitly profiled (e.g. `mode=agy-collab` in room profile / map extension) **and** the master flag `RC_AGY_COLLAB` is enabled. |
| **FR-A2** | Collab bot↔bot wakes **shall not** apply to DMs or unprofiled channels by default. |
| **FR-A3** | Collab rooms **shall** be private and membership **shall** include at least `principal`, `grok`, and `agy` before dual-peer wakes are armed. |

### 3.2 Dual identities

| ID | Requirement |
| --- | --- |
| **FR-A4** | The system **shall** use distinct Rocket.Chat users **`grok`** and **`agy`** (bot users preferred). |
| **FR-A5** | Credentials for `agy` **shall** live in the secrets surface (e.g. alongside `rocketchat.env`); **shall not** be committed to git. |
| **FR-A6** | Posts attributed to Antigravity/Gemini **shall** be created and finalized using **`agy` authentication** (Thinking… and `chat.update` as `agy`). |
| **FR-A7** | Posts attributed to Grok **shall** continue to use **`grok` authentication** as today. |
| **FR-A8** | Implementation **shall not** synthesize dual voices under a single RC username (C3-C forbidden). |

### 3.3 Tag-to-talk mention wake

| ID | Requirement |
| --- | --- |
| **FR-A9** | In collab rooms, a wake **shall** be enqueued only when the message targets an agent via mention (structured `mentions[]` preferred; fallback `@username` word-boundary parse). Plain text without `@` **shall not** wake. |
| **FR-A10** | Allowed authors for collab wakes **shall** be the allowlist `{principal, grok, agy}` only. |
| **FR-A11** | Author `principal` + mention `agy` **shall** wake the **agy backend**; author `principal` + mention `grok` **shall** wake the **Grok CLI** path. |
| **FR-A12** | Author `grok` + mention `agy` **shall** wake the **agy backend** (handoff). Author `agy` + mention `grok` **shall** wake the **Grok CLI** path. |
| **FR-A13** | Self-mentions (e.g. `agy` mentioning only `agy`) **shall not** re-wake the same backend. |
| **FR-A14** | If principal mentions both `agy` and `grok` in one message, the operator **shall** either reject with a short help (“mention one target”) **or** run sequential wakes in deterministic order — choice is **OD-A1**; silent dual parallel wakes **shall not** occur. |
| **FR-A15** | Mention detection **shall** prefer RC `mentions` array when present; text fallback **shall** be case-insensitive for usernames `agy` and `grok`. |
| **FR-A16** | Bot replies intended to hand off **shall** include a **real** peer mention that the dispatcher can observe (lab **shall** verify REST `chat.postMessage` produces usable mentions on RC 8.6). |

### 3.4 Backend mapping and CLI-only Gemini

| ID | Requirement |
| --- | --- |
| **FR-A17** | Target `grok` **shall** invoke the existing Grok CLI wake path (`build_wake_argv` / `rc_operator_agent` family) with collab inject when in collab rooms. |
| **FR-A18** | Target `agy` **shall** invoke the local **`agy` CLI** (helper preferred: `~/.grok/skills/agy-cli-collab/scripts/agy_cli.py`) in print mode with pinned conversation when known. |
| **FR-A19** | The Gemini/agy backend path **shall not** call MCP tools `agy_ask`, `agy_ping`, `agy_models`, `agy_version`, or any other MCP `agy_*` API — including on CLI failure. |
| **FR-A20** | On `agy` CLI failure, the system **shall** finalize the **`agy`** Thinking bubble with an honest error (and **shall not** post fabricated Gemini content as success). |
| **FR-A21** | In dual-account collab rooms, Grok wakes **shall not** nest `agy` CLI to impersonate Gemini (inject **shall** forbid nested collab). |
| **FR-A22** | `agy` invocations **shall** be serialized globally (or at least per host); parallel `agy` subprocesses **shall not** run (skill serialize rule). |
| **FR-A23** | Per-turn `agy` print timeout **shall** be configurable (default recommendation **10m**); parent wake timeout for agy-target turns **shall** be ≥ print timeout + margin. |

### 3.5 Per-speaker one-bubble contract

| ID | Requirement |
| --- | --- |
| **FR-A24** | Each wake **shall** post exactly one Thinking… placeholder as the **target identity**, then **shall** finalize that same `msgId` via `chat.update` with the final body only. |
| **FR-A25** | The target identity **shall not** `chat.postMessage` a second copy of the same answer. |
| **FR-A26** | `NO_DUPLICATE_POSTS` **shall** be interpreted **per speaker per turn** in collab rooms (multiple speakers over time are required and allowed). |
| **FR-A27** | Final body source of truth **shall** be the reply file (or operator-captured `agy` stdout written to a reply file) after `compose_unified_reply`-equivalent stripping of Thinking prefixes. |
| **FR-A28** | Phase/streaming updates (NF-SPEC-02), when enabled, **shall** update **that turn’s** msgId only. |

### 3.6 Long-horizon durability and state

| ID | Requirement |
| --- | --- |
| **FR-A29** | Operator durable state **shall** store per collab room at least: `grok_session_id`, `agy.conversation_id`, collab `epoch`, `hop_count_epoch`, `hop_budget_epoch`, `total_hops`, `auto_handoff`, `paused_reason`, `last_speaker`, `last_hop_at`. |
| **FR-A30** | After operator process restart, a subsequent valid mention **shall** resume the same `agy.conversation_id` and Grok session pin when present (no silent “start fresh” without principal command). |
| **FR-A31** | Collab lifetime **shall not** be bounded by a single wall-clock timer; timeouts **shall** apply **per turn** (per backend invocation). |
| **FR-A32** | Per-room wake locks / queues **shall** serialize turns in a collab room (no concurrent dual backends for the same room). |
| **FR-A33** | Soft hop budget (epoch) default **shall** be high enough for long-horizon work (recommended default **100** bot↔bot hops per epoch, configurable). On budget hit, auto-handoff **shall** pause; agents **shall** be instructed not to peer-tag; principal **shall** be notified in-channel. |
| **FR-A34** | Tiny hard caps (e.g. max 6 hops total) **shall not** be the primary safety mechanism. |
| **FR-A35** | The system **should** detect no-progress spin (empty substance, near-duplicate peer-only tags) and auto-pause with reason. |
| **FR-A36** | Principal `/pause` (or equivalent) **shall** freeze auto-handoff without clearing session pins; `/resume` **shall** restore auto-handoff when safe. |
| **FR-A37** | Principal `/cancel` **shall** terminate in-flight wake for the room (PID-verified) for either backend. |
| **FR-A38** | Checkpoint cadence: every N hops (configurable, recommended **10–20**) or on epoch pause, inject **shall** encourage a durable repo note under Project cwd when write scope allows. |

### 3.7 Identity profiles (layering)

| ID | Requirement |
| --- | --- |
| **FR-A39** | **L1** Domain project `AGENTS.md` (if present under cwd) **shall** remain authoritative for domain claim discipline. |
| **FR-A40** | **L2** RC collab social contract **shall** be loaded for agy-target wakes via named agent (`agy --agent rc_collab` or equivalent) and/or `.agents/rules` content derived from draft profiles in `04-agy-rocketchat-collab/profiles/`. |
| **FR-A41** | **L3** Per-turn inject **shall** include at least: mention body, room id, cwd, hop/epoch counters, auto_handoff flag, write scope, agy conversation id (or NONE), and peer last message summary when available. |
| **FR-A42** | Grok-target wakes in collab rooms **shall** include a collab inject fragment equivalent to `profiles/grok-rc-collab.inject.md` (dual-account rules, no nested agy CLI, `@agy` handoff rules). |
| **FR-A43** | Default Gemini write scope **shall** be **read-only** unless principal elevation / explicit inject elevates path-scoped writes. |
| **FR-A44** | Profile content **shall** require: real peer @mention to hand off; omit peer mention to yield; honesty on failure; no impersonation of the other peer. |

### 3.8 Non-functional requirements

| ID | Requirement |
| --- | --- |
| **NFR-A1** | Single-turn agy print **should** complete within configured print-timeout on healthy Mac/auth; failures **shall** surface within timeout + finalize margin. |
| **NFR-A2** | Multi-day collabs **shall** remain operable from phone via channel history + `/status`-class summaries (Feature 3 alignment). |
| **NFR-A3** | Mention classification and hop/budget state machines **shall** be unit-testable without network. |
| **NFR-A4** | Operator logs **shall** record: target identity, author, mention parse result, hop counters, agy UUID capture/miss, CLI rc, pause reasons. |
| **NFR-A5** | Usability contracts for non-collab rooms **shall** remain unchanged. |

### 3.9 Security requirements

| ID | Requirement |
| --- | --- |
| **SR-A1** | Collab wakes **shall** reject non-allowlisted authors even if they can @mention bots. |
| **SR-A2** | Secrets and tokens **shall** never appear in reply bodies, Thinking updates, or injects. |
| **SR-A3** | `agy --dangerously-skip-permissions` (if used) **shall** be constrained by L2 read-only default + cwd allowlist + elevated write scope only when principal authorizes. |
| **SR-A4** | Daily or wall-clock cost budgets **should** exist to bound unattended spend. |
| **SR-A5** | MCP `agy_*` **shall** remain forbidden even if an MCP server is later installed. |
| **SR-A6** | Second-bot credentials **shall** use mode-600 secrets files; token auth preferred (IMP-20 style). |

---

## 4. Architecture and design decisions

### 4.1 Selected approach (research C3)

**Dual Rocket.Chat identities + @mention turns** is the normative product architecture.

```
#grok-agy-collab (private)
  members: principal, grok, agy
           │
    message + mentions[]
           ▼
  Mention dispatcher (collab rooms only)
     @grok ──► Thinking as grok ──► Grok CLI ──► chat.update as grok
     @agy  ──► Thinking as agy  ──► agy CLI   ──► chat.update as agy
           │
    body may include peer @mention ──► next hop
```

### 4.2 Implementation shape

| Decision | Choice | Rationale | Rejected |
| --- | --- | --- | --- |
| D1 Product shape | C3 dual peers | Human-like long-horizon ledger | C1 mediated monologue as primary UX |
| D2 Fake dual voice | Forbidden | Trust / avatars | C3-C |
| D3 Process topology | C3-A or C3-B (**OD-A2**) | Both valid | — |
| D4 Gemini transport | Local `agy` CLI + helper | Skill contract; validated smoke | MCP `agy_*` |
| D5 Nested agy in Grok | Forbidden in collab rooms | Double-speak | C1 primary |
| D6 Depth safety | Soft epoch budget + pause + spin detect | Allows many turns | Max-6 hard hop product cap |
| D7 Time model | Per-turn timeouts | Multi-day collab | Single collab wall clock |
| D8 Profiles | L1 domain + L2 rc_collab + L3 inject | Sticky identity | Inject-only L2 |
| D9 Final body | Reply file / captured stdout file | Align NO_DUPLICATE | Stream-only final |
| D10 REST updates | `chat.postMessage` Thinking + `chat.update` | Verified RC 8.6 | Unverified DDP-only |

### 4.3 Mention routing algorithm (normative sketch)

```
on_message(msg, room):
  if not is_collab_room(room) or not RC_AGY_COLLAB:
    return legacy_principal_only_path(msg, room)
  if msg.u.username not in {principal, grok, agy}:
    return ignore
  targets = resolve_mention_targets(msg) ∩ {grok, agy}
  if not targets:
    return ignore  # tag-to-talk
  if self_only(msg, targets):
    return ignore
  if paused(room) and msg.u.username in {grok, agy}:
    return ignore  # principal may still @-wake when policy allows
  if both targets and author == principal:
    return policy_OD_A1(msg)  # reject or sequential
  target = single(targets)
  if hop_budget_exhausted(room) and author in {grok, agy}:
    notify_principal_budget(room); return
  enqueue_wake(room, target, msg)
```

### 4.4 Agy backend algorithm (normative sketch)

```
on_agy_wake(room, msg):
  auth = agy_credentials()
  msgId = post_thinking_as(auth, room)  # "Thinking..."
  state = load_room_state(room)
  mode = conversation if state.agy.conversation_id else start
  prompt = build_l3_inject(room, msg, state)  # + L2 via --agent rc_collab
  rc, stdout, new_uuid = run_agy_cli_serialized(mode, state.agy.conversation_id, prompt, cwd)
  if new_uuid: state.agy.conversation_id = new_uuid
  body = stdout_to_reply_file(stdout) or error_body(rc)
  chat_update_as(auth, msgId, body)
  update_hops_and_pause_if_needed(room, state)
  mark_processed(msg)
```

### 4.5 Grok backend in collab rooms

Same as live path with:

- collab inject fragment (FR-A42),  
- no nested `agy` CLI,  
- optional Feature 2 streaming on **grok** msgId,  
- hop accounting when author was `agy` or principal.

---

## 5. Integration contracts

### 5.1 Live code touch points (implement-time map)

| Location | Contract change |
| --- | --- |
| `rc_operator_agent.py` | Collab room branch; mention parse; allowlist authors; dual auth posting **or** handoff to sibling agent |
| `wake_lib.py` | Room profile fields; hop/budget state; session keys for agy UUID; timeout overrides per target |
| `reply_prompt.txt` / new fragment | Grok collab inject when profile matches |
| `channel_projects.json` or `room_profiles.json` | `mode=agy-collab`, cwd, budgets, timeouts |
| `state.json` | Collab sub-object per room (FR-A29) |
| secrets `rocketchat.env` (or sibling) | `agy` user token/password (not in this docs package) |
| `~/.grok/skills/agy-cli-collab/` | Unchanged CLI-only contract; operator shells helper |
| Profiles install | `.agents/agents/rc_collab/agent.md` from research drafts |

### 5.2 Compatibility with Feature 2 (streaming)

| Requirement | Integration |
| --- | --- |
| Long agy turns | Phase updates on **agy** Thinking bubble when streaming/meta available |
| Long Grok turns | Existing NF-SPEC-02 rules on **grok** bubble |
| Final | Reply file still wins |

### 5.3 Compatibility with Feature 3 (control plane)

| Command / surface | Collab semantics |
| --- | --- |
| `/status` | **Shall** show both session pins, hop counters, pause, last errors when in collab room |
| `/pause` `/resume` | **Shall** map to `auto_handoff` |
| `/cancel` | **Shall** kill in-flight either backend |
| `/new` | **Should** clear Grok session only unless args clear agy UUID |
| `/agy new` (or `/collab new-agy`) | **Should** clear agy conversation UUID only |
| `/budget` | **Should** show/adjust epoch hop budget |

If Feature 3 is not yet shipped, collab v1 **may** implement a minimal subset of these as collab-native commands, but **shall not** invent conflicting grammars.

### 5.4 Channel / cwd policy

| Rule | Contract |
| --- | --- |
| Project cwd | From `channel_projects.json` / profile; absolute path for agy cwd keying |
| Auto-create IdeaProjects | Remain off by default (IMP-19); collab rooms **shall** use explicit map entries |
| agy session keying | Same absolute cwd every turn (skill: resume keyed by shell cwd) |

### 5.5 Approval / write scope

| Mode | Collab expectation |
| --- | --- |
| Grok restricted | Default; collab inject still works for text; tool limits per IMP-01 |
| Grok admin / once | Feature 3 elevation; required for mutating tools |
| Agy default | Read-only L2; elevated writes only when inject says so |
| Nested permissions | `agy --dangerously-skip-permissions` only with SR-A3 constraints |

---

## 6. Interfaces and configuration

### 6.1 Environment variables (proposed)

| Variable | Default | Meaning |
| --- | --- | --- |
| `RC_AGY_COLLAB` | `0` | Master enable for collab-room dual-peer behavior |
| `RC_AGY_USER` | `agy` | RC username for Antigravity peer |
| `RC_AGY_TOKEN` / password pair | (secrets) | Auth for posting as `agy` |
| `RC_AGY_BIN` | `~/.local/bin/agy` | CLI path |
| `RC_AGY_HELPER` | skill `agy_cli.py` path | Preferred wrapper |
| `RC_AGY_AGENT` | `rc_collab` | `--agent` name for L2 |
| `RC_AGY_PRINT_TIMEOUT` | `10m` | Print mode timeout |
| `RC_AGY_WAKE_TIMEOUT_S` | `1200` | Parent wait for agy-target turns |
| `RC_AGY_HOP_BUDGET_EPOCH` | `100` | Soft bot↔bot hops per epoch |
| `RC_AGY_CHECKPOINT_EVERY` | `15` | Inject checkpoint nudge period |
| `RC_AGY_COOLDOWN_S` | `0` or small | Min seconds between bot-triggered wakes |
| `RC_AGY_DAILY_WAKE_CAP` | (optional) | Hard daily budget |

### 6.2 Room profile fields (proposed)

```json
{
  "grok-agy-collab": {
    "cwd": "/Users/…/IdeaProjects/prime-gap-structure",
    "mode": "agy-collab",
    "hop_budget_epoch": 100,
    "agy_print_timeout": "10m",
    "wake_timeout_s": 1200,
    "checkpoint_every": 15,
    "auto_handoff_default": true
  }
}
```

### 6.3 State schema (proposed, normative fields)

See FR-A29. Exact JSON nesting is implement-time flexible if fields are durable and per-room.

### 6.4 Operator log lines (proposed)

- `collab mention room=<id> author=<u> targets=<…>`  
- `collab wake target=agy mode=start|conversation uuid=<…|none>`  
- `collab hop epoch=<n> count=<k>/<budget>`  
- `collab pause reason=budget|spin|principal`  
- `collab agy rc=<n> uuid_captured=<bool>`  

---

## 7. Phased delivery and acceptance criteria

### 7.1 Phases

| Phase | Deliverable | Gate |
| --- | --- | --- |
| **A0 Lab** | RC user `agy`; private channel; REST mention physics; manual CLI post-as-agy | Mentions[] or reliable parse proven on RC 8.6 |
| **A1 MVP** | Mention dispatcher + dual auth Thinking/update + agy helper backend + high soft budget + serial room queue | Principal `@agy` → agy `@grok` → grok reply without principal mid-hop |
| **A2 Durability** | State pins + hop counters + resume after operator restart | Mid-epoch restart continues same agy UUID |
| **A3 Trust UX** | Feature 2 phases on both identities; structured fail as that user | Long print does not look dead; fail honest |
| **A4 Control** | `/status` collab block, `/pause` `/resume` `/cancel`, budget | Phone supervisor path without SSH |
| **A5 Harden** | Spin detection, daily cap, token auth, profile install automation | Unattended multi-hour safe |

### 7.2 Acceptance criteria (implement-time)

- [ ] **AC-A1:** Dual avatars: channel history shows distinct `agy` and `grok` usernames for their turns.  
- [ ] **AC-A2:** Tag-to-talk: untagged principal note does **not** wake either backend.  
- [ ] **AC-A3:** Handoff: principal `@agy` → agy message with `@grok` → grok wake without further principal text.  
- [ ] **AC-A4:** CLI-only: zero MCP `agy_*` invocations in logs during collab.  
- [ ] **AC-A5:** Per-speaker bubble: each wake one Thinking… → one finalize; no double answer post.  
- [ ] **AC-A6:** Sticky agy: third `@agy` turn recalls early marker **or** repo checkpoint (H-01 class).  
- [ ] **AC-A7:** Long-horizon: ≥50 bot↔bot hops **or** multi-hour epoch without forced hard-cap death.  
- [ ] **AC-A8:** Soft budget pause: at budget, auto-handoff stops; principal notified; sessions retained.  
- [ ] **AC-A9:** Restart resume: operator restart; next mention continues agy UUID + Grok pin.  
- [ ] **AC-A10:** Failure honesty: killed agy mid-flight → **agy** bubble error; Grok does not invent Gemini text.  
- [ ] **AC-A11:** Profiles: agy wake uses L2 agent/rules; Grok wake includes collab inject forbidding nested agy.  
- [ ] **AC-A12:** Non-collab rooms unchanged principal-only behavior regression suite green.

### 7.3 Documentation-package acceptance (this goal)

- [x] NF-SPEC-04 exists with multi-section depth and normative **shall** language.  
- [x] Linked from specs index and parent new-features index.  
- [x] Traces to research + profiles.  
- [x] No runtime operator implementation required by this package.

---

## 8. Risks and dependencies

### 8.1 Risks

| ID | Risk | Severity | Mitigation |
| --- | --- | --- | --- |
| R1 | REST @mention does not populate `mentions[]` | High | A0 lab; text fallback; force mention API if needed |
| R2 | Runaway bot↔bot spin | Critical | Soft budget + spin detect + `/pause` |
| R3 | Over-tight hop cap kills product | Critical | FR-A33/A34 |
| R4 | Timeout kills nested long print | High | Per-target wake timeout ≥ print timeout |
| R5 | UUID not captured | High | Helper log parse; fail visible |
| R6 | Context window collapse at 50+ turns | High | OD-A3 context strategy; checkpoints |
| R7 | Secret leakage in collab text | High | SR-A2; inject hygiene |
| R8 | Dual process auth drift (C3-A) | Medium | Shared state schema; health checks |
| R9 | Feature 2/3 not ready | Medium | Minimal collab-native status/pause |
| R10 | Restricted Grok cannot act on repo | Medium | Elevation path; read-only analysis still valuable |

### 8.2 Dependencies

| Dependency | Need |
| --- | --- |
| Rocket.Chat 8.6 REST + WS | Message events, postMessage, update, mentions |
| Local `agy` CLI authenticated | Print mode + conversation pin |
| `agy-cli-collab` helper | UUID capture, modes |
| Draft profiles | L2 content source |
| Optional NF-SPEC-02/03 | Better UX / control; not hard blockers for A1 |
| Secrets storage | Second bot credentials |

---

## 9. Open decisions

| ID | Decision | Options | Default lean |
| --- | --- | --- | --- |
| **OD-A1** | Principal double-mention both bots | Reject vs sequential | Reject with help (simpler) |
| **OD-A2** | C3-A dual process vs C3-B multi-identity operator | A / B | C3-B for fewer daemons unless isolation required |
| **OD-A3** | Context after 50+ turns | compress / repo summary inject / new epoch sessions | Repo summary inject + checkpoint |
| **OD-A4** | Default collab cwd | PGS vs dedicated workspace | Explicit profile per channel |
| **OD-A5** | Unattended auto-handoff default | on vs require `/unattended on` | on in private collab rooms only |
| **OD-A6** | Exact epoch hop default | 50 / 100 / 200 | **100** |
| **OD-A7** | Profile install: `--agent` only vs also `.agents/rules` | agent / both | **Both** |
| **OD-A8** | `/new` clears agy UUID? | no / yes / flag | **No** (independent clear command) |

---

## 10. Traceability

| Spec area | Research / profile source |
| --- | --- |
| Dual accounts + @mention | Research §1.2, §3 C3 |
| Long-horizon value | Research §1.1b, D1–D10 |
| Anti-runaway ≠ anti-depth | Research anti-runaway table |
| CLI-only Gemini | Research skill contract §2.7; skill SKILL.md |
| Per-speaker bubble | Research §4.6; NO_DUPLICATE_POSTS |
| State / hops | Research §5.2 |
| Profiles L1–L3 | Research §4.0; `profiles/*` |
| Live principal-only gap | `rc_operator_agent.py` filter; research §2.2 |
| Phased delivery | Research §9 |

| Requirement cluster | Profile artifact |
| --- | --- |
| FR-A39–A44 | `profiles/agy-rc-collab.agent.md`, `.AGENTS.md`, `grok-rc-collab.inject.md` |
| Handoff @grok / @agy | Same |

---

## 11. Normative summary (implementer checklist)

1. Collab rooms only; master flag; private members `principal`+`grok`+`agy`.  
2. Tag-to-talk @mentions; allowlisted authors; no self-wake.  
3. Dual auth posting; per-speaker Thinking… → `chat.update`.  
4. Grok CLI vs local `agy` CLI backends; **never MCP `agy_*`**.  
5. No nested agy inside Grok in collab rooms.  
6. Durable dual sessions + hop/epoch state; soft budget pause.  
7. L1 domain + L2 rc_collab profile + L3 inject.  
8. Long-horizon first; safety against spin/cost, not against depth.

---

*End of NF-SPEC-04.*
