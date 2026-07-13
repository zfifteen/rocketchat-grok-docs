# Technical Specification: Lead–Peer Full Collab (Grok lead · AGY full peer)

| Field | Value |
| --- | --- |
| **Spec ID** | **NF-SPEC-10** |
| **Version** | 1.1 |
| **Status** | Specification — documentation only (runtime not required by this package) |
| **Date** | 2026-07-12 · **Rev 1.1:** adversarial review mitigations ([REVIEW.md](./REVIEW.md)) |
| **Mode id** | `lead_peer_full` |
| **Parent / prior art** | [NF-SPEC-04](../04-agy-rocketchat-collab/spec.md) (dual identity, tag-to-talk, CLI-only agy); [NF-SPEC-09](../09-agy-collab-enablement/spec.md) (arming / enablement); [profiles](../04-agy-rocketchat-collab/profiles/) |
| **Test plan** | [test-plan.md](./test-plan.md) (**NF-TP-10**) |
| **Implementation plan** | [implementation-plan.md](./implementation-plan.md) (**NF-IP-10** — fine-grained `!goal` ladder) |
| **Primary runtime surface** | `~/.grok/agency/ops/rocketchat/wake/` (`rc_operator_agent.py`, `rc_collab.py`, `rc_commands.py`, `wake_lib.py`) |
| **Related** | NF-SPEC-02 (Thinking bubble), NF-SPEC-03 (control plane / `!` prefix), IMP-01 (approval), `NO_DUPLICATE_POSTS.md`, skill `agy-cli-collab` |

---

## 1. Problem and context

### 1.1 Problem

The live Rocket.Chat integration is a strong **principal → Grok** operator. Dual-peer collab (NF-SPEC-04) defines dual RC identities and @mention handoffs, but pure tag-to-talk does not match the desired product story:

> In a purpose-created channel such as `#grok-agy-collab`, the principal posts an **untagged** goal (e.g. `Build me a simple TODO app`). **Grok is always channel lead** (intake). **AGY is a full peer** (not an optional reviewer add-on). The two agents follow a protocol until the task is complete or stopped.

AGY is a paid, highly capable backend. Under-using it (solo Grok delivery with a token “LGTM?” ping) is a **protocol failure**, not success.

### 1.2 Context (live stack facts)

| Element | Fact |
| --- | --- |
| Operator | Single KeepAlive process: `rc_operator_agent.py` |
| Grok path | Thinking… → headless Grok CLI → `chat.update` as `grok` |
| Trust filter (non-collab) | Principal-only wakes in DMs/normal rooms |
| Gemini path | Local `agy` CLI + `agy-cli-collab` skill; **never** MCP `agy_*` |
| Collab helpers | `rc_collab.py` (mention parse, hop budget, agy lock, pure FSM pieces) |
| Control plane | NF-SPEC-03; Rocket.Chat steals `/` — prefer **`!`** |
| Gap | No production dual-auth posts as `agy`; no lead intake; no peer bar; profiles not installed |

### 1.3 Spec purpose

Define the **normative engineering contract** for room mode **`lead_peer_full`**: classifier, epoch/phase/peer-bar state, dual backends, injects, control plane, acceptance criteria, and non-goals — sufficient to implement without re-deriving product intent.

### 1.4 Relationship to NF-SPEC-04 / 09

| Spec | Role |
| --- | --- |
| **NF-SPEC-04** | Baseline: dual identities, C3 dual voice, CLI-only agy, no nested primary UX, self-wake filter |
| **NF-SPEC-09** | Enablement: master flag, arm/disarm, hop budget ops, doctor cutover |
| **NF-SPEC-10 (this)** | **Normative v1 room protocol** for purpose-created collab channels: lead intake + full peer utilization |

Where this spec and NF-SPEC-04 conflict on room behavior for `lead_peer_full`, **this spec wins**. Symmetric pure tag-to-talk without lead intake remains an optional future mode, not v1 default for `#grok-agy-collab`.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
| --- | --- |
| G1 | Principal can post **untagged** goals in a purpose-created collab channel and have work start. |
| G2 | **Grok is always lead** for intake of untagged principal tasks in that channel. |
| G3 | **AGY is a full peer**: substantive co-work is required on non-trivial epochs; not an optional polish step. |
| G4 | Each agent posts as its **own RC identity** (`grok` / `agy`) with Thinking… → `chat.update`. |
| G5 | Bot→bot continuation uses **real @mentions** on the floor (observable handoffs). |
| G6 | Epoch state (goal, hops, phase, peer bar, sessions) **survives** operator restart. |
| G7 | Safety stops **runaway cost/spin** (hop budget, pause) without forbidding productive depth. |
| G8 | Gemini backend remains **local `agy` CLI only**. |
| G9 | Single operator process; no second KeepAlive collab daemon required for v1. |
| G10 | Principal retains pause/complete/budget control via **`!collab`** commands. |

### 2.2 Non-goals

| ID | Non-goal |
| --- | --- |
| NG1 | Implementing runtime in this documentation package. |
| NG2 | Multi-tenant public collab or non-allowlisted authors. |
| NG3 | MCP `agy_*` transport. |
| NG4 | Faking two voices under one RC user. |
| NG5 | Nested `agy` inside Grok wakes as **primary** collab UX. |
| NG6 | Symmetric dual intake (AGY also picks up untagged principal goals). |
| NG7 | Parallel dual wakes on one message. |
| NG8 | Voice/Call dual-agent mode. |
| NG9 | Replacing project domain `AGENTS.md` with collab transport rules. |

---

## 3. Roles and product model

### 3.1 Fixed roles (`lead_peer_full`)

| Role | RC username | Responsibility |
| --- | --- | --- |
| **Supervisor** | `principal` | Posts goals, steers, `!collab` control, accepts done |
| **Lead** | `grok` | **All untagged principal messages** (intake); orchestration; integration; local tools/cwd; final Done summary when peer bar met |
| **Peer (full)** | `agy` | Full reasoning/compute peer; owns assigned packages; may implement in owned paths; adversarial pass; **does not** intake untagged principal tasks |

**Normative framing:** Lead is **conductor + integrator**, not soloist. Room lead ≠ sole intellect. Phase leadership may pass to AGY inside an epoch while channel intake remains Grok.

### 3.2 Example purpose-created channel

- Name: `#grok-agy-collab` (or equivalent).  
- Members **shall** include at least: `principal`, `grok`, `agy`.  
- Room **shall** be private for v1.  
- Room profile **shall** set `mode=lead_peer_full` (see §5).

### 3.3 Example principal message

```text
Build me a simple TODO app
```

No `@` required. Dispatcher **shall** treat this as **lead intake** when the room is armed and mode is `lead_peer_full`.

---

## 4. Architecture

### 4.1 Component diagram (normative)

```text
Rocket.Chat room (lead_peer_full)
        │ stream-room-messages
        ▼
rc_operator_agent (single process)
        │
        ├─ control plane (!collab …) ──► state mutate + short reply
        │
        └─ collab classifier + epoch FSM
                │
                ▼
         enqueue WakeJob { target, kind, mid, epoch_id }
                │
         per-room wake lock (serial turns v1)
                │
        ┌───────┴────────┐
        ▼                ▼
 target=grok        target=agy
 REST as grok       REST as agy
 Thinking…          Thinking…
 Grok CLI           agy CLI (global serialize lock)
 reply file         reply file
 chat.update        chat.update
 session pin        conversation UUID pin
```

### 4.2 Design constraints

| ID | Constraint |
| --- | --- |
| **AR-1** | One dispatcher owns protocol; two backends differ by auth + CLI + inject. |
| **AR-2** | Handoffs **shall** be triggered by **posted RC messages** with observable mentions, not silent cross-CLI calls. |
| **AR-3** | Nested primary collab (Grok shelling `agy` instead of `@agy`) **shall** be forbidden in collab inject for this mode. |
| **AR-4** | v1 collab room wakes **shall** be **serial** (one active wake per room). |
| **AR-5** | All `agy` CLI invocations **shall** take the global agy serialize lock (skill contract). |

### 4.3 Dual REST identity

The operator **shall** maintain authenticated clients for both `grok` and `agy`:

| Identity | Credentials (secrets; never committed / never in model prompt) |
| --- | --- |
| `grok` | Existing operator secrets |
| `agy` | `ROCKETCHAT_AGY_USERNAME` / `ROCKETCHAT_AGY_PASSWORD` and/or token pair |

Posts and `chat.update` for a wake **shall** use the target identity’s auth. DDP may remain a single connection if both users are room members; attribution of bubbles **shall not** rely on forging username in content alone.

---

## 5. Room profile configuration

### 5.1 Profile schema (normative fields)

```json
{
  "room_id": "<rid>",
  "name": "grok-agy-collab",
  "mode": "lead_peer_full",
  "lead": "grok",
  "peer": "agy",
  "principal_untagged": "lead_intake",
  "agent_untagged": "ignore",
  "peer_bar": {
    "min_substantive_peer_turns": 1,
    "require_adversarial_before_done": true,
    "trivial_max_goal_chars": 80,
    "trivial_requires_explicit": true,
    "trivial_bypass_patterns": ["^(?i)(fix|typo|nit)\\b"]
  },
  "phases": ["frame_split", "peer_deep", "integrate", "adversarial", "close"],
  "hop_budget": 12,
  "cwd": "<absolute path>",
  "write_scope": {
    "lead_default": "apply",
    "peer_default": "apply_owned_paths",
    "owned_paths_from_handoff": true,
    "owned_paths_must_be_under_cwd": true
  },
  "armed": true
}
```

Default **`hop_budget` is 12** (not 30) for cost control; principal may raise via `!collab budget` for deep work.

### 5.2 Profile requirements

| ID | Requirement |
| --- | --- |
| **FR-P1** | `mode` **shall** be `lead_peer_full` for this protocol. |
| **FR-P2** | `lead` **shall** be `grok` for v1 purpose-created channels of this type. |
| **FR-P3** | `peer` **shall** be `agy` (or `RC_AGY_USER` equivalent). |
| **FR-P4** | `principal_untagged` **shall** be `lead_intake`. |
| **FR-P5** | Master env `RC_AGY_COLLAB` (or NF-SPEC-09 master flag) **shall** be enabled for any collab routing. |
| **FR-P6** | Room **shall** be explicitly armed (`armed=true` or `!collab on`) before dual-peer or lead-intake wakes. |
| **FR-P7** | When master off or room disarmed, operator **shall** retain non-collab behavior for that room (no bot↔bot; no AGY intake). |
| **FR-P8** | Profile default `hop_budget` **shall** be ≤ **12** unless principal explicitly configures higher (cost default). |

---

## 6. Durable state

### 6.1 Storage

Collab state **shall** live in operator `state.json` (or successor single state store), keyed by `room_id`. State **shall** survive operator restart and Mac sleep.

### 6.2 Epoch object (normative)

```json
{
  "id": "e_<opaque>",
  "goal": "<principal text>",
  "status": "active|paused|done|failed",
  "opened_at": "<iso8601>",
  "opened_by_mid": "<message id>",
  "hop": 0,
  "budget": 12,
  "phase": "frame_split",
  "phases_done": [],
  "peer_substantive_turns": 0,
  "adversarial_done": false,
  "trivial": false,
  "trivial_reason": null,
  "goal_amendments": [],
  "contribution": { "grok": [], "agy": [] },
  "last_handoff": {
    "from": "grok|agy",
    "to": "grok|agy",
    "mid": "<id>",
    "ask_type": "design|implement|adversarial|other|none",
    "ask_summary": "<short>"
  }
}
```

### 6.3 Session pins

| Key | Meaning |
| --- | --- |
| `sessions.grok_session_id` | Grok CLI `--resume` pin for room |
| `sessions.agy_conversation_id` | Sticky `agy` conversation UUID for room |

### 6.4 Epoch lifecycle

| ID | Requirement |
| --- | --- |
| **FR-E1** | **Open:** principal untagged (or lead-targeted) message when no active epoch → create epoch, `status=active`, `phase=frame_split`, store goal + mid. |
| **FR-E2** | **Amend / steer:** principal untagged while epoch `active` → **shall not** open a second concurrent epoch; **shall** wake lead with steer context (amendment), same `epoch.id`. |
| **FR-E3** | **Pause:** `!collab pause` or budget exhaust → `status=paused`; no agent→agent handoff enqueues. |
| **FR-E4** | **Resume:** `!collab resume` → `active` if budget remains. |
| **FR-E5** | **Done:** only if peer bar satisfied (§8) or principal `!collab complete` override. |
| **FR-E6** | **New task after done:** next qualifying principal message opens a **new** epoch id. |
| **FR-E7** | **Lock-before-classify:** for each inbound collab-room message, the operator **shall** acquire the per-room wake/serialization lock (or equivalent room mutex) **before** reading epoch status and deciding LeadIntake vs LeadSteer vs open-epoch, so rapid successive messages cannot create two concurrent epochs (FR-E2). |

---

## 7. Classifier (message → action)

### 7.1 Action types

```text
ControlPlane
LeadIntake(goal)
LeadSteer(text)
DirectPeer(text)          # optional principal @agy
Handoff(to, from, mid)
Reject(reason)
Ignore
```

### 7.2 Allowlist

| ID | Requirement |
| --- | --- |
| **FR-C1** | Collab wakes **shall** only consider authors in `{principal, grok, agy}` (configurable names via env). |
| **FR-C2** | Non-allowlisted authors **shall** be Ignore. |
| **FR-C3** | In collab rooms with mode `lead_peer_full`, the operator **shall** accept messages from `grok` and `agy` for handoff classification (override pure principal-only filter). |

### 7.3 Decision table (normative)

**Order is security-sensitive.** Author checks **shall** run before control-plane execution. Agents **shall never** execute collab control commands.

| # | Condition | Action |
| --- | --- | --- |
| 0 | author ∉ allowlist | **Ignore** |
| 1 | Text matches control plane shape (`!collab…` / yes\|no confirm) **and** author ≠ principal | **Ignore** (log `collab_ctrl_rejected author=…`) — **no** state mutation |
| 2 | Text matches control plane **and** author = principal | **ControlPlane** (then FR-K*) |
| 3 | room paused (non-control traffic) | Ignore handoffs/intake; principal control still via #2 |
| 4 | author=principal, no agent mention, no active epoch | **LeadIntake** |
| 5 | author=principal, no agent mention, active epoch | **LeadSteer** |
| 6 | author=principal, mentions only lead (`grok`) | LeadSteer or LeadIntake if no epoch |
| 7 | author=principal, mentions only peer (`agy`) | DirectPeer **or** Reject — **OD-10-1** (default recommend: allow DirectPeer) |
| 8 | author=principal, mentions both agents | Reject with help (mention one target) |
| 9 | author=lead, mentions peer only (not lead, not both) | **Handoff→peer**, hop++ |
| 10 | author=peer, mentions lead only (not peer, not both) | **Handoff→lead**, hop++ |
| 11 | author ∈ {lead, peer}, mentions **both** agents | **Reject** (ambiguous dual handoff) — **shall not** Ignore silently |
| 12 | author ∈ {lead, peer}, no agent mention | Ignore |
| 13 | self-mention only | Ignore (self-wake filter) |
| 14 | Handoff would exceed hop budget | Stop card; pause; no enqueue |
| 15 | Parallel multi-target agent wake | Forbidden |

### 7.4 Lead intake (critical)

| ID | Requirement |
| --- | --- |
| **FR-C20** | Untagged principal messages in armed `lead_peer_full` rooms **shall** enqueue **lead (grok)** only. |
| **FR-C21** | AGY **shall never** be selected for untagged principal intake in this mode. |
| **FR-C22** | Optional seatbelt: profile may require prefix (e.g. `!do `) for intake; if unset, any non-command principal text qualifies. |

### 7.5 Mention detection

| ID | Requirement |
| --- | --- |
| **FR-C30** | Prefer Rocket.Chat structured `mentions[]` when present. |
| **FR-C31** | Fallback: word-boundary `@username` parse, case-insensitive for configured lead/peer names. |
| **FR-C32** | Bot handoff replies **shall** include a real peer mention the dispatcher can observe (lab-verify on RC 8.6). |

---

## 8. Peer bar and phases (full-peer enforcement)

### 8.1 Rationale

Without enforcement, lead models solo-complete and under-use AGY. The peer bar makes full utilization **machine-checkable**.

### 8.2 Phases

Ordered phases (hints, not a rigid spoken script):

```text
frame_split → peer_deep → integrate → adversarial → close
```

| Phase | Intent |
| --- | --- |
| `frame_split` | Lead frames goal, constraints, work split |
| `peer_deep` | Peer owns a real package (reasoning / design / implement slice) |
| `integrate` | Lead integrates, runs tools, applies on Mac |
| `adversarial` | Peer attacks gaps / edge cases / simpler design |
| `close` | Lead Done + contribution map |

### 8.3 Phase transitions (normative minimum)

| ID | Requirement |
| --- | --- |
| **FR-B1** | Epoch open → `phase=frame_split`. |
| **FR-B2** | First accepted lead→peer handoff → operator **shall** treat peer work as `peer_deep` path. |
| **FR-B3** | After a **substantive** peer turn returning to lead → `peer_substantive_turns += 1`; phase hint → `integrate` if still early. |
| **FR-B4** | Lead→peer handoff with `ask_type=adversarial` (footer or equivalent) → phase → `adversarial`. |
| **FR-B5** | Substantive peer reply after adversarial ask → `adversarial_done=true`. |

### 8.4 Peer bar close rules

| ID | Requirement |
| --- | --- |
| **FR-B10** | Non-trivial epoch **shall not** transition to `done` unless `peer_substantive_turns >= min_substantive_peer_turns`. |
| **FR-B11** | If `require_adversarial_before_done` is true, non-trivial epoch **shall not** done unless `adversarial_done`. |
| **FR-B12** | Trivial peer-bar bypass **shall not** rely on goal-prefix regex alone. See §8.5a. |
| **FR-B13** | If lead claims Done but bar fails, operator **shall** refuse close, keep epoch `active`, and emit a short protocol notice (prefer updating/finalizing without a second long answer bubble; one short protocol line is allowed). |
| **FR-B14** | Principal `!collab complete` **may** override peer bar (logged). |

### 8.5 Substantive peer turn

A peer turn **shall** count as substantive only if **all** of the following hold:

1. The footer (if any) was accepted under **FR-F4…F6** (wake-finalize of **peer** identity only); and  
2. Body is not pure rubber-stamp (LGTM-only patterns); and  
3. At least one of: body length ≥ threshold; structured decision content; non-empty sanitized `owned_paths`.

Footer flag `peer_substantive: 1` alone **shall not** mark substantive without (2)+(3).

**FR-B20:** Pure “LGTM” / “looks good” peer replies **shall not** increment `peer_substantive_turns`.

### 8.5a Trivial bypass (anti-gaming)

| ID | Requirement |
| --- | --- |
| **FR-B30** | Default profile **shall** set `trivial_requires_explicit=true`. |
| **FR-B31** | When `trivial_requires_explicit` is true, epoch is trivial **only** if principal issues `!collab trivial` (while epoch active or as part of intake policy) — **not** because the goal text matches a regex. |
| **FR-B32** | If implementers enable regex assist (`trivial_bypass_patterns`), it **shall** also require `len(goal) <= trivial_max_goal_chars` (default **80**) and **shall not** treat a match as trivial when the remainder of the goal after the first token is longer than `trivial_max_goal_chars` or contains build/implement intent keywords (configurable denylist, e.g. `build`, `implement`, `architecture`, `microservice`). |
| **FR-B33** | “Fix the world: build …” style goals **shall** remain non-trivial under default policy. |

### 8.6 Default collaboration graph (inject guidance)

For non-trivial goals, lead inject **shall** prescribe approximately:

1. Frame + split → `@agy` with **real package**  
2. Peer deep pass → `@grok`  
3. Lead integrate  
4. `@agy` adversarial  
5. Lead close with contribution map  

Under-using AGY on non-trivial goals is defined as **protocol failure** in lead inject (§10).

---

## 9. Wake pipeline

### 9.1 WakeJob

```text
WakeJob {
  room_id, mid, epoch_id,
  target: "grok" | "agy",
  kind: "intake" | "steer" | "handoff" | "direct_peer",
  approval_mode, cwd, model/effort pins...
}
```

### 9.2 Shared steps (both targets)

| Step | Requirement |
| --- | --- |
| Lock | Acquire per-room wake lock; serial v1 (**also** before classify — FR-E7) |
| Placeholder | Post `Thinking...` **as target identity** only (FR-ID1) |
| Inject | Build role + epoch + phase + peer bar + last relevant peer/principal text; **strip any `---rc-collab---` blocks from untrusted principal/peer history before inject** (FR-F7) |
| Backend | Spawn CLI with timeout / max turns |
| Reply | Read reply file only (no second answer post) |
| Footer | Parse machine footer **only from this wake’s reply file** as the **current target** (FR-F4); strip before user-visible body if configured |
| Finalize | `chat.update` placeholder as **same** target identity |
| State | Update epoch, sessions, contribution, substantive flags |
| Unlock | Release room lock |

### 9.3 Grok backend

| ID | Requirement |
| --- | --- |
| **FR-W1** | Use existing headless Grok wake path (`build_wake_argv`, session resume). |
| **FR-W2** | Apply IMP-01 approval mode (restricted default). |
| **FR-W3** | Collab inject **shall** forbid nesting `agy` CLI as primary handoff. |

### 9.4 AGY backend

| ID | Requirement |
| --- | --- |
| **FR-W10** | Spawn local `agy` / skill helper only; hold global agy CLI lock for entire invocation. |
| **FR-W11** | Use sticky `agy_conversation_id` when present; create and pin on first peer wake. |
| **FR-W12** | Thinking + finalize **as `agy`**. |
| **FR-W13** | Separate timeout env (e.g. `RC_AGY_WAKE_TIMEOUT_S`) **should** exist; default may exceed Grok wake timeout. |
| **FR-W14** | On failure: FINAL_ERR on the same Thinking bubble (NF-SPEC-02 parity). |

### 9.5 Hop accounting

| ID | Requirement |
| --- | --- |
| **FR-W20** | Hop increments on **accepted agent→agent handoff enqueue**, not on principal steers. |
| **FR-W21** | At budget exhaust: post stop card; set paused; no further handoff enqueues until resume/budget raise. |

### 9.6 NO DUPLICATE POSTS

| ID | Requirement |
| --- | --- |
| **FR-W30** | One answer bubble per wake: Thinking → update. |
| **FR-W31** | Outbound media only via `rc_post_media.py` (idempotent), as the posting identity. |

---

## 10. Injects, profiles, and machine footer

### 10.1 Layering

```text
L1  Project AGENTS.md     → domain law (unchanged)
L2  Role profiles         → lead vs peer social contract
L3  Per-turn inject       → epoch, phase, peer bar, last message, cwd, scope
```

### 10.2 Lead inject (normative content)

Lead (Grok) L2/L3 **shall** include:

- You are **Lead** in this room; untagged principal tasks are yours.  
- **AGY is a full peer**, not a reviewer add-on; under-use on non-trivial goals is failure.  
- Assign **real work packages** via `@agy` (design, adversarial, or implement slice).  
- You own integration, local tools, and Done **after** peer bar.  
- Do not nest `agy` CLI; use floor mentions.  
- Done summary **shall** include a contribution map (what each agent owned).  
- Emit machine footer (§10.3).

### 10.3 Peer inject (normative content)

Peer (AGY) L2/L3 **shall** include:

- You are **full peer**, not intake and not rubber-stamp.  
- Use full reasoning/compute; own your package; disagree when wrong.  
- Return with `@grok`; optional owned_paths for implement scope.  
- Do not claim untagged principal goals.  
- Emit machine footer.

### 10.4 Machine footer

Both backends **should** append a parseable footer (stripped from visible body when possible):

```text
---rc-collab---
epoch: <id>
role: lead|peer
phase_hint: frame_split|peer_deep|integrate|adversarial|close
status: active|done|blocked
handoff: agy|grok|none
ask_type: design|implement|adversarial|other|none
owned_paths: <glob list or empty>
contribution: <short>
peer_substantive: 0|1
---rc-collab---
```

| ID | Requirement |
| --- | --- |
| **FR-F1** | Footer alone **shall not** enqueue a wake; visible `@mention` still required for handoff. |
| **FR-F2** | `status=done` accepted **only** from a **lead** wake finalize footer (FR-F4) triggers peer-bar check before epoch close. |
| **FR-F3** | Invalid/missing footer **shall not** crash the wake; operator uses heuristics. |
| **FR-F4** | Operator **shall** parse footers **only** from the **reply file of the wake just completed**, attributed to `WakeJob.target` (`grok` or `agy`). |
| **FR-F5** | Footers appearing in **principal messages**, inbound history, or quoted text **shall be stripped/ignored** for state mutation (not trusted). |
| **FR-F6** | Role in footer **shall** match wake target (`lead` iff target=grok; `peer` iff target=agy); mismatch → ignore footer fields for bar/done/substantive. |
| **FR-F7** | When building inject, operator **shall** strip `---rc-collab---` blocks from untrusted prior messages so agents cannot be fed spoofed machine state as “history.” |
| **FR-F8** | `peer_substantive` / `status=done` in a spoofed principal goal **shall not** affect epoch counters. |

### 10.5 Handoff quality (should)

Lead handoffs that are only “thoughts?” / “LGTM?” **should** be discouraged in inject; optional operator warn if ask_type missing and body matches weak patterns.

### 10.6 Write scope and path sandbox

| ID | Requirement |
| --- | --- |
| **FR-S1** | Lead default write scope **shall** be configurable (`apply` recommended for pinned scratch cwd). |
| **FR-S2** | Peer **shall not** be permanently demoted to propose-only if full-peer is claimed; v1 **shall** allow `apply_owned_paths` when handoff/footer specifies paths. |
| **FR-S3** | Integration conflicts: lead merges; principal breaks ties. |
| **FR-S4** | Every path in `owned_paths` **shall** be resolved with `Path.resolve()` (or equivalent) and **shall** be a descendant of the room `cwd` resolve root. |
| **FR-S5** | Paths containing `..` segments that escape `cwd`, absolute paths outside `cwd`, symlinks escaping `cwd` (when detectable), or empty/globs that expand outside `cwd` **shall** be **rejected**; reject **shall not** grant apply outside sandbox. |
| **FR-S6** | On reject, operator **should** log `owned_path_rejected` and treat peer write scope as propose-only for that turn. |

### 10.7 Dual REST identity isolation

| ID | Requirement |
| --- | --- |
| **FR-ID1** | Auth token cache **shall** be keyed by identity (`grok` \| `agy`); a request for identity A **shall never** use B’s token. |
| **FR-ID2** | `postMessage` / `chat.update` for a wake **shall** use only `WakeJob.target`’s client. |
| **FR-ID3** | Concurrent wakes (if ever allowed later) **shall not** share mutable “current token” globals; v1 serial lock makes this easier but **shall not** be the only isolation. |
| **FR-ID4** | Unit/integration tests **shall** assert no cross-identity post under concurrent mock load (TP-10-B-01 / B-01b). |

---

## 11. Control plane

Rocket.Chat client intercepts `/…`. Commands **shall** use **`!` prefix** (and any `RC_CMD_PREFIXES`).

| Command | Behavior |
| --- | --- |
| `!collab status` | armed, epoch id/goal/status/phase/hop/budget, peer bar, session pins (no secrets) |
| `!collab pause` | pause epoch / block handoffs |
| `!collab resume` | resume if budget allows |
| `!collab complete` | principal force-done (override peer bar; log) |
| `!collab budget <n>` | set remaining hop budget (cap max, e.g. 50) |
| `!collab trivial` | mark active epoch trivial **only** if FR-B30…B33 policy allows; principal-only |
| `!collab new` | close/abandon active epoch; next intake opens fresh |
| `!collab doctor` | check: master flag, room armed, both users in room, agy CLI path, cwd exists, dual auth probe |
| `!collab on` / `off` | arm/disarm room (NF-SPEC-09) |

| ID | Requirement |
| --- | --- |
| **FR-K1** | Collab control commands **shall** be principal-only (**enforced before dispatch**, decision table #0–#2). |
| **FR-K1a** | If `grok` or `agy` posts text matching `!collab…`, operator **shall** Ignore for control purposes (no pause/complete/budget/arm mutation). Optional: short protocol notice once per epoch that agents cannot drive control plane. |
| **FR-K2** | Commands **shall not** spawn a research Grok wake. |
| **FR-K3** | Unknown `!…` **shall not** start a research wake (NF-SPEC-03). |
| **FR-K4** | `!collab budget <n>` **shall** clamp `n` to a configured maximum (default max **50**) to limit cost bombs. |

---

## 12. Implementation map and build phases

### 12.1 Code map (expected touch points)

| Module | Responsibility |
| --- | --- |
| `wake/rc_collab.py` | profile, classifier, epoch FSM, peer bar, footer parse, agy lock helpers |
| `wake/rc_operator_agent.py` | dual RcClient, author allowlist in collab rooms, WakeJob branch, arm checks |
| `wake/wake_lib.py` | shared argv/session helpers parameterized by target if needed |
| `wake/rc_commands.py` | `!collab *` |
| inject / profiles | lead vs peer L2; wire L3 dynamic block |
| secrets | `ROCKETCHAT_AGY_*` |
| room map / state | `#grok-agy-collab` → `lead_peer_full` profile |
| tests | pure unit classifier + epoch + peer bar; optional integration mocks |

### 12.2 Suggested build phases

| Phase | Deliverable | Exit |
| --- | --- | --- |
| **P0** | Dual auth smoke (post as agy); classifier unit tests for lead intake | Tests green |
| **P1** | Real agy wake (Thinking→CLI→update) + conversation pin | Live @agy handoff works |
| **P2** | Epoch + hop budget + pause + `!collab status` | Budget stop card works |
| **P3** | Peer bar + phases + footer + false-Done block | Solo Done rejected on build goal |
| **P4** | owned_paths write scope | Peer can apply limited paths |
| **P5** | `!collab doctor` + live smoke checklist + docs sync | Cutover ready |

### 12.3 Open decision

| ID | Decision | Default for implementers |
| --- | --- | --- |
| **OD-10-1** | Principal `@agy` direct peer without lead | **Allow** DirectPeer |
| **OD-10-2** | Require `!do` prefix for untagged intake | **Off** (any non-command text) for purpose-created work channels |
| **OD-10-3** | Strip footer from visible message | **Yes** strip |

---

## 13. Acceptance criteria

| ID | Criterion |
| --- | --- |
| **AC-1** | In armed `#grok-agy-collab`, principal message `Build me a simple TODO app` (no @) enqueues **Grok** lead intake and opens an epoch. |
| **AC-2** | Same message does **not** enqueue AGY. |
| **AC-3** | Grok `@agy` with concrete package enqueues AGY wake; Thinking appears **as agy**. |
| **AC-4** | AGY `@grok` returns to lead; hop increments once per handoff. |
| **AC-5** | On non-trivial epoch, lead cannot close Done until peer bar met (or principal override). |
| **AC-6** | LGTM-only peer reply does not satisfy substantive bar. |
| **AC-7** | Hop budget exhaust pauses further bot↔bot wakes and posts a stop card. |
| **AC-8** | `!collab pause` blocks handoffs; `!collab resume` restores when allowed. |
| **AC-9** | Operator restart preserves epoch + session pins; no duplicate processing of completed mids. |
| **AC-10** | No nested primary agy path required for success path; floor mentions suffice. |
| **AC-11** | NO DUPLICATE POSTS holds for both identities. |
| **AC-12** | Disarmed / master-off room does not run lead_peer_full intake. |

---

## 14. Security, cost, and ops

| ID | Requirement |
| --- | --- |
| **FR-X1** | Secrets for `agy` **shall** never appear in inject, reply file, or RC posts. |
| **FR-X2** | Restricted approval remains default for channel wakes unless policy explicitly elevates (IMP-01). |
| **FR-X3** | Hop budget and pause are mandatory cost controls. |
| **FR-X4** | Logs **shall** include `collab=1 target=… kind=… epoch=… hop=…` without tokens. |
| **FR-X5** | `!collab doctor` **shall not** print secrets. |

---

## 15. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Lead solos, peer bar gamed | Heuristics + adversarial flag + inject; tune thresholds |
| Infinite polite @ ping-pong | Default hop budget 12; clamp; handoff quality; pause |
| Merge conflicts dual apply | owned_paths under cwd only (FR-S4…S6); lead integrates; serial wakes |
| Casual chat starts builds | Purpose-created channel only; optional `!do` seatbelt (OD-10-2) |
| agy CLI contention | Global lock; serial room |
| Empty / max-turns wakes | Parity with Grok FINAL_ERR; adequate max turns/timeouts |
| RC `/` slash steal | `!collab` only in docs and help |
| Agent spoofs `!collab` | FR-K1 / K1a; decision table #1 |
| Footer spoof in goal/history | FR-F4…F8 |
| Trivial regex gaming | FR-B30…B33; `!collab trivial` |
| Race double epoch | FR-E7 lock-before-classify |
| REST identity mix-up | FR-ID1…ID4 |

---

## 16. End-to-end normative scenario

1. Principal in `#grok-agy-collab`: `Build me a simple TODO app`.  
2. Classifier → LeadIntake; epoch `e1` opened; phase `frame_split`.  
3. Grok Thinking… → frames + split → posts `@agy` with real package.  
4. Handoff → AGY Thinking… → deep peer work → `@grok` (substantive).  
5. `peer_substantive_turns ≥ 1`; phase → integrate.  
6. Grok implements/integrates → `@agy` adversarial ask.  
7. AGY adversarial → `adversarial_done`; `@grok` must-fix list.  
8. Grok applies fixes → Done + contribution map; peer bar OK → epoch `done`.  
9. Room quiet until next principal task.

---

## 17. Document control

| Version | Date | Notes |
| --- | --- | --- |
| 1.0 | 2026-07-12 | Initial NF-SPEC-10 from lead–peer full design discussion |
| 1.1 | 2026-07-12 | Adversarial review ([REVIEW.md](./REVIEW.md)): control-plane principal gate order; footer trust boundary; trivial anti-gaming; owned_paths sandbox; hop default 12; agent dual-mention Reject; lock-before-classify; REST identity isolation |

**Normative language:** *shall* / *shall not* = requirements; *should* = strong recommendation; *may* = optional.

When implementing, follow [NF-TP-10](./test-plan.md) and [NF-IP-10](./implementation-plan.md). Keep [NF-SPEC-04](../04-agy-rocketchat-collab/spec.md) for baseline dual-peer primitives; treat **this document as the v1 protocol for purpose-created lead–peer rooms**.
