# Feature 3 — Phone control plane (slash commands, approval cards, room mission control)

**Status:** Research only (no runtime implementation in this document set)  
**Date:** 2026-07-10 · **Last reviewed:** 2026-07-11 (`/model` `/effort` `/goal` + slash taxonomy)  
**Stack baseline:** Principal-only wakes; per-room Grok session pins + cwd pins; approval modes IMP-01; `health.json` + IMP-12 watchdog; channel map `channel_projects.json`; multi-room operator WebSocket  
**Product thesis:** Rocket.Chat is not only a chat mirror of Grok — it is the **remote console** for the principal Mac / agency program.

### Downstream documentation (normative chain)

| Layer | Document | ID |
| --- | --- | --- |
| **Spec** | [spec.md](./spec.md) | NF-SPEC-03 |
| **Test plan** | [test-plan.md](./test-plan.md) | NF-TP-03 |
| **Implementation plan** | [implementation-plan.md](./implementation-plan.md) | NF-IP-03 |

**Canonical recommended direction:** Operator-native command interceptor (not Apps-Engine for v1); room-scoped `/admin once` with confirm; master flag `RC_CONTROL_PLANE` for rollback.

**Live stack fact:** Restricted = `--permission-mode auto`; admin = `--always-approve`. Elevation overlays base `resolve_approval_mode` without permanently flipping launchd env.

---

## 1. Problem framing (against the live stack)

### 1.1 What works today (conversational)

- Principal messages in DM or joined channels wake Grok with project-aware `--cwd`.  
- Same room → same Grok session (`--resume` pin in `state.json`).  
- Restricted vs admin approval (`RC_WAKE_APPROVAL_MODE`, `RC_WAKE_ADMIN_DMS_ONLY`).  
- Media via `rc_post_media.py`; Path A voice notes; Path C calls (fragile).  
- Ops truth lives in logs, launchd, `health.json`, and `~/.grok/agency/STATE.md`.

### 1.2 What is operationally opaque on the phone

| Need | Today’s path | Phone friction |
| --- | --- | --- |
| “Is the operator alive?” | SSH / log / `rc_health_check.sh` | Not in chat |
| “What session/cwd is this room on?” | Read `state.json` or infer from behavior | Invisible |
| “Reset session” | Hope model understands `/new` or manual state edit | Unreliable |
| “Elevate to admin for one wake” | Edit launchd env + kickstart | Impossible mid-walk |
| “Cancel runaway wake” | Kill process on Mac | No phone affordance |
| “Room mission / last research status” | Freeform prose or PGS hourly posts | No structured panel |

### 1.3 Gap statement

Conversation is strong; **steering and observability** are weak. After IMP-01, elevation and mode are env-level, not principal-gesture-level. The 2026-07-10 empty-reply incident would have been shorter if `/status` showed `stopReason` and `/retry --admin` existed.

---

## 2. Current baseline / interfaces (precise)

### 2.1 Trust and filter model

| Actor | RC user | Role |
| --- | --- | --- |
| Human | `principal` | Only username that triggers wakes |
| Bot | `grok` | Posts Thinking…, updates, media, call join |

Operator ignores non-principal traffic. **Control plane must keep that invariant** — commands only from principal.

### 2.2 State the control plane should surface

From operator / wake_lib (conceptual fields already or easily available):

| State | Storage | Notes |
| --- | --- | --- |
| Per-room session id | `wake/state.json` (`grok_sessions` / helpers) | Resume pin |
| Per-room cwd | `state.json` + `channel_projects.json` | Map + pin |
| Approval mode effective | `resolve_approval_mode(room_type, room_name)` | restricted / admin |
| Last wake rc / time | state + logs | `last_wake_at`, `last_wake_rc` |
| WS health | `health.json` | `ws_connected`, `pid`, `rooms_count` |
| Pending wakes / locks | `pending_wakes`, `wake.lock.d` | Queue / stuck lock |
| Agency mandate | `~/.grok/agency/STATE.md` | Continuity (DM-relevant) |

### 2.3 Extension surfaces in Rocket.Chat

| Surface | How | Fit for this stack |
| --- | --- | --- |
| **Message text parse** | Operator intercepts messages matching `^/` before normal wake | **Recommended primary** — no Apps-Engine required; principal-only already |
| **Apps-Engine slashcommand** | App registers slash commands (permission `slashcommand`) | Cleaner UX (autocomplete); more deploy overhead on private RC |
| **Message actions / buttons** | Apps-Engine UI kit / interactive messages | Best for Approve/Deny cards |
| **Custom emoji reactions** | Principal reacts ✅/❌ on card | Works on mobile; weaker structure |
| **Pinned messages** | REST pin room status card | Mission control panel |

Primary recommendation: **operator-native command parser** first (matches current architecture), optional Apps-Engine later for autocomplete and buttons.

### 2.4 Approval mode reality (IMP-01 + hotfix)

| Mode | CLI flags (current) | Who gets it |
| --- | --- | --- |
| restricted | `--permission-mode auto` | Default; channels when admin+DMs-only |
| admin | `--always-approve` | When `RC_WAKE_APPROVAL_MODE=admin` and (DM or DMs-only off) |

**Problem:** No **per-wake** or **time-boxed** elevation from phone. Global env change is nuclear and slow.

**Control-plane need:** `admin-once`, `admin-for-room-15m`, explicit confirm cards for dangerous tools.

---

## 3. Feature package (three sub-features, one plane)

### 3.1 Slash / command grammar (operator-native)

Commands are **principal messages** that start with `/` (or a configurable prefix `!`). They are **not** forwarded to Grok as freeform research unless marked `/ask …`.

#### Proposed command set (v1)

| Command | Effect | Room scope |
| --- | --- | --- |
| `/help` | **First-class:** list v1 commands + one-line semantics; optional `/help <cmd>` usage | any (even if elevation off) |
| `/status` | Card: health, session, cwd, mode, **model**, **effort**, **goal**, last wake rc/stopReason, lock | current room + global health |
| `/health` | Operator WS + Docker reachability summary (local checks) | any |
| `/new` | Clear room session pin (+ optional cwd pin keep); **does not** clear model/effort pins by default | current |
| `/session show` | Print session id / age | current |
| `/session reset` | Alias of `/new` | current |
| `/cwd` | Show resolved cwd + reason (map/pin/dm) | current |
| `/cwd pin <path>` | Pin cwd if path exists and under allowlist | current |
| `/cwd clear` | Drop cwd pin | current |
| `/mode` | Show effective **approval** mode + elevation (not LLM “model”) | current |
| `/model` | Show or pin room LLM model for subsequent wakes (`--model`) | current |
| `/model <id\|name>` | Set pin; optional second token effort if CLI allows | current |
| `/model clear` | Drop model pin → operator/env default | current |
| `/effort` | Show room reasoning-effort pin | current |
| `/effort <level>` | Pin effort: `none`/`minimal`/`low`/`medium`/`high`/`xhigh`/`max` → `--reasoning-effort` / `--effort` | current |
| `/effort clear` | Drop effort pin | current |
| `/goal` | Show room goal pin / last known status | current |
| `/goal <objective>` | Set room goal pin; next wakes carry goal context (see §3.1b) | current |
| `/goal status` \| `pause` \| `resume` \| `clear` | Manage room goal pin (map of TUI `/goal` subcommands) | current |
| `/admin on` | Request elevation (see cards) | current / global policy |
| `/admin off` | Drop elevation | current |
| `/admin once` | Next wake only admin | current |
| `/cancel` | Kill active wake for room if any | current |
| `/retry` | Re-queue last principal non-command text (if retained) | current |
| `/wake <text>` | Explicit freeform wake (escape hatch) | current |
| `/ask <text>` | Same as wake; emphasizes LLM path | current |

#### Parsing rules

1. Only `u.username == principal`.  
2. Trim; match `^/(?P<cmd>\S+)(?:\s+(?P<args>.*))?$`.  
3. Unknown command → short help error **without** spawning Grok (fail closed).  
4. Commands that mutate state write operator log line + optional confirmation bubble from `grok`.  
5. `/new` must **not** depend on model interpreting natural language.  
6. **Name collision:** `/mode` = approval elevation surface; `/model` = LLM model pin. Never alias them.

#### Allowlist for `/cwd pin`

- Under `~/IdeaProjects/` or `~/.grok/agency` only.  
- Reject `..`, symlinks escaping, home root, `/`, secrets paths.  
- Align with blast-radius goals of IMP-01.

#### 3.1b Room pins: model / effort / goal

These map Grok CLI **session controls** that the TUI exposes as `/model`, `/effort`, `/goal` onto **per-room operator state**, because Rocket.Chat wakes are headless subprocesses (not a live TUI session).

| Pin | Operator state (conceptual) | Applied on next `build_wake_argv` |
| --- | --- | --- |
| Model | `room_models[roomId]` | `-m` / `--model <id>` when set |
| Effort | `room_effort[roomId]` | `--reasoning-effort` / `--effort <level>` when set |
| Goal | `room_goals[roomId] = { objective, status, updated_at }` | Prompt preamble and/or goal-tool enablement when CLI supports it; at minimum inject durable “active goal” lines into the wake prompt file so headless runs stay goal-aware |

**Goal note:** Full interactive TUI goal automation (`update_goal` tool, multi-turn autonomy inside one process) is not identical to multi-wake RC. v1 **shall** pin objective + status and make subsequent room wakes goal-aware; deep goal-tool parity is OD-C7 if headless CLI lacks a single-flag equivalent.

#### 3.1c Why not “all” Grok TUI slash commands?

The Grok Build TUI advertises a large slash menu (session pickers, themes, plugins, vim mode, `/quit`, …). The phone control plane is **not** a remote TUI keyboard — it is an **operator-native grammar** for principal-safe, room-scoped ops on headless wakes.

| Class | Examples | RC policy |
| --- | --- | --- |
| **A — Control plane (v1)** | `/help` `/status` `/health` `/new` `/cwd` `/mode` `/model` `/effort` `/goal` `/admin*` `/cancel` `/retry` `/wake` `/ask` | Deterministic operator handlers; no surprise research wake |
| **B — Map when cheap** | `/clear`→`/new`, `/m`→`/model`, TUI `/session-info` fields → `/status` | Aliases + card fields |
| **C — Pass-through as wake content (optional later)** | `/imagine …`, `/remember …`, freeform skill names | Only if explicitly allowlisted; still a **wake**, not silent magic |
| **D — TUI / UI-only (do not implement as no-ops that lie)** | `/theme` `/vim-mode` `/multiline` `/compact-mode` `/sessions` (picker) `/home` `/quit` `/copy` `/export` (clipboard) `/settings` modals | Reply: “TUI-only; use Mac Grok or N/A on phone” **or** omit from `/help` and treat as unknown → `/help` |
| **E — Security / account (never from phone v1)** | `/login` `/logout` `/privacy` raw `/always-approve` without confirm | Reject; elevation stays `/admin once`/`on` with confirm |
| **F — Heavy product (deferred)** | `/loop` (scheduler), full `/plugins`/`/marketplace`, `/plan` UX, voice `/call` | Separate specs (scheduler, Feature 1, etc.) |

**Principles:**

1. **Fail closed:** unknown `/foo` never becomes a multi-hour research wake.  
2. **No fake parity:** do not advertise `/theme` as “supported” if it cannot change anything on the phone.  
3. **Prefer room pins + argv** over re-implementing the entire pager/shell slash router.  
4. **Expand Class A deliberately** (as with `/model` `/effort` `/goal`) when there is a clear headless mapping and phone value.

---

### 3.2 Approval cards (human-in-the-loop elevation)

#### Problem cards solve

Restricted mode is correct for phone-driven safety, but some tasks need shell/network. Today that means:

- permanent admin env, or  
- silent cancel / incomplete work.

#### Card flows

**Flow A — explicit elevation**

1. Principal: `/admin once`  
2. Bot posts card: “Next wake in this room will use **admin** (`--always-approve`). Confirm?”  
3. Principal replies `yes` / `no` or taps button / reacts ✅ ❌  
4. State: `room_elevation[rid] = {mode: admin, uses: 1, expires: …}`  
5. Next non-command wake consumes the once-token.

**Flow B — model-requested elevation (advanced)**

1. Wake runs restricted; tool denied or policy predicts need.  
2. Operator finalizes with: “Need admin for `<tool summary>`. Reply `/admin once` then `/retry`.”  
3. No auto-elevation without principal gesture.

**Flow C — Apps-Engine buttons (v2)**

Interactive message blocks: **Approve admin once** / **Deny**. Requires app package on RC 8.6.

#### Security properties

| Property | Rule |
| --- | --- |
| Default | restricted |
| Elevation | explicit principal action only |
| Scope | prefer **room + once/TTL**, not global forever |
| Audit | log every elevation grant/deny/consume |
| Secrets | never print tokens in cards |

---

### 3.3 Room mission control (status panel)

#### Status card content (markdown)

```text
## Mission control — #Prime-Gap-Structure
- operator: online (pid …, ws ok)
- approval: restricted (elevation: none)
- session: 019f4897-… (pinned)
- cwd: ~/IdeaProjects/prime-gap-structure (pinned)
- last wake: 03:26Z rc=0 stopReason=EndTurn
- queue: empty
- agency tip: (optional 1-line from STATE.md if DM)
```

#### Delivery modes

| Mode | Mechanism | When |
| --- | --- | --- |
| On demand | `/status` | Default |
| Sticky pin | pin message; update in place via `chat.update` | Optional `RC_STATUS_PIN=1` |
| Hourly | adjacent to PGS notify pattern | Only if principal wants ambient ops |

Pinned status must obey NO_DUPLICATE_POSTS spirit: **one pin**, update in place, never flood.

#### Cross-room dashboard (v2)

DM-only `/ops` lists all watched rooms with one-line health. Useful when principal manages Agency + PGS + research simultaneously.

---

## 4. Candidate implementation approaches

### Approach C1 — Operator message interceptor (recommended v1)

In `handle_principal` / enqueue path:

```
if is_command(text):
    dispatch_command(...)
    mark processed; do not wake
else:
    existing wake path
```

| Pros | Cons |
| --- | --- |
| Fits current Python operator | No slash autocomplete in mobile UI |
| Fast to ship; testable | Manual `/help` discovery |
| Principal-only already enforced | Buttons need later app |

---

### Approach C2 — Rocket.Chat Apps-Engine slash commands + UI kit

Register commands with RC; app calls operator via localhost webhook or shared queue.

| Pros | Cons |
| --- | --- |
| Native `/` UX | App deploy, permissions, versioning |
| Buttons/cards first-class | Another process to KeepAlive |
| | Private app signing/upload on self-hosted 8.6 |

**Verdict:** v2 after C1 proves grammar.

---

### Approach C3 — Natural language only (“reset the session please”)

| Pros | Cons |
| --- | --- |
| Zero new code | Unreliable; burns wake; wrong cwd risk |
| | Bad for safety-critical elevation |

**Verdict:** Reject as sole design; `/ask` remains for freeform.

---

## 5. Integration with wake / call / streaming

| System | Integration |
| --- | --- |
| Wake path | Commands short-circuit before Thinking… (except `/wake` `/ask` `/retry`) |
| Streaming Feature 2 | `/status` reads same telemetry schema (`stopReason`, phase) |
| Voice Feature 1 | `/call status`, later `/call hangup` if agent worker exposes control socket |
| Approval IMP-01 | Elevation state feeds `resolve_approval_mode` override per room |
| Locks IMP-02/10 | `/cancel` clears room lock + kills child grok PID if owned |
| Health IMP-12 | `/health` shells out to same predicates as `rc_health_check.sh` |
| Agency spine | DM `/status` may include one-line STATE.md mandate (read-only) |
| PGS hourly | Remains separate notify path; do not double-post (NO_DUPLICATE) |

### Suggested `resolve_approval_mode` extension (design only)

```
effective = base_from_env_and_room_type()
if room_elevation_active(rid):
    effective = admin
return effective
```

Elevation records in `state.json` with TTL and remaining uses.

---

## 6. Risks and failure modes

| Risk | Mitigation |
| --- | --- |
| Command injection via crafty args | Strict argv parse; no shell=True for user args |
| `/cwd pin` to sensitive paths | Allowlist + realpath check |
| Accidental `/admin on` forever | Prefer once/TTL; confirm card; `/mode` visibility |
| Commands eaten as normal wakes | Interceptor **before** enqueue; tests for `/status` no wake |
| Principal typo `/nwe` | Unknown → help; do not wake |
| Mobile clients strip leading `/` | Document; support `!status` alias |
| State.json corruption | Atomic writes (already pattern); backup on change |
| Cancel kills wrong process | PID file per room; verify parent is operator |
| Help spam | Rate-limit help replies |
| Multi-device principal sessions | Still one principal user; last write wins on elevation |

---

## 7. Open questions

1. Confirm-card UX without Apps-Engine: is `yes`/`no` reply in next message good enough on iOS?  
2. Should `/new` also create a fresh Grok session id eagerly or only clear pin (lazy new on next wake)?  
3. Retention of last non-command message for `/retry` — privacy vs utility?  
4. Expose Docker/ngrok status in `/health` (local curls) or keep health.json-only?  
5. Do channel non-admin users ever exist later? (Today principal-only — design stays principal-only.)  
6. Should elevation require a typed passphrase from secrets (extra safety) or is principal login enough?  
7. How deep should `/goal` go on headless multi-wake RC (prompt inject only vs native goal tool / orchestrator)? See OD-C7.  
8. Which Class C skills (if any) ever get phone pass-through allowlist? Default: none.  
9. Should `/new` ever clear model/effort/goal (OD-C8 default: no)?

---

## 8. Recommended direction

### Primary

**Operator-native command interceptor (C1)** + **room elevation tokens** + **`/status` mission card**.

### Phased delivery

| Phase | Deliverable | Exit criteria |
| --- | --- | --- |
| **P0** | `/help`, `/status`, `/health`, `/new`, `/cwd`, `/mode`, **`/model`**, **`/effort`**, **`/goal` show/set/clear** | No Grok spawn for pins; argv wired for model/effort |
| **P1** | `/admin once` + confirm + consume on next wake | Restricted default; one elevated wake works |
| **P2** | `/cancel`, `/retry` | Runaway wake stoppable from phone |
| **P3** | Optional pinned status; Feature 2 telemetry; richer `/goal` status | Single schema |
| **P4** | Apps-Engine slash + buttons | Autocomplete + tap Approve |

### Success signals

1. From phone, **`/help`** lists the v1 command set in &lt;2s without a research wake; **`/status`** answers in &lt;2s without a full research wake.  
2. `/new` guarantees next message is a fresh session (no stale resume).  
2b. `/model` and `/effort` pin room CLI args; next content wake uses them; `/goal` pins an objective visible on `/status` and in subsequent wake context.
3. Principal can elevate **one** wake without editing launchd.  
4. Unknown `/foo` never triggers a 30s Grok run.  
5. Audit log shows every elevation grant/consume.  
6. Existing non-command messages behave identically.

### Explicit non-goals (v1)

- Multi-user RBAC.  
- Full web dashboard outside RC.  
- Replacing agency `STATE.md` continuity system.  
- Natural-language-only control without slash grammar.

---

## 9. Sources and primary interfaces

| Kind | Reference |
| --- | --- |
| Architecture / accounts | `docs/architecture.md` |
| Message flow | `docs/message-flow.md` |
| Ops health | `docs/operations.md`, `scripts/rc_health_check.sh` |
| Approval modes | `wake/wake_lib.py` (`resolve_approval_mode`, `approval_mode_cli_flags`) |
| State pins | `wake/state.json`, wake_lib room session/cwd helpers |
| Channel map | `wake/channel_projects.json` |
| Operator agent | `wake/rc_operator_agent.py` |
| Health artifact | `~/logs/rocketchat-dm-wake/health.json` |
| Agency continuity | `~/.grok/agency/STATE.md`, `START_HERE.md` |
| RC app permissions | https://developer.rocket.chat/docs/app-permission-system (`slashcommand`, …) |
| RC Apps-Engine | https://developer.rocket.chat/docs/rocketchat-apps-engine |
| IMP-01 requirements | `docs/improvements/01-cap-blast-radius/` |

---

## 10. Research conclusion

The control plane is how this integration becomes a **remote agent workstation** rather than a clever webhook. Implement **deterministic commands and elevation tokens** in the operator first — cheap, testable, principal-safe — then layer native RC slash/button UX. Combined with Feature 2 telemetry and Feature 1 voice, the phone stops being a thin client and becomes the primary cockpit for the Mac-side agency.
