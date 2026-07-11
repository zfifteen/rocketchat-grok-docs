# Test plan: Antigravity (agy) dual-peer collab via Rocket.Chat channel

| Field | Value |
| --- | --- |
| **ID** | NF-TP-04 |
| **Feature** | Long-horizon Grok↔`agy` collab — dual RC accounts, @mention handoffs |
| **Spec** | [`./spec.md`](./spec.md) (NF-SPEC-04) |
| **Research** | [`./research.md`](./research.md) |
| **Profiles** | [`./profiles/`](./profiles/) |
| **Implementation plan** | *(NF-IP-04 deferred — not required by this test-planning package)* |
| **Related** | `rc_operator_agent.py` principal-only filter; `agy-cli-collab` / local `agy`; `NO_DUPLICATE_POSTS.md` per speaker; NF-SPEC-02/03 |
| **Type** | Unit (mention parse, hop/budget FSM) + contract (mock wakes) + lab (mention physics, sticky UUID) + optional live RC multi-hop |
| **Status** | Test-planning documentation only — **no runtime implementation of collab in this package** · **Last reviewed:** 2026-07-11 |
| **Flags under test** | `RC_AGY_COLLAB`, `RC_AGY_USER`, `RC_AGY_PRINT_TIMEOUT`, `RC_AGY_WAKE_TIMEOUT_S`, `RC_AGY_HOP_BUDGET_EPOCH`, `RC_AGY_CHECKPOINT_EVERY`, `RC_AGY_AGENT`, room `mode=agy-collab` |

---

## 1. Scope and traceability

### 1.1 In scope

- Master flag / room profile gating for collab vs legacy principal-only behavior  
- Dual identities (`grok` / `agy`) posting Thinking… → `chat.update` as the correct user  
- Tag-to-talk @mention wake routing (principal and bot↔bot handoff)  
- Author allowlist `{principal, grok, agy}`  
- CLI-only Gemini backend (`agy` helper); MCP `agy_*` forbid  
- No nested `agy` CLI inside Grok collab wakes  
- Per-speaker one-bubble contract (NO_DUPLICATE_POSTS per turn)  
- Long-horizon soft hop budget, pause/resume, spin detection  
- Durable state: Grok session + agy conversation UUID + hop counters across restart  
- L1/L2/L3 profile layering (domain AGENTS, `rc_collab` agent/rules, per-turn inject)  
- Failure honesty on agy CLI fail / timeout  
- Non-collab room regression (principal-only unchanged)

### 1.2 Out of scope

- Implementing the mention dispatcher, dual auth, launchd, or RC user creation **in this docs package**  
- Executing live multi-day unattended collab as a gate for *this documentation goal* (cases are specified for implement-time)  
- Installing profiles into `~/.gemini` or production `wake/` from this package  
- Feature 1 voice dual-agent  
- Full NF-IP-04 implementation plan authoring  
- Apps-Engine slash autocomplete as v1 requirement  

### 1.3 Requirement map (NF-SPEC-04 → cases)

| Spec IDs | Cases |
| --- | --- |
| FR-A0–A3, AC-A12 | TP-A-00, TP-A-01, TP-A-02, E-A-room* |
| FR-A4–A8, AC-A1 | TP-A-10, TP-A-11, E-A-fake-voice |
| FR-A9–A16, AC-A2–A3 | TP-A-20 … TP-A-29, E-A-mention* |
| FR-A17–A23, AC-A4 | TP-A-30 … TP-A-36, E-A-mcp, E-A-timeout |
| FR-A24–A28, AC-A5 | TP-A-40, TP-A-41, E-A-double-post |
| FR-A29–A38, AC-A7–A9 | TP-A-50 … TP-A-58, E-A-budget*, E-A-spin |
| FR-A39–A44, AC-A11 | TP-A-60 … TP-A-64 |
| FR-A20, AC-A10 | TP-A-70, TP-A-71 |
| NFR-A*, SR-A* | TP-A-80 … TP-A-84, E-A-author*, E-A-secret |
| AC-A6 (sticky) | TP-A-55, TP-A-lab-H01 |

---

## 2. Test strategy and layers

| Layer | Proves |
| --- | --- |
| **L0 Unit** | `resolve_mention_targets`, self-wake filter, hop/budget/pause FSM, author allowlist, double-mention policy (OD-A1 lean) |
| **L1 Contract** | Mock room messages → assert target backend (`grok` vs `agy`), auth identity for post/update, no wake when untagged |
| **L2 Backend mock** | Fake `agy_cli.py` / Grok argv capture; assert mode start vs conversation, `--agent rc_collab`, no MCP |
| **L3 State durability** | Reload `state.json` after “operator restart”; UUID + hops retained |
| **L4 Lab (A0)** | Real RC 8.6 REST: post as `agy` with `@grok`; inspect `mentions[]`; optional sticky 3-turn agy print (skill H-01 class) |
| **L5 Live opt-in multi-hop** | Private collab channel end-to-end handoff (implement-time / soak) |
| **L6 Regression** | Unprofiled DM/channel: principal-only; usability contracts for normal wakes |

---

## 3. Preconditions

### 3.1 Documentation / harness (any time)

- Spec NF-SPEC-04 and research present under this bundle  
- Fixtures: temp `state.json`, room profile `mode=agy-collab`, fake clock for cooldown  
- Mockable subprocess for Grok CLI and `agy` helper  

### 3.2 Lab / live (implement-time)

| Need | Notes |
| --- | --- |
| RC users | `principal`, `grok`, **`agy`** (bot) with secrets **not** in git |
| Private channel | e.g. `#grok-agy-collab` with all three members |
| `RC_AGY_COLLAB=1` | Master flag |
| Room profile | Explicit cwd map; no auto-create folder surprise (IMP-19) |
| Local `agy` | Authenticated CLI; helper from `agy-cli-collab` |
| L2 profile | `--agent rc_collab` or rules install from `profiles/` drafts |

### 3.3 Evidence artifacts (implement-time)

- Operator logs: `collab mention`, `collab wake`, `collab hop`, `collab pause`  
- `wake-run-*.log` / agy log with `Created conversation <uuid>`  
- RC message history (usernames + msgIds)  
- `state.json` snapshots before/after restart  

---

## 4. Concrete test cases

### TP-A-00 — Master flag off retains legacy path

| | |
| --- | --- |
| **Phase** | A1 / L1 |
| **Preconditions** | Collab room profile exists but `RC_AGY_COLLAB=0` |
| **Steps** | Principal posts `@agy hello`. Message from `agy` posts `@grok hi` (if simulated). |
| **Expected** | Legacy principal-only path only: principal may wake as today **or** be ignored per current filter rules without dual-peer arming; **no** `agy`-identity Thinking post; bot→bot **shall not** wake (FR-A0). |
| **Pass** | No collab dispatcher arm; no dual-auth post as `agy` |
| **Type** | Contract |

### TP-A-01 — Unprofiled channel never arms bot↔bot

| | |
| --- | --- |
| **Phase** | A1 |
| **Preconditions** | Room without `mode=agy-collab` |
| **Steps** | Principal `@agy`; simulated `agy` `@grok`. |
| **Expected** | No collab dual-peer wakes (FR-A1–A2). |
| **Pass** | Dispatcher skip |
| **Type** | Contract |

### TP-A-02 — Membership incomplete blocks dual-peer arm

| | |
| --- | --- |
| **Phase** | A1 / L4 |
| **Preconditions** | Profile collab but `agy` not in room members |
| **Steps** | Principal `@agy`. |
| **Expected** | Fail closed: no agy wake or clear error; not silent Grok impersonation (FR-A3). |
| **Pass** | Documented fail-closed |
| **Type** | Contract / lab |

### TP-A-10 — Dual avatars on successive turns

| | |
| --- | --- |
| **Phase** | A1 / L5 |
| **Steps** | Principal `@agy` brief; after agy reply with `@grok`, observe grok reply. |
| **Expected** | History shows username **`agy`** then **`grok`** (AC-A1, FR-A4–A7). |
| **Pass** | REST history usernames |
| **Type** | Live / integration |

### TP-A-11 — C3-C fake dual voice forbidden

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Code review / static assert: no path posts Gemini body as `grok` while claiming dual mode. |
| **Expected** | FR-A8: single-username dual voice rejected. |
| **Pass** | Architecture check / no dual-voice poster |
| **Type** | Unit / review |

### TP-A-20 — Tag-to-talk: untagged principal note no wake

| | |
| --- | --- |
| **Phase** | A1 |
| **Preconditions** | Collab armed |
| **Steps** | Principal posts `notes for later` (no @). |
| **Expected** | No Grok CLI; no agy CLI (FR-A9, AC-A2). |
| **Pass** | wake_spawned=false both backends |
| **Type** | Contract |

### TP-A-21 — Principal @agy wakes agy backend only

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Principal `@agy Strongest objection to X. Marker M1.` |
| **Expected** | Thinking… **as `agy`**; `agy` CLI start or conversation; finalize **as `agy`**; no simultaneous Grok research wake (FR-A11, FR-A18). |
| **Pass** | Auth identity + argv/helper call |
| **Type** | Contract |

### TP-A-22 — Principal @grok wakes Grok only

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Principal `@grok Summarize open questions.` |
| **Expected** | Thinking… as `grok`; Grok CLI; no agy CLI (FR-A11, FR-A17). |
| **Pass** | |
| **Type** | Contract |

### TP-A-23 — Bot handoff agy → grok

| | |
| --- | --- |
| **Phase** | A1 / L5 |
| **Preconditions** | Prior agy reply includes real `@grok` mention |
| **Steps** | Process message author=`agy`, mentions include `grok`. |
| **Expected** | Grok wake without new principal text (FR-A12, AC-A3). |
| **Pass** | handoff wake_spawned target=grok |
| **Type** | Contract / live |

### TP-A-24 — Bot handoff grok → agy

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Author=`grok`, body with `@agy` ask. |
| **Expected** | Agy backend wake (FR-A12). |
| **Pass** | target=agy |
| **Type** | Contract |

### TP-A-25 — Self-mention no re-wake

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Author=`agy`, mentions only `agy`. |
| **Expected** | Ignore (FR-A13). |
| **Pass** | no wake |
| **Type** | Unit |

### TP-A-26 — Author allowlist

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | User `other` posts `@agy hi` in collab room. |
| **Expected** | No wake (FR-A10, SR-A1). |
| **Pass** | |
| **Type** | Contract |

### TP-A-27 — Mentions[] preferred over bare word

| | |
| --- | --- |
| **Phase** | A0 / A1 |
| **Steps** | A) msg with structured mentions username=agy. B) body contains word “agy” without @. |
| **Expected** | A wakes; B does not (FR-A9, FR-A15). |
| **Pass** | Parser table |
| **Type** | Unit |

### TP-A-28 — Text fallback @Agy case-insensitive

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Body `@AGY test` without structured mentions (if fallback enabled). |
| **Expected** | Target agy (FR-A15). |
| **Pass** | |
| **Type** | Unit |

### TP-A-29 — Principal double-mention both bots

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Principal `@agy @grok both please`. |
| **Expected** | Per OD-A1 lean: **reject with help** (preferred) **or** sequential deterministic order; **not** parallel dual wakes (FR-A14). |
| **Pass** | Document chosen policy; assert no parallel |
| **Type** | Contract |

### TP-A-30 — Agy CLI helper invoked (not MCP)

| | |
| --- | --- |
| **Phase** | A1 / L2 |
| **Steps** | Principal `@agy` turn; instrument process/network. |
| **Expected** | Local helper/`agy` binary only; **zero** MCP `agy_*` (FR-A19, AC-A4). |
| **Pass** | Call log empty for MCP |
| **Type** | Contract |

### TP-A-31 — First agy turn uses start; second uses conversation UUID

| | |
| --- | --- |
| **Phase** | A1–A2 |
| **Preconditions** | Empty `agy.conversation_id` |
| **Steps** | Two successive `@agy` principal turns (or handoff cycle that re-enters agy). Capture helper mode. |
| **Expected** | First `start` (or new-project); after UUID capture, later `conversation` with same UUID (FR-A18, FR-A30). |
| **Pass** | state + argv |
| **Type** | Contract |

### TP-A-32 — Nested agy inside Grok collab wake forbidden

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Grok-target collab wake; inspect inject + tool policy / subprocess denylist. |
| **Expected** | Inject forbids nested `agy` CLI; no helper spawn from Grok collab turn (FR-A21, FR-A42). |
| **Pass** | inject contains forbid; no agy child under grok wake |
| **Type** | Contract |

### TP-A-33 — Agy invocations serialized

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Two rooms or two queued agy targets attempt concurrent helper. |
| **Expected** | Global (or host) serialize; no parallel `agy` (FR-A22). |
| **Pass** | Mutex / queue |
| **Type** | Contract |

### TP-A-34 — Per-room serial queue

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Mentions arrive while wake running in same room. |
| **Expected** | Queued; no concurrent dual backends for room (FR-A32). |
| **Pass** | Lock held |
| **Type** | Contract |

### TP-A-35 — Print timeout vs parent wake timeout

| | |
| --- | --- |
| **Phase** | A1 |
| **Preconditions** | `RC_AGY_PRINT_TIMEOUT=10m`, parent ≥ print + margin |
| **Steps** | Mock long print under limit; mock exceeding parent timeout. |
| **Expected** | Under limit: finalize OK; over parent: structured fail as agy, not hang forever (FR-A23, NFR-A1). |
| **Pass** | |
| **Type** | Contract |

### TP-A-36 — Same absolute cwd for agy resume

| | |
| --- | --- |
| **Phase** | A2 |
| **Steps** | Two agy wakes with profile cwd; inspect helper `--cwd` / process cwd. |
| **Expected** | Identical absolute cwd each turn (skill keying; §5.4). |
| **Pass** | |
| **Type** | Contract |

### TP-A-40 — Per-speaker one bubble

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Complete agy wake; count answer posts for that turn; inspect msgId chain. |
| **Expected** | One Thinking postMessage as agy + one chat.update final; no second answer post (FR-A24–A26, AC-A5). |
| **Pass** | post count / ledger |
| **Type** | Contract / live |

### TP-A-41 — Grok turn same one-bubble rule

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Grok-target collab wake completes. |
| **Expected** | One grok Thinking → update; reply file is final body (FR-A24–A27). |
| **Pass** | Align usability contracts |
| **Type** | Contract |

### TP-A-50 — Soft hop budget pause (not hard death)

| | |
| --- | --- |
| **Phase** | A2 |
| **Preconditions** | `hop_budget_epoch=5` (test value); auto_handoff on |
| **Steps** | Drive 5 bot↔bot hops; on 6th bot handoff attempt. |
| **Expected** | Pause auto-handoff; principal notified; sessions **retained**; not hard wipe (FR-A33–A34, AC-A8). |
| **Pass** | state.paused_reason=budget; UUID still set |
| **Type** | Contract |

### TP-A-51 — Tiny hard cap of 6 must not be product default

| | |
| --- | --- |
| **Phase** | A2 / review |
| **Steps** | Read default `RC_AGY_HOP_BUDGET_EPOCH` / profile. |
| **Expected** | Default high (spec lean **100**); test may lower for TP-A-50 only (FR-A34). |
| **Pass** | Config default assertion |
| **Type** | Unit / config |

### TP-A-52 — /pause freezes handoff

| | |
| --- | --- |
| **Phase** | A4 |
| **Steps** | Mid-collab `/pause` (or collab-native); bot posts `@peer`. |
| **Expected** | No auto wake from bot author while paused; sessions kept (FR-A36). |
| **Pass** | |
| **Type** | Contract |

### TP-A-53 — /resume restores handoff

| | |
| --- | --- |
| **Phase** | A4 |
| **Steps** | After pause, `/resume`; principal or bot handoff. |
| **Expected** | Auto-handoff works again if under budget (FR-A36). |
| **Pass** | |
| **Type** | Contract |

### TP-A-54 — /cancel kills in-flight either backend

| | |
| --- | --- |
| **Phase** | A4 |
| **Preconditions** | Long fake child for agy-target; then for grok-target |
| **Steps** | `/cancel` each. |
| **Expected** | Owned PID killed; bubble finalized fail/cancel; no foreign PID kill (FR-A37, SR cancel rules). |
| **Pass** | |
| **Type** | Contract |

### TP-A-55 — Sticky agy UUID after operator restart

| | |
| --- | --- |
| **Phase** | A2 / L3 |
| **Preconditions** | state has conversation_id U1 after first agy turn |
| **Steps** | Simulate process restart (reload state); principal `@agy` recall marker. |
| **Expected** | Helper mode conversation with U1; no silent start fresh (FR-A29–A30, AC-A9). |
| **Pass** | argv conversation=U1 |
| **Type** | Contract |

### TP-A-56 — Collab lifetime not single wall clock

| | |
| --- | --- |
| **Phase** | A2 |
| **Steps** | Multiple turns spanning > parent wake timeout wall time across hours (simulated clocks). |
| **Expected** | Each turn has own timeout; collab continues (FR-A31). |
| **Pass** | No global collab kill timer |
| **Type** | Contract / design |

### TP-A-57 — Checkpoint inject cadence

| | |
| --- | --- |
| **Phase** | A2 |
| **Preconditions** | `RC_AGY_CHECKPOINT_EVERY=3` |
| **Steps** | Complete 3 hops; inspect L3 inject. |
| **Expected** | Checkpoint nudge present when cadence hits (FR-A38). |
| **Pass** | inject substring |
| **Type** | Contract |

### TP-A-58 — Spin / no-progress auto-pause

| | |
| --- | --- |
| **Phase** | A5 |
| **Steps** | Feed near-duplicate peer-only tags / empty substance handoffs. |
| **Expected** | Auto-pause with reason spin (FR-A35). |
| **Pass** | paused_reason=spin |
| **Type** | Contract |

### TP-A-60 — L2 agent flag on agy wake

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Agy-target wake; capture helper/`agy` argv. |
| **Expected** | `--agent rc_collab` (or rules equivalent) present (FR-A40, AC-A11). |
| **Pass** | |
| **Type** | Contract |

### TP-A-61 — L3 inject fields present

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Capture prompt file for agy and grok collab wakes. |
| **Expected** | Includes mention body, room id, cwd, hop/epoch, auto_handoff, write scope, conversation id or NONE (FR-A41). |
| **Pass** | Field checklist |
| **Type** | Contract |

### TP-A-62 — Grok collab inject fragment

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Grok-target collab wake prompt. |
| **Expected** | Dual-account rules; no nested agy; @agy handoff guidance (FR-A42; profiles/grok-rc-collab.inject.md). |
| **Pass** | |
| **Type** | Contract |

### TP-A-63 — Default read-only write scope for agy

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Agy wake without elevation; inspect L2/L3. |
| **Expected** | Read-only default stated (FR-A43). |
| **Pass** | |
| **Type** | Contract |

### TP-A-64 — Profile content requires real peer mention to hand off

| | |
| --- | --- |
| **Phase** | docs / L2 |
| **Steps** | Read installed/draft `agy-rc-collab.agent.md`. |
| **Expected** | Handoff rules with `@grok` / yield without peer tag (FR-A44). |
| **Pass** | Substring in profiles (docs always; runtime when installed) |
| **Type** | Structural / contract |

### TP-A-70 — Agy CLI failure honest bubble

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Force helper exit nonzero / missing binary. |
| **Expected** | Finalize **as `agy`** with error; no fabricated success; Grok does not invent Gemini text (FR-A20, AC-A10). |
| **Pass** | body contains failure; username agy |
| **Type** | Contract |

### TP-A-71 — Kill mid-print

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Start long agy print; SIGKILL child; observe bubble. |
| **Expected** | Agy bubble fails closed; no eternally Thinking if finalize always runs (FR-A20, NFR-A1). |
| **Pass** | |
| **Type** | Contract |

### TP-A-80 — /status collab block (when Feature 3 present)

| | |
| --- | --- |
| **Phase** | A4 |
| **Steps** | `/status` in collab room mid-epoch. |
| **Expected** | Shows both pins, hop counters, pause, last errors (spec §5.3). |
| **Pass** | Field checklist |
| **Type** | Contract / live |

### TP-A-81 — Secrets never in bubble or inject dump

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Inspect final bodies + inject files for token patterns. |
| **Expected** | No secrets (SR-A2). |
| **Pass** | Grep fail if token-like |
| **Type** | Contract |

### TP-A-82 — Daily wake cap (if configured)

| | |
| --- | --- |
| **Phase** | A5 |
| **Preconditions** | `RC_AGY_DAILY_WAKE_CAP=3` |
| **Steps** | Fourth wake same day. |
| **Expected** | Reject/pause with reason (SR-A4). |
| **Pass** | |
| **Type** | Contract |

### TP-A-83 — Non-collab usability regression

| | |
| --- | --- |
| **Phase** | A1 / L6 |
| **Steps** | DM principal “hello”; run usability contracts. |
| **Expected** | Unchanged Thinking→update path (NFR-A5, AC-A12). |
| **Pass** | Existing suite green |
| **Type** | Regression |

### TP-A-84 — Operator log lines present

| | |
| --- | --- |
| **Phase** | A1 |
| **Steps** | Successful handoff cycle. |
| **Expected** | Logs include mention, wake target, hop, uuid capture (NFR-A4, §6.4). |
| **Pass** | Substrings |
| **Type** | Contract |

### TP-A-lab-H01 — Sticky three-turn agy recall (lab)

| | |
| --- | --- |
| **Phase** | A0–A2 / L4 |
| **Steps** | T1 principal `@agy` set marker `RC_AGY_MARK_*`. T2 substantive objection. T3 ask for marker only. |
| **Expected** | T3 returns marker (AC-A6; skill H-01 class) **or** repo checkpoint contains it. |
| **Pass** | Exact marker in agy final body or file |
| **Type** | Lab |

### TP-A-lab-mention-physics — REST creates usable mentions

| | |
| --- | --- |
| **Phase** | A0 / L4 |
| **Steps** | As `agy`, `chat.postMessage` body containing `@grok` in collab room; fetch message. |
| **Expected** | `mentions[]` includes grok **or** documented fallback parse works for dispatcher (FR-A16). |
| **Pass** | Lab record in implement evidence |
| **Type** | Lab |

### TP-A-lab-multi-hop-50 — Long-horizon depth smoke (soak)

| | |
| --- | --- |
| **Phase** | A2 / L5 soak |
| **Steps** | Automated or semi-auto ≥50 bot↔bot hops or multi-hour epoch with high budget. |
| **Expected** | Sessions sticky; soft pause only on budget/spin; product not hard-capped at 6 (AC-A7). |
| **Pass** | hop_count ≥ 50 or duration gate |
| **Type** | Soak (implement-time) |

---

## 5. Edge cases and negative / failure cases

| ID | Edge / failure | Expected |
| --- | --- | --- |
| **E-A-author-1** | Non-allowlisted user @agy | No wake (SR-A1) |
| **E-A-author-2** | grok user outside collab room @agy in DM | No collab arm (FR-A2) |
| **E-A-mention-1** | Plain word “grok” without @ | No wake |
| **E-A-mention-2** | Fullwidth `＠agy` | Document: reject or normalize |
| **E-A-mention-3** | Zero-width chars inside @agy | Reject / no wake |
| **E-A-mention-4** | Mentions array for missing user | No crash; no wake |
| **E-A-mention-5** | Bot posts `@grok` as plain text that does **not** link | Lab: may fail handoff — FR-A16 gate |
| **E-A-fake-voice** | Attempt to post agy body as grok | Forbidden (FR-A8) |
| **E-A-mcp** | MCP server installed; collab still runs | Still zero MCP agy_* (FR-A19, SR-A5) |
| **E-A-timeout** | Parent timeout &lt; print timeout misconfig | Fail visible; document config validation |
| **E-A-double-post** | Model calls chat.postMessage answer | Guard / inject forbid; finalize only via operator |
| **E-A-budget-1** | Budget 0 | Immediately paused or reject handoff |
| **E-A-budget-2** | Budget hit mid-Thinking | Finish current turn; pause after |
| **E-A-spin** | Alternating empty `@grok` / `@agy` | Auto-pause |
| **E-A-uuid-miss** | Start succeeds but UUID not parsed | Next turn must not silently invent; visible error or forced start with log |
| **E-A-uuid-invalid** | Corrupt UUID in state | Fail closed or start new with principal-visible notice |
| **E-A-cwd-drift** | Helper cwd ≠ profile cwd | Reject or correct; no wrong-thread resume |
| **E-A-parallel-rooms** | Room A and B both collab | Isolation of sessions/hops; agy still serialized |
| **E-A-room-lock** | Second mention while locked | Queue; no drop without log |
| **E-A-secret** | Inject accidentally includes env token | SR-A2 fail test |
| **E-A-restart-corrupt-state** | Corrupt collab sub-object | Defaults; no crash; log |
| **E-A-pause-principal** | Principal @agy while paused | Policy: allow principal re-open (lean yes) — document |
| **E-A-cancel-none** | /cancel with no child | Friendly error |
| **E-A-nested-grok** | Grok shell tries agy despite inject | Tool deny / no spawn |
| **E-A-daily-cap** | Cap exceeded | Pause with reason |
| **E-A-membership** | agy leaves channel mid-epoch | Fail closed next agy post |
| **E-A-flag-race** | RC_AGY_COLLAB flipped mid-wake | Current wake finishes; next respects flag |

---

## 6. Pass / fail and exit criteria

| Phase | Exit when |
| --- | --- |
| **A0 Lab** | TP-A-lab-mention-physics; manual post-as-agy optional; document mention reality on RC 8.6 |
| **A1 MVP** | TP-A-00–02, 10–11, 20–29, 30–36, 40–41, 60–64, 70–71, 83–84 + critical edges E-A-author*, E-A-mcp, E-A-double-post |
| **A2 Durability** | TP-A-50–58, 55, lab-H01; soft budget pause retains sessions |
| **A3 Trust UX** | Streaming/meta if NF-SPEC-02 wired; fail honesty TP-A-70–71 |
| **A4 Control** | TP-A-52–54, 80 |
| **A5 Harden** | TP-A-58, 82, soak TP-A-lab-multi-hop-50 optional |

**Hard fails (any phase):**

- MCP `agy_*` used for Gemini backend  
- Non-allowlisted author wakes bot  
- Fake dual voice under single username  
- Untagged principal note wakes collab backends  
- Second answer bubble for same speaker turn  
- Silent UUID reset across restart when state valid  
- Product default hard hop cap ≤ 6 as sole safety  

**Evidence:** argv/helper captures, state.json snapshots, RC history usernames, operator log lines, lab notes for mention physics.

---

## 7. Mapping to acceptance criteria (NF-SPEC-04 §7.2)

| AC | Primary cases |
| --- | --- |
| AC-A1 Dual avatars | TP-A-10 |
| AC-A2 Tag-to-talk | TP-A-20 |
| AC-A3 Handoff | TP-A-23, TP-A-24 |
| AC-A4 CLI-only | TP-A-30, E-A-mcp |
| AC-A5 One bubble | TP-A-40, TP-A-41 |
| AC-A6 Sticky | TP-A-55, TP-A-lab-H01 |
| AC-A7 Long-horizon | TP-A-51, TP-A-lab-multi-hop-50 |
| AC-A8 Soft budget pause | TP-A-50 |
| AC-A9 Restart resume | TP-A-55 |
| AC-A10 Failure honesty | TP-A-70, TP-A-71 |
| AC-A11 Profiles | TP-A-60–64 |
| AC-A12 Non-collab regression | TP-A-83 |

---

## 8. Open / blocked (test design)

| Item | Note |
| --- | --- |
| OD-A1 double-mention | Cases assert no parallel; exact reject vs sequential is lean reject |
| OD-A2 C3-A vs C3-B | Topology-agnostic cases (behavior-level) |
| Mention physics on RC 8.6 | A0 lab must close before handoff reliability claims |
| Feature 3 not shipped | TP-A-52–54/80 may use collab-native command aliases temporarily |
| Soak multi-hop-50 | Implement-time; not a docs-package gate |

---

## 9. References

- **NF-SPEC-04** [`./spec.md`](./spec.md) — FR-A*, NFR-A*, SR-A*, AC-A*, phases A0–A5  
- **Research** [`./research.md`](./research.md) — C3 dual-peer, long-horizon, anti-runaway  
- **Profiles** [`./profiles/`](./profiles/) — L2 social contract drafts  
- Live: `rc_operator_agent.py` principal-only filter; `wake_lib.py` locks/sessions; `agy-cli-collab` helper; `NO_DUPLICATE_POSTS.md`  
- Related specs: NF-SPEC-02 streaming per bubble; NF-SPEC-03 control plane  

---

*End of NF-TP-04. Test-planning documentation only — no runtime collab implementation in this package.*
