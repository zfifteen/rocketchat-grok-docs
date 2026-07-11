# Technical Specification: Phone control plane (slash commands, approval cards, mission control)

| Field | Value |
| --- | --- |
| **Spec ID** | NF-SPEC-03 |
| **Version** | 1.1 |
| **Status** | Specification (implementation out of scope for this document package) |
| **Date** | 2026-07-10 · **Last reviewed:** 2026-07-10 |
| **Prior research** | [`./research.md`](./research.md) |
| **Test plan** | [`./test-plan.md`](./test-plan.md) (NF-TP-03) |
| **Implementation plan** | [`./implementation-plan.md`](./implementation-plan.md) (NF-IP-03) |
| **Related** | IMP-01 approval modes, `wake/state.json`, `health.json`, `channel_projects.json` |
| **Owner surface** | Principal-only command interceptor + room elevation + status cards |

---

## 1. Problem and context

### 1.1 Problem statement

The Rocket.Chat ↔ Grok integration is strong as a **conversational wake bridge** but weak as a **remote operations console**. Session pins, cwd pins, approval mode, operator health, and wake failures are invisible or only steerable by editing launchd/env on the Mac. After restricted-mode production defaults (IMP-01), the principal cannot safely elevate a single wake from the phone without nuclear config changes. Commands like “reset session” currently depend on freeform model interpretation (`/new` as prose), which is unreliable.

### 1.2 Context (live stack)

| Element | Current fact |
| --- | --- |
| Trust | Only username `principal` triggers wakes; bot is `grok` |
| Continuity | Per-room Grok session + cwd pins in `state.json` |
| Approval | `RC_WAKE_APPROVAL_MODE` + `RC_WAKE_ADMIN_DMS_ONLY`; restricted uses `--permission-mode auto` |
| Health | `health.json` + `scripts/rc_health_check.sh` (ops-facing) |
| Map | `channel_projects.json` for channel → IdeaProjects |
| Wake path | All principal text currently eligible for Thinking… wake (no command short-circuit) |

### 1.3 Spec purpose

Define the engineering contract for a **phone control plane**: deterministic slash commands, room-scoped elevation tokens with confirmation, and mission-control status — without implementing runtime code in this package.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
| --- | --- |
| G1 | Principal can inspect room + operator health from phone in &lt;2s without a research wake. |
| G2 | Principal can reset session (`/new`) deterministically without model cooperation. |
| G3 | Principal can grant **time- or count-bounded** admin elevation without editing launchd. |
| G4 | Unknown slash commands never spawn a multi-turn Grok research wake. |
| G5 | Default remains restricted; elevation is explicit, audited, and room-scoped preferred. |
| G6 | Non-command messages continue to behave exactly as today’s wake path. |

### 2.2 Non-goals

| ID | Non-goal |
| --- | --- |
| NG1 | Multi-user RBAC beyond principal-only trust. |
| NG2 | Full web dashboard outside Rocket.Chat. |
| NG3 | Natural-language-only control without a deterministic grammar. |
| NG4 | Replacing agency `STATE.md` continuity system. |
| NG5 | Apps-Engine slash autocomplete as a v1 blocker (v1 is operator-native). |
| NG6 | Implementing this feature in the present documentation goal. |

---

## 3. Normative requirements

### 3.1 Trust and routing

| ID | Requirement |
| --- | --- |
| **FR-C0** | When `RC_CONTROL_PLANE` is disabled (`0`/`false`/`off`), the operator **shall** treat all principal text as content (legacy wake path) with no command short-circuit. |
| **FR-C1** | Only messages from RC user `principal` **shall** invoke control-plane commands or wakes. |
| **FR-C2** | Before enqueueing a normal wake, the operator **shall** classify principal text as **command** or **content**. |
| **FR-C3** | Command messages **shall not** spawn Grok CLI research wakes (except `/wake`, `/ask`, `/retry` which explicitly request wake). |
| **FR-C4** | Unknown commands **shall** reply with a short help/error from `grok` and **shall** mark the message processed without CLI wake. |

### 3.2 Command grammar

| ID | Requirement |
| --- | --- |
| **FR-C5** | Commands **shall** match (after trim): `^/(?P<cmd>\S+)(?:\s+(?P<args>.*))?$` or optional alias prefix `!` (`RC_CMD_PREFIXES=/,!`). |
| **FR-C6** | Command dispatch **shall** be case-insensitive for `cmd`; args **may** be case-sensitive (paths). |
| **FR-C7** | The v1 command set **shall** include at least: `help`, `status`, `health`, `new`, `session`, `cwd`, `mode`, `admin`, `cancel`, `retry`, `wake`, `ask` (see §6). |
| **FR-C8** | `/new` and `/session reset` **shall** clear the room’s Grok session pin; cwd pin **should** be retained unless args request clear. |
| **FR-C9** | `/cwd pin <path>` **shall** accept only paths that resolve under allowlisted roots (`~/IdeaProjects`, `~/.grok/agency`) after `realpath`; otherwise reject. |
| **FR-C10** | `/status` **shall** return a markdown mission card for the current room plus global operator health summary. |
| **FR-C11** | `/health` **shall** report operator WS/health.json freshness and **should** report local RC reachability (`http://127.0.0.1:3000/api/info` or configured base). |
| **FR-C12** | `/cancel` **shall** attempt to terminate the active wake for that room if owned by the operator (PID verification). |
| **FR-C13** | `/retry` **shall** re-enqueue the last retained non-command principal text for the room if present; else error. |
| **FR-C14** | `/wake <text>` and `/ask <text>` **shall** enqueue a normal wake with `<text>` as the user message. |

### 3.3 Elevation (approval cards)

| ID | Requirement |
| --- | --- |
| **FR-C15** | Default effective mode **shall** remain the result of existing `resolve_approval_mode` (env + room type). |
| **FR-C16** | Room elevation **shall** be grantable only by explicit principal gesture (`/admin once`, `/admin on` with confirm, etc.). |
| **FR-C17** | `/admin once` **shall** require confirmation (`yes`/`no` in a short confirmation window, or reaction/button when available) before arming. |
| **FR-C18** | Armed `once` elevation **shall** apply to the next non-command wake in that room and then consume itself. |
| **FR-C19** | TTL-based elevation (if implemented) **shall** expire automatically; recommended default TTL **15 minutes** for `/admin on`. |
| **FR-C20** | Every grant, deny, expire, and consume event **shall** be written to the operator log (audit). |
| **FR-C21** | Effective mode for a wake **shall** be: elevation if active, else `resolve_approval_mode(...)`. |
| **FR-C22** | Elevation state **shall** persist in operator state (`state.json` or adjacent) across operator restarts until consumed/expired. |

### 3.4 Mission control content

| ID | Requirement |
| --- | --- |
| **FR-C23** | `/status` card **shall** include: operator online/ws, effective mode + elevation, session id (or none), cwd + resolve reason, last wake time/rc/stopReason if known, queue/lock summary. |
| **FR-C24** | Optional pinned status (`RC_STATUS_PIN=1`) **shall** use a single pin updated via `chat.update`, not repeated new posts. |
| **FR-C25** | Status content **shall not** include secrets or full env. |

### 3.5 Non-functional requirements

| ID | Requirement |
| --- | --- |
| **NFR-C1** | Command responses (non-wake) **should** complete within **2 seconds** on a healthy operator. |
| **NFR-C2** | Command handling **shall** be unit-tested without network where pure (parse, allowlist, elevation state machine). |
| **NFR-C3** | Confirmation windows **should** default to **60 seconds**; expired confirm **shall** deny. |
| **NFR-C4** | Help text **should** be rate-limited to avoid spam loops. |
| **NFR-C5** | Implementation **shall** keep existing usability contracts for non-command wakes. |

### 3.6 Security requirements

| ID | Requirement |
| --- | --- |
| **SR-C1** | No shell interpolation of principal args (`subprocess` list form / pure Python only). |
| **SR-C2** | `/cwd pin` **shall** reject symlink escapes and `..` traversal outside allowlist. |
| **SR-C3** | Global forever-admin from phone **should not** be the only elevation path; prefer once/TTL. |
| **SR-C4** | Cancel **shall** only kill processes whose PID is recorded as the room’s wake child of this operator. |

---

## 4. Architecture and design decisions

### 4.1 Selected approach (research C1)

**Operator-native interceptor** in the principal message path:

```
principal message
    → if command: dispatch_command → reply as grok → mark processed
    → else: existing Thinking… → wake → finalize path
```

Apps-Engine slash commands / UI kit buttons are **v2** (OD-C2), not v1 blockers.

### 4.2 Decision record

| Decision | Choice | Rationale | Rejected |
| --- | --- | --- | --- |
| D1 Command host | Operator Python | Fits existing trust filter; fast ship | NL-only control |
| D2 Elevation scope | Room + once/TTL | Blast radius (IMP-01) | Launchd-only elevation |
| D3 Confirm UX v1 | Textual yes/no in-thread | Works on mobile without app | Require Apps-Engine for v1 |
| D4 Session reset | Clear pin only (lazy new session) | Simple; next wake creates session | Eager session create always |
| D5 Retry buffer | Last non-command text per room | Useful after elevation | Infinite history |

### 4.3 Elevation state machine

```
NONE
  --/admin once--> PENDING_CONFIRM(once)
  --yes--> ARMED_ONCE
  --no/timeout--> NONE
  --next wake consumes--> NONE (after that wake uses admin)

NONE
  --/admin on--> PENDING_CONFIRM(ttl)
  --yes--> ARMED_TTL(expires_at)
  --expire/off--> NONE
```

`build_wake_argv` / wake path reads:

```
effective_mode = admin if elevation_active(room) else resolve_approval_mode(...)
```

### 4.4 State schema (proposed)

```json
{
  "room_elevation": {
    "<roomId>": {
      "mode": "admin",
      "uses_remaining": 1,
      "expires_at": "2026-07-11T04:00:00+00:00",
      "armed_at": "...",
      "armed_by": "principal"
    }
  },
  "pending_confirm": {
    "<roomId>": {
      "kind": "admin_once",
      "expires_at": "..."
    }
  },
  "last_content_by_room": {
    "<roomId>": {
      "text": "...",
      "mid": "...",
      "ts": "..."
    }
  }
}
```

Store alongside existing session/cwd pins in operator state with atomic write patterns already used by `save_state`.

---

## 5. Integration contracts

### 5.1 Wake path

| Integration | Contract |
| --- | --- |
| Enqueue | Commands short-circuit before Thinking… (except explicit wake commands) |
| Approval | Elevation overrides env mode per FR-C21 |
| Streaming (NF-SPEC-02) | `/status` reads `last_stop_reason` / last wake fields when present |
| Locks | `/cancel` interacts with per-room wake lock + child PID |
| Processed ids | Commands mark processed like failed/empty paths — no reprocessing loops |

### 5.2 Existing helpers to reuse

| Helper | Use |
| --- | --- |
| `resolve_approval_mode` | Base mode |
| `get_room_session_id` / `set_room_session_id` | `/new`, `/status` |
| `get_room_cwd` / `set_room_cwd` | `/cwd` |
| `resolve_project_cwd` | Show reason (map/pin/dm) |
| `health.json` / health check script | `/health` |
| `approval_mode_cli_flags` | Unchanged; receives effective mode |

### 5.3 Call path (Feature 1)

v1 control plane **may** omit call controls. Future: `/call status` once voice worker exposes a control socket (OD-C3). Must not block v1 text control plane.

### 5.4 PGS / notify

Hourly PGS posts remain a separate path. Control plane **shall not** double-post research memos. Status pin is orthogonal and must obey single-pin update rules.

---

## 6. Interfaces and control surfaces

### 6.1 Command reference (v1 normative set)

| Command | Args | Behavior | Wakes Grok? |
| --- | --- | --- | --- |
| `/help` | — | List commands | No |
| `/status` | — | Mission card | No |
| `/health` | — | Operator/RC health | No |
| `/new` | — | Clear session pin | No |
| `/session show` | — | Show session | No |
| `/session reset` | — | Alias `/new` | No |
| `/cwd` | — | Show cwd + reason | No |
| `/cwd pin` | `<path>` | Pin if allowlisted | No |
| `/cwd clear` | — | Clear pin | No |
| `/mode` | — | Effective mode + elevation | No |
| `/admin once` | — | Confirm → arm one admin wake | No |
| `/admin on` | — | Confirm → TTL admin | No |
| `/admin off` | — | Clear elevation | No |
| `/cancel` | — | Kill room wake if any | No |
| `/retry` | — | Re-wake last content | **Yes** |
| `/wake` | `<text>` | Wake with text | **Yes** |
| `/ask` | `<text>` | Wake with text | **Yes** |
| `yes` / `no` | — | Only if `pending_confirm` active | No |

### 6.2 Confirmation protocol (v1)

1. Principal sends `/admin once`.  
2. Bot: “Confirm admin for **next wake** in this room? Reply `yes` or `no` within 60s.”  
3. Principal `yes` → arm; `no`/timeout → none.  
4. Next content message consumes arm and runs with admin flags.

### 6.3 Configuration (proposed)

| Variable | Default | Meaning |
| --- | --- | --- |
| `RC_CONTROL_PLANE` | `1` after soak (may ship first PR as `0` then enable) | **Master switch** — `0` disables interceptor; all messages use legacy wake path (NF-IP-03 rollback) |
| `RC_ELEVATION` | `1` | When `0`, `/admin*` commands refuse without affecting other commands |
| `RC_CMD_PREFIXES` | `/,!` | Recognized prefixes |
| `RC_ADMIN_CONFIRM_S` | `60` | Confirm window |
| `RC_ADMIN_TTL_S` | `900` | TTL for `/admin on` |
| `RC_STATUS_PIN` | `0` | Sticky pin status |
| `RC_CWD_ALLOW_ROOTS` | IdeaProjects + agency | Pin allowlist |

**Normative:** Implementations **shall** honor `RC_CONTROL_PLANE=0` as a full disable that restores pre-feature message routing (no command short-circuit).

### 6.4 Example `/status` card (normative fields)

```text
## Mission control — #Prime-Gap-Structure
- operator: online (pid …, ws ok)
- approval: restricted (elevation: none)
- session: 019f4897-… (pinned) | none
- cwd: …/prime-gap-structure (pinned|map|dm)
- last wake: <iso> rc=<n> stopReason=<…|unknown>
- queue: empty | draining
```

---

## 7. Phased delivery and acceptance criteria

### 7.1 Phases

| Phase | Scope | Exit |
| --- | --- | --- |
| **P0** | `/help` `/status` `/health` `/new` `/cwd` `/mode` | No CLI wake; correct state |
| **P1** | `/admin once` confirm + consume | One elevated wake; then restricted |
| **P2** | `/cancel` `/retry` | Stop runaway; redo last content |
| **P3** | Optional pin status; NF-SPEC-02 field alignment | Shared telemetry |
| **P4** | Apps-Engine slash + buttons | Autocomplete / tap approve |

### 7.2 Acceptance criteria

- [ ] AC-C1: `/status` returns card &lt;2s; no `wake-run-*.log` created for that message.  
- [ ] AC-C2: `/new` clears session pin; next content wake uses new session id.  
- [ ] AC-C3: `/foo` unknown → help; no Grok CLI process.  
- [ ] AC-C4: `/admin once` + `yes` + next content → wake argv contains `--always-approve`; following wake does not.  
- [ ] AC-C5: `/admin once` + `no` → no elevation.  
- [ ] AC-C6: `/cwd pin /etc` rejected; pin under IdeaProjects accepted if exists.  
- [ ] AC-C7: Non-command “hello” still takes Thinking… path unchanged.  
- [ ] AC-C8: Audit log lines exist for elevation grant/consume.  
- [ ] AC-C9: Usability contracts for normal wakes still pass.

### 7.3 Validation strategy

| Layer | Method |
| --- | --- |
| Unit | parse_command, path allowlist, elevation FSM |
| Contract | Mock principal messages: command vs content routing |
| Integration opt-in | Live RC command probe without research wake |
| Security | Path traversal fixtures; cancel PID mismatch fixture |

---

## 8. Risks, dependencies, mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Command injection via args | High | No shell; allowlist paths |
| Accidental long-lived admin | High | Prefer once/TTL; `/mode` visibility |
| yes/no collides with content | Medium | Only honor when pending_confirm active |
| Mobile strips leading `/` | Medium | `!` alias prefix |
| Cancel wrong PID | High | Ownership check |
| State.json corruption | Medium | Atomic saves; schema defaults |
| Feature interaction with streaming | Low | Shared fields only |

### Dependencies

- Operator message handling entry point change  
- State persistence  
- Soft: NF-SPEC-02 for rich stopReason on `/status`  
- Soft: Feature 1 for later `/call` commands  

---

## 9. Open decisions

| ID | Decision | Default if forced |
| --- | --- | --- |
| **OD-C1** | Eager vs lazy new session after `/new` | Lazy (clear pin only) |
| **OD-C2** | When to require Apps-Engine | After P2 stable |
| **OD-C3** | Call control commands | After NF-SPEC-01 V1 |
| **OD-C4** | Retention size for `/retry` text | Last 1 message, max 8k chars |
| **OD-C5** | Extra passphrase for admin | Not required (principal login enough) |
| **OD-C6** | `/ops` cross-room dashboard | P3+ |

---

## 10. Traceability

| Spec element | Research anchor |
| --- | --- |
| Command set | Research §3.1 |
| Elevation flows | Research §3.2 |
| Mission control card | Research §3.3 |
| Approach C1 | Research §4 / §8 |
| IMP-01 alignment | Research §2.4; `wake_lib.resolve_approval_mode` |
| Stack | `docs/architecture.md`, operator health artifacts |

---

## 11. Document control

- Normative for future implementation goals adopting NF-SPEC-03.  
- Research retained at `research.md` in this bundle.  
- Breaking changes to principal-only trust or default unrestricted elevation require a new major spec version.
