# Feature 4 — Antigravity collab facilitated through a Rocket.Chat channel

**Status:** Research only (no runtime implementation in this document set)  
**Normative spec:** [`spec.md`](./spec.md) (**NF-SPEC-04**) · **Test plan:** [`test-plan.md`](./test-plan.md) (**NF-TP-04**)  
**Date:** 2026-07-10  
**Updated:** 2026-07-10 — preferred UX = dual RC accounts + @mention turns; **core value = long-horizon multi-turn inter-agent collab**  
**Working name:** RC-agy collab channel (example room: `#grok-agy-collab`)  
**Stack baseline:** Rocket.Chat **8.6** + operator `rc_operator_agent.py` (principal-only wake; Thinking… → reply file → `chat.update`); Grok CLI headless wakes; global skill `agy-cli-collab` → local `agy` print mode  
**Hard rules preserved:** [`NO_DUPLICATE_POSTS.md`](file:///Users/velocityworks/.grok/agency/ops/rocketchat/NO_DUPLICATE_POSTS.md) **per speaker turn**; skill CLI-only for Gemini runtime (never MCP `agy_*`); collab rooms use **mention-target wake**, not principal-only for bot↔bot turns  

**Preferred product model (principal direction):** Create Rocket.Chat user **`agy`**. In the collab channel, participants interact **the same way two humans would** — `@agy` on a message wakes Antigravity/Gemini; `agy` replies and tags `@grok`; `@grok` wakes Grok; and so on. The principal may also `@`-tag either bot to inject guidance.

**Core value proposition:** Not a one-shot “ask Gemini” button. The channel exists to **facilitate long-horizon inter-agent collaborations** — potentially **many, many turns** over hours or days — with Rocket.Chat as the durable, phone-visible floor and the principal as intermittent supervisor rather than turn-by-turn babysitter.

---

## 1. Problem framing (against the live stack)

### 1.1 What works today (two separate systems)

| System | What it does well | Where it lives |
| --- | --- | --- |
| **Rocket.Chat ↔ Grok** | Phone-reachable principal messaging; per-room Grok session resume; project-aware `--cwd`; one answer bubble | `~/.grok/agency/ops/rocketchat/wake/` |
| **Grok ↔ Gemini via agy** | Sticky multi-turn Lead-Scientist collaboration; UUID pin / cwd-scoped continue; validated helper + smoke suite | `~/.grok/skills/agy-cli-collab/` |

They are **not wired as a product surface**. A principal on mobile can talk to Grok in RC, and a principal (or Grok in a desktop session) can invoke `/agy-cli-collab`, but there is no dedicated **room contract** that:

1. Declares “this channel is a Grok↔agy collaboration floor,”  
2. Keeps **agy conversation UUID** sticky per RC room across wakes,  
3. Surfaces **each agent’s contribution** under its own identity for many turns,  
4. Aligns **timeouts, approval, serialization, and durability** so collab can run for **dozens–hundreds of turns**,  
5. Lets the principal **supervise intermittently** (redirect, pause, budget, summarize) without sitting in every hop.

### 1.1b Why long-horizon is the point (not a stretch goal)

Short collabs (3–5 turns) can already be faked by a human pasting between tools or by a single nested `agy` call. That is **not** the product bet.

| Horizon | What fails without this channel | What the channel must provide |
| --- | --- | --- |
| **Minutes (few turns)** | Mild inconvenience | @mention handoff + dual avatars |
| **Hours (tens of turns)** | Context loss; no audit trail; Mac session dies | Sticky sessions, room history as ledger, per-turn reliability |
| **Days (many, many turns)** | Research programs drift; no resume after sleep/restart; principal cannot “check in” | Durable pins, checkpoints to repo, budgets that allow long runs without equating “long” with “runaway” |

**Implication:** Design for **sustained dialogue**, not demo ping-pong. Safety controls must stop **spin / no-progress / cost runaway**, not artificially cap productive depth at ~6 hops.

### 1.2 Desired experience (preferred product sketch)

Example channel: **`#grok-agy-collab`** (private; members: `principal`, `grok`, **`agy`**).

**Social model = two humans in a room.** Each bot has its own Rocket.Chat identity. Turns are addressed with **@mentions**, not a single mediated monologue.

#### Canonical turn loop

```
principal:  @agy Strongest objection to chamber-reset as an inference gate?
   → wakes **agy** (Gemini via local agy CLI)
agy:        @grok Objection is … Falsifiers: … Your counter?
   → wakes **grok** (Grok CLI)
grok:       @agy Counter is … Propose experiment E1 …
   → wakes **agy** again
…
principal:  @grok Summarize agreement and open questions.
   → wakes **grok** only (steering)
```

| Actor | RC username | Wakes when | Backend process | Posts as |
| --- | --- | --- | --- | --- |
| Human | `principal` | n/a (initiates) | — | self |
| Grok | `grok` | Message **mentions** `grok` (and room is collab-enabled / watched) | Grok CLI (existing wake path) | `grok` |
| Antigravity / Gemini | **`agy`** (new account) | Message **mentions** `agy` | Local **`agy`** CLI print mode (skill-compatible) | **`agy`** |

#### Rules of the floor (product)

1. **Tag to talk** — a bot does not reply to every channel message; it replies when **@mentioned** (or when principal uses an explicit command that implies a target).  
2. **Bots tag each other** — when continuing the collab, the speaker **@-tags the other bot** so the next wake is automatic and human-visible.  
3. **Principal is intermittent supervisor** — can `@agy`, `@grok`, pause, raise budget, force checkpoint, or stop; **need not** re-prompt every hop for long runs.  
4. **Each speaker owns their own bubble** — `agy` posts as `agy`; `grok` posts as `grok` (Thinking… → update **per wake**, per identity).  
5. **No silent nested Gemini inside Grok** as the primary UX — Gemini’s words appear under the **`agy` avatar**.  
6. Sticky backends remain: per-room Grok session pin + per-room agy conversation UUID across **many** wakes (hours/days).  
7. Long waits surface progress (Feature 2) on **that speaker’s** Thinking bubble.  
8. **Long-horizon first** — room history + repo checkpoints are the audit trail of a research collaboration, not a disposable chat.

### 1.3 Why a channel (not only DM) — especially for long horizon

| Factor | Channel advantage for many-turn collab |
| --- | --- |
| **Durable transcript** | RC channel is a scrollable multi-day ledger of who said what (human-readable, phone-reachable) |
| **Cwd policy** | Maps to a **repo root** where durable artifacts land between turns |
| **Session keys** | Per-room Grok session + per-room agy UUID survive operator restarts if state is persisted |
| **Isolation** | Long dual-agent noise stays out of DM agency spine |
| **Social model** | Principal can drop in mid-thread days later; optional second human later |
| **Precedence** | `#Prime-Gap-Structure` already shows program-scoped channels |

DM remains valid for *ad-hoc* short collab; the **product** surface is a named long-horizon collab channel (or per-program rooms with `mode=agy-collab`).

### 1.4 Gap statement (updated for dual-account @mention model)

| Gap | Impact |
| --- | --- |
| **No RC user `agy`** | Cannot post or authenticate as second peer |
| **Wake filter is principal-only** | `rc_operator_agent.py` ignores non-`principal` authors (`user != PRINCIPAL` → drop). Bot↔bot `@grok` / `@agy` tags **never wake** today |
| **Single operator identity** | Operator logs in and posts only as `grok`; no second token path for `agy` Thinking… / `chat.update` |
| **No mention-target routing** | Even if both bots existed, there is no “if mentions include X, run backend Y” dispatcher |
| No durable **agy UUID** in operator state | Sticky Gemini threads die across wakes — fatal for multi-day collab |
| Channel **restricted** approval / timeouts | Full `agy` print runs need room profile (timeout ≥ print-timeout; elevated tools) |
| **Runaway vs long-horizon confusion** | Naive “max 6 hops” kills the product; unbounded spin burns Mac/API |
| No progress / checkpoint model | After tens of turns, channel alone is hard to re-enter; repo must gain durable state |
| Session/context decay | Grok `--resume` and agy UUID may hit model context limits long before “many turns” finish |
| Operator / Mac lifecycle | launchd restart, sleep, wake timeout — long collabs need resume-safe state |
| Serialization | Two backends + skill “no parallel agy” need a room-level turn lock |
| Failure honesty | `agy` must post failure **as `agy`**, not leave Thinking… forever or have Grok invent Gemini text |

---

## 2. Current baseline / interfaces (precise)

### 2.1 Rocket.Chat operator message path

From [docs/message-flow.md](../../docs/message-flow.md) and live `rc_operator_agent.py`:

```
principal msg (watched room)
  → WebSocket event
  → filter (principal-only, not self, not handled)
  → chat.postMessage "Thinking..."
  → resolve cwd + session pin + approval mode
  → spawn Grok CLI (reply_prompt.txt + inject)
  → reply file
  → chat.update(thinking_msg_id, final_text only)
  → optional rc_post_media.py
```

**Implications for collab:**

- Gemini never talks to Rocket.Chat directly today.  
- All collab mediation must either happen **inside the Grok wake** (skill/subprocess) or be **orchestrated by the operator** (new code path).  
- Final user-visible text is whatever lands in the **reply file** (unless media helper posts attachments).

### 2.2 Accounts and trust

| RC user | Role today |
| --- | --- |
| `principal` | Only username that triggers wakes |
| `grok` | Bot presence; Thinking…; updates; media; call join |

There is **no** `agy` Rocket.Chat user today. The preferred product model **requires** creating one (bot or user with API access), storing credentials alongside `rocketchat.env` (e.g. `RC_AGY_USER` / token pair — parallel to IMP-20 bot-token work), and teaching the operator (or a sibling agent) to:

1. Authenticate **as `agy`** for posts attributed to Antigravity.  
2. Subscribe to collab rooms while able to **see** messages from `principal` **and** `grok` (and optionally other allowlisted humans).  
3. Wake the **agy backend** only when the message **targets** `agy` via mention (or explicit command).

**Live code anchor:** `handle_principal_message` / WS handler in `rc_operator_agent.py` drops traffic unless `(msg.u.username) == "principal"`. Dual-peer collab is therefore **not a prompt change** — it is a **filter + identity + dispatcher** change.

### 2.3 Project cwd and channel map

| Room type | Default cwd |
| --- | --- |
| DM | `~/.grok/agency` |
| Channel / group | `~/IdeaProjects/<slug>` (auto-create **off** by default — IMP-19) |
| Override | `wake/channel_projects.json` |

Live example:

```json
"Prime-Gap-Structure": "prime-gap-structure"
```

For `#grok-agy-collab`, implementers would need either:

- explicit map entry → e.g. `prime-gap-structure` or a dedicated workspace, and  
- operator invite + membership refresh (≤ ~60s `RC_ROOM_REFRESH_S`).

**agy skill constraint:** Session resume is keyed by shell **`cwd`**, not `--add-dir`. Collab wakes must `cd` / `--cwd` consistently to the same absolute repo root every turn.

### 2.4 Per-room state already present (extend, don’t reinvent)

From IMP-14 / `wake_lib.py` / `state.json` v2 patterns:

| State | Storage today | Collab need |
| --- | --- | --- |
| Grok session id | `grok_sessions[room_id]` | Keep (Grok sticky chat) |
| Grok cwd pin | `grok_cwds` / map | Keep; must match agy cwd |
| Approval mode | env + room type | Need **collab exception** or admin-once |
| Wake locks | per-room under `wake.lock.d/rooms/` | Hold for full Grok+agy duration |
| **agy conversation UUID** | **missing** | **Add** `agy_conversations[room_id]` (or collab profile sub-object) |
| **agy project name / log path** | **missing** | Optional for ops forensics |

### 2.5 Timeouts and concurrency (hard numbers)

| Knob | Typical default | Collab implication |
| --- | --- | --- |
| `RC_WAKE_TIMEOUT_S` | **600** (10 min) | Must cover **entire** Grok turn including nested agy |
| `agy --print-timeout` | skill helper **10m**; CLI default **5m** | Nested call alone can exhaust parent wake |
| Wake lock stale | timeout + 300s | Must stay consistent if timeout raised |
| `RC_WAKE_MAX_TURNS` | **12** | Collab tool loops burn turns; may need room profile bump |
| `RC_WAKE_MAX_CONCURRENT` | **1** | Global serialize helps agy “no parallel” rule; multi-room collab needs explicit queue |
| Room refresh | 60s | New channel not watched until join + refresh |

**Minimum viable timeout math (conceptual):**

```
wake_timeout ≥ agy_print_timeout + grok_prepost_overhead + margin
e.g.  agy 10m + Grok brief/integrate 3–5m + margin → RC_WAKE_TIMEOUT_S ≥ 900–1200 for collab rooms
```

Raising global timeout is nuclear (locks, mobile “stuck” feels). Prefer **per-room profile** timeouts (ties to Feature 3 control plane + IMP-02 lock TTL discipline).

### 2.6 Approval / permission reality (IMP-01)

| Mode | Grok CLI flags | Channels (default policy) |
| --- | --- | --- |
| restricted | `--permission-mode auto` | **Default** when admin is DMs-only |
| admin | `--always-approve` | Opt-in; usually **not** channels |

`agy-cli-collab` **requires** running the local `agy` binary with `--dangerously-skip-permissions` for headless tool use. Under restricted wakes, Grok may be **unable to spawn** that path reliably — or may spawn it only if `auto` allows the specific shell pattern.

**Research conclusion:** Collab rooms need an explicit **permission strategy** (see §3 approaches), not hope that restricted mode allows nested agent CLIs.

### 2.7 agy-cli-collab skill contract (must remain law)

Source: `~/.grok/skills/agy-cli-collab/SKILL.md` + smoke results 2026-07-06.

| Rule | Meaning for RC |
| --- | --- |
| CLI only | Operator must not “help” by calling MCP `agy_*` |
| Serialize agy | Never parallel subprocesses; queue multi-room collab |
| Modes | `start` / `conversation` / `continue` / `clean` |
| Capture UUID | From log line `Created conversation <uuid>` into durable state |
| Resume preferred | `--conversation <uuid>` over bare `--continue` |
| cwd keying | Same absolute cwd every turn |
| Prompt style | Focused task brief; evidence + question; default **read-only** for Gemini |
| Output handling | Integrate; preserve disagreement; don’t claim success on CLI fail |
| Validated | helper + sticky 3-turn recall on `prime-gap-structure` |

Helper path (preferred over ad-hoc argv):

```text
python ~/.grok/skills/agy-cli-collab/scripts/agy_cli.py
  --cwd <repo>
  --mode start|conversation|continue|clean
  --conversation <uuid>   # conversation mode
  --log-file …
  --state-file …
  --prompt-file …
  --print-timeout 10m
```

### 2.8 Reply prompt / inject (extension surface)

Every wake injects `reply_prompt.txt` + context block (`Room id`, `Project cwd`, `Reply file`, `Approval mode`, Thinking message id, principal text, …).

There is **no** today:

- `Collab mode: on`  
- `Agy conversation id: …`  
- `Agy last status: …`  
- Room-specific prompt overlay for collab channels  

**Cleanest low-code lever:** room profile → extra inject lines + optional alternate prompt fragment (`reply_prompt_agy_collab.txt`).

### 2.9 Adjacent patterns worth reusing

| Pattern | Relevance |
| --- | --- |
| PGS hourly notify | One-way bot post without Thinking…; shows second posting path exists — **not** for collab answers |
| Feature 2 streaming | Long agy waits need phase updates (`Working… · agy running`) |
| Feature 3 slash commands | Natural home for `/agy …` steering |
| Media ledger | Optional attach of Gemini long form as file if chat bubble too short |
| Call bot spawn | Precedent for “operator spawns specialized subprocess for room event” — collab is still text-wake-centric first |

---

## 3. Candidate technical approaches

Approaches are ordered from thinnest to thickest. Names use **C*** (collab).

### Approach C0 — Convention only (no operator code)

**Mechanism:**

1. Create private channel `#grok-agy-collab`.  
2. Invite `grok`; map cwd in `channel_projects.json`.  
3. Put collab instructions in project `AGENTS.md` / channel description / principal habit (“use agy-cli-collab”).  
4. Rely on Grok discovering the skill and calling `agy`.

| Pros | Cons |
| --- | --- |
| Zero operator engineering | Unreliable under restricted approval |
| Fast experiment | No durable UUID across wakes (unless Grok invents files) |
| | Timeout mismatch kills long Gemini work |
| | No phone steering; no honest failure UX contract |
| | Skill Collab Mode not session-sticky in RC |

**Verdict:** Useful as a **manual lab probe**, not a product. Document as preflight only.

---

### Approach C1 — Room collab profile + skill-inside-wake (recommended MVP)

**Mechanism:**

1. **Room profile** (new small config or extension of `channel_projects.json`):

   ```json
   {
     "grok-agy-collab": {
       "cwd": "prime-gap-structure",
       "mode": "agy-collab",
       "wake_timeout_s": 1200,
       "max_turns": 24,
       "approval": "admin",
       "agy_print_timeout": "10m",
       "agy_default_cwd": "/Users/…/IdeaProjects/prime-gap-structure"
     }
   }
   ```

2. Operator, when `mode=agy-collab` for room:

   - Inject collab block: Collab Mode on; skill path; last `agy_conversation_id`; cwd absolute; read-only default for Gemini; output shape.  
   - Apply profile timeout / turns / approval **for this room only**.  
   - Optionally pass env `RC_AGY_STATE_DIR` / state file path under log dir.  

3. **Grok** (inside wake) owns science + integration:

   - Calls helper `agy_cli.py` per skill.  
   - On start: write UUID to reply-side state file **and/or** machine-readable trailer the operator parses into `state.json`.  
   - Writes integrated answer to reply file.

4. **UUID durability (critical design choice):**

   | Option | How | Prefer |
   | --- | --- | --- |
   | C1a Model-written state file | Grok writes `/tmp` or log-dir UUID; next inject reads it | Fragile if model skips |
   | C1b Operator-parsed trailer | Reply file ends with `<!-- agy-conversation: uuid -->`; operator strips before post, stores in `state.json` | **Better** |
   | C1c Operator runs agy | See C3 | Thicker |

5. **UX in bubble (single post, multi-section):**

   ```markdown
   ## Synthesis
   …

   ## Material disagreement
   …

   ## Gemini contribution (compact)
   …
   ```

   Still **one** `chat.update` — satisfies NO_DUPLICATE_POSTS for the answer.

| Pros | Cons |
| --- | --- |
| Reuses entire operator + skill | Still depends on Grok correctly invoking skill |
| Minimal new process surface | Trailer / state convention needs tests |
| Per-room timeout/approval fixes hard blockers | Long runs still need Feature 2 visibility |
| Aligns with skill “integrate, don’t dump” | admin-on-channel increases blast radius |

**Verdict:** **Recommended MVP** for “facilitated through a channel.”

---

### Approach C2 — Operator-orchestrated dual call (Grok plan → agy → Grok integrate)

**Mechanism:**

Operator detects collab room (or `/agy` command) and runs a **fixed pipeline**:

1. Wake Grok with `mode=plan-only` (or short turns): produce `agy-task.md` only.  
2. Operator runs `agy_cli.py` **itself** (CLI-only, skill-compatible argv).  
3. Capture Gemini stdout + UUID → state.  
4. Second Grok wake (or same process chain): integrate Gemini output → reply file.  
5. Single Thinking… bubble held across the chain (or phase updates).

| Pros | Cons |
| --- | --- |
| UUID capture reliable (operator-owned) | Two Grok invocations or complex multi-phase wake |
| agy serialization enforced in one process | Operator becomes “collab bus” — more code |
| Failures attributed without model honesty | Risk of double Thinking if naively implemented |
| Matches skill failure rule in deterministic code | Latency = sum of stages |

**Verdict:** **Recommended hardening** after C1 if UUID / invocation reliability is weak. Compatible with Feature 2 phase labels (`Planning…` / `Consulting Gemini…` / `Integrating…`).

---

### Approach C3 — Dual Rocket.Chat identities + @mention turns (**preferred product**)

**Mechanism (matches principal direction):**

1. **Create RC account `agy`** (bot user preferred) with password or personal access token; store in secrets (do not commit).  
2. **Membership:** private channel `#grok-agy-collab` includes `principal`, `grok`, `agy`.  
3. **Mention-target wake dispatcher** (collab rooms only):

   | Incoming message author | Mentions include | Action |
   | --- | --- | --- |
   | `principal` | `agy` | Wake **agy backend**; post Thinking… **as `agy`** |
   | `principal` | `grok` | Wake **Grok CLI**; post Thinking… **as `grok`** (today’s path) |
   | `principal` | both | Policy choice: sequential both, or reject with “mention one target” |
   | `grok` | `agy` | Wake **agy backend** (bot→bot handoff) |
   | `agy` | `grok` | Wake **Grok CLI** (bot→bot handoff) |
   | either bot | self only | Ignore or treat as no-op (no self-wake loops) |
   | anyone | neither | **No wake** (browsing / notes / principal monologue OK) |

4. **Backend mapping:**

   - Target `grok` → existing `build_wake_argv` + Grok CLI + `grok` reply file → `chat.update` as `grok`.  
   - Target `agy` → operator (or collab agent) runs `agy_cli.py` with room’s pinned UUID / cwd → reply file → `chat.update` **as `agy`**.  
   - Optional: Grok’s prompt forbids nesting `agy` CLI when dual-account mode is on (avoid double Gemini).  

5. **Human-like tagging convention (prompt/inject):**

   - When `agy` intends to continue with Grok, final message body **must include** a real RC mention of `grok` (so the operator’s mention parser fires).  
   - When `grok` intends to continue with `agy`, body **must mention** `agy`.  
   - When either is done or waiting on the human, **do not** mention the other bot (stop condition).  
   - Principal can always re-open with `@agy` / `@grok`.

6. **NO_DUPLICATE_POSTS reinterpreted:** one answer bubble **per speaker per turn**, not one bubble for the whole room forever. `agy` must not also finalize via `grok`’s bubble; `grok` must not `chat.postMessage` a second copy of `agy`’s text.

| Pros | Cons |
| --- | --- |
| Matches “two humans” mental model | Largest change vs today’s principal-only filter |
| Visible, attributable turns on phone | Second account + dual auth headers |
| Natural interrupt / redirect by principal | Ping-pong control required |
| Gemini text is first-class (not nested dump) | Mention parsing must be robust (RC `mentions` array vs `@agy` text) |
| Reuses Thinking… UX per identity | Two session stores (Grok + agy UUID) |
| Aligns with how people already use RC | Collab rooms need different policy than DMs |

**Verdict:** **Preferred product architecture.** C1/C2 remain valid **implementation internals** for *how* the `agy` backend is invoked, but **presentation and wake routing** should be C3 @mention peers — not a single Grok-mediated monologue.

#### C3 implementation shapes (still research)

| Shape | Description | Notes |
| --- | --- | --- |
| **C3-A Dual process** | `rc_operator_agent` (as `grok`) + `rc_agy_agent` (as `agy`) | Clean identity isolation; two launchd KeepAlives; share room profile + mutex |
| **C3-B Single multi-identity operator** | One process holds both tokens; dispatcher chooses poster + backend | Fewer daemons; careful auth mixing; one WS or two logins |
| **C3-C Grok-only poster with fake attribution** | One account pretends dual voice | **Reject** — breaks human-like avatars and trust |

Recommend designing for **C3-A or C3-B**; reject C3-C.

#### Mention detection (RC 8.6)

Prefer structured fields when present:

- Message payload often includes `mentions: [{ _id, username, … }]` for true `@user` mentions.  
- Fallback: parse `@agy` / `@grok` in `msg` text (normalize case; word boundary).  
- Do **not** treat plain word “agy” without `@` as a wake (too noisy).  
- Bot replies that need to wake the peer must use a **real mention** (RC autocomplete / known user), not plain text that looks like a mention but is not linked — verify on 8.6 whether REST `chat.postMessage` with `@grok` creates a mention object automatically when the user exists in-room.

#### Anti-runaway (mandatory) — distinct from “allow many turns”

Long-horizon collab **requires** large hop counts. Safety must target **pathology**, not depth.

| Control | Purpose | Sketch for long-horizon |
| --- | --- | --- |
| **Soft hop budget** | Pause for principal, not kill the project | High default (e.g. 50–200 bot↔bot hops / “epoch”); on hit, bots **stop tagging peer** and post `@principal` checkpoint ask |
| **Hard daily / wall-clock budget** | Cost and Mac heat | e.g. max wakes/day or max active hours; configurable |
| **No-progress detector** | Stop spin | Near-duplicate messages, empty substance, repeated `@peer` only → auto-pause |
| **Cooldown** | Dampen thrash | Min seconds between bot-triggered wakes (small; not multi-minute if turns are sequential) |
| **Explicit stop** | Clean end of a phase | No peer mention, `PASS` / `DONE` / `/stop`, or principal `/pause` |
| **Principal cancel** | Emergency | `/cancel` kills in-flight backend; `/pause` freezes auto-handoff without clearing sessions |
| **No self-wake** | Trivial loop | `@agy` by `agy` ignored |
| **Checkpoint cadence** | Re-enterability | Every N turns or on budget pause: one agent writes durable notes to **repo** (not only RC) |

**Wrong design:** global max hops = 6 (kills the value prop).  
**Right design:** long runway + **epoch pauses** + **spin detection** + **durable checkpoints**.

---

### 3.x Long-horizon durability (design requirements)

These are first-class requirements if “many, many turns” is the goal:

| Requirement | Why | Design note |
| --- | --- | --- |
| **D1 Resume after process death** | Operator/launchd restarts mid-collab | `state.json` holds both session IDs; next mention continues, does not “start fresh” |
| **D2 Resume after Mac sleep** | Phone-supervised research overnight | Wakes are discrete jobs; no in-memory-only collab state |
| **D3 Channel as ledger, repo as truth** | Scrollback ≠ proof/code | Inject periodically: “write joint note to `research/…`” under write scope rules |
| **D4 Context window strategy** | Sessions bloat over tens of turns | Options: (a) rely on CLI session compression; (b) inject rolling summary from repo; (c) `/compact` command; (d) epoch = new Grok session but **same** agy UUID or vice versa — product choice |
| **D5 Turn queue** | Mentions arrive while a wake runs | Per-room serial queue (already lock-shaped); never parallel agy |
| **D6 Idempotent processing** | WS reconnect / catch-up | Message ids already mark processed; bot-authored messages must enter same ledger |
| **D7 Unattended policy** | Principal not watching every hop | Default: allow auto-handoff until soft budget; notify principal (optional DM or channel system line) on pause/fail |
| **D8 Observability over days** | “Is collab still alive?” | `/status`: last hop time, hop count this epoch, both session ids, last error, budget remaining |
| **D9 Timeouts are per-turn, not per-collab** | Collab lasts days; each wake is minutes | Do **not** use one global wall clock for the whole collab — only per backend invocation |
| **D10 Cost / rate awareness** | Many turns ⇒ many CLI bills | Soft budgets + principal-visible counters |

---

### Approach C4 — Dedicated collab bridge process (launchd)

**Mechanism:**

Separate KeepAlive process (peer of operator / call bot):

- Subscribes to one or more collab rooms.  
- Owns agy lifecycle, UUID store, rate limits.  
- Talks to RC via REST; may still spawn Grok CLI for integration.

| Pros | Cons |
| --- | --- |
| Isolation from general DM load | Second daemon to ops/health |
| Can hold multi-hour sessions | Duplicates room membership / auth concerns |
| Cleaner serialization | Drift from single operator mental model |

**Verdict:** Long-horizon (multi-hour/day) is **in scope for the product**; start by extending the operator with durable state (C3 + D1–D10). Split out a dedicated bridge daemon only if multi-room / isolation pressure demands it.

---

### Approach C5 — Rocket.Chat Apps-Engine / slash UX only

Register formal slash commands and UI kit cards for Approve Gemini write-scope.

| Pros | Cons |
| --- | --- |
| Native autocomplete | Deploy overhead on private RC 8.6 |
| Pretty approval cards | Does not solve nested CLI/timeout by itself |

**Verdict:** Optional polish **after** operator-native `/agy` parser (Feature 3 style). Not sufficient alone.

---

### Approach comparison (summary)

| Approach | Reliability | Engineering cost | Phone UX | Skill fidelity | Recommend |
| --- | --- | --- | --- | --- | --- |
| C0 Convention | Low | Near zero | Weak | Accidental | Lab only |
| C1 Profile + skill-in-wake | Medium–high | Low–medium | Mediated only | High | Backend helper for **agy target** |
| C2 Operator orchestrates agy | High | Medium | Mediated / phased | High | **agy backend runner** under C3 |
| **C3 Dual bots + @mentions** | High if loop-safe | Medium–high | **Excellent (human-like)** | High if CLI-backed | **Preferred product** |
| C4 Bridge daemon | High | High | Good | High | If multi-room scale |
| C5 Apps-Engine | n/a alone | Medium | Excellent cmds | n/a | Polish on top of C3 |

---

## 4. Integration points (operator / skill / RC / features 2–3)

### 4.0 Agent profile / AGENTS file for `agy` (required design piece)

Wake inject alone is not enough for long-horizon collab. Each `agy` print invocation is a CLI turn that must load a **stable identity** describing:

- You are Rocket.Chat user **`agy`** (Antigravity / Gemini), peer of **`grok`**, supervised by **`principal`**
- Tag-to-talk handoff protocol (`@grok` to continue, omit peer tag to yield)
- Long-horizon norms (disagreement preservation, checkpoints, no fake completion)
- Default read-only write scope unless principal elevates
- Never speak *as* Grok; never invent that Grok agreed
- Repo remains source of truth; RC is the floor

Repo `AGENTS.md` (e.g. PGS) already names **Gemini as Lead Scientist** and a dual-agent disagreement protocol, but it does **not** describe Rocket.Chat dual accounts, @mentions, or multi-day auto-handoff. That gap needs a **collab-specific profile layer**.

#### How Antigravity loads rules today (evidence)

From `agy` built-in docs (`~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/rules.md`):

| Mechanism | Behavior |
| --- | --- |
| **`AGENTS.md` / `GEMINI.md`** | Discovered walking from cwd toward repo root; always-on for that tree |
| **`.agents/rules/*.md`** | Additional rule files in workspace |
| **Custom `agent.md`** | Named agent under `.agents/agents/<name>/agent.md`; selectable via `agy --agent …` |
| **Print prompt (`-p`)** | Per-turn task brief from operator (mention text + room inject) |

Also: `agy --agent` exists; example custom agents live under project brain `.agents/agents/*/agent.md` with YAML frontmatter (`name`, `description`, `tools`, …).

#### Recommended layering (three layers, not one mega-file)

| Layer | Lives where | Loaded how | Contents |
| --- | --- | --- | --- |
| **L1 Domain contract** | Project `AGENTS.md` (e.g. PGS Lead Scientist, claim discipline) | Auto via cwd | Math/program rules; already exists |
| **L2 RC collab social contract** | Dedicated profile (draft in this package under `profiles/`) installed into collab cwd or custom agent | Auto `AGENTS.md` fragment **or** `--agent rc_collab` | Dual-peer @mention protocol, long-horizon norms, RC identity |
| **L3 Per-turn inject** | Built by operator each wake | `-p` / prompt file | Latest mention body, hop count, epoch, write scope, peer last message summary |

**Do not** put L2 only in L3: multi-day collab must not depend on a perfect inject every time.  
**Do not** overload L1 with RC transport details: domain repos stay usable outside Rocket.Chat.

#### Placement options

| Option | Path sketch | Pros | Cons |
| --- | --- | --- | --- |
| **P1 Collab overlay file in project** | e.g. `AGENTS.rc-collab.md` or `.agents/rules/rc-grok-collab.md` under project cwd | Auto-loaded with repo work; versioned with research | Pollutes pure research tree slightly |
| **P2 Custom agy agent** | `.agents/agents/rc_collab/agent.md` + `agy --agent rc_collab` | Clear name; tool allowlist in frontmatter | Must pass `--agent` from operator every wake |
| **P3 Dedicated collab workspace** | `~/IdeaProjects/grok-agy-collab/` with own `AGENTS.md`; `--add-dir` research repo | Clean separation of social contract vs domain | Two trees; cwd vs add-dir discipline |
| **P4 Operator-only system prompt file** | `wake/agy_collab_prompt.txt` prepended every print | Single place next to `reply_prompt.txt` | Easy to drift from agy’s native AGENTS discovery; less sticky inside long conversations |

**Recommendation:** **P2 + L1** for production shape (named agent `rc_collab` always passed by operator), with **P4 inject as L3**. Optionally mirror L2 into `.agents/rules/` (P1) so interactive desktop `agy` sessions in that repo inherit the same social contract. Draft text lives in this research package under [`profiles/`](./profiles/) until install paths are chosen.

#### Symmetric Grok-side profile

When dual-account mode is on, **Grok** needs a collab fragment too (not only `agy`):

- You are RC user `grok`; peer `agy` posts Gemini’s words under their own avatar  
- **Do not** shell into nested `agy` CLI to impersonate Gemini  
- Continue with `@agy` when handoff is useful; omit peer tag when yielding to principal  
- Long-horizon: preserve disagreement; propose checkpoints; respect pause/budget  

Ship as `wake/reply_prompt_agy_collab.txt` fragment or Feature-3 room profile inject — parallel to agy’s L2.

#### Draft artifact (research package)

See **[`profiles/`](./profiles/)** in this folder:

- `agy-rc-collab.agent.md` — draft custom agent / system instructions for Antigravity  
- `agy-rc-collab.AGENTS.md` — draft directory-rules form (same content, AGENTS-style)  
- `grok-rc-collab.inject.md` — draft Grok wake fragment for collab rooms  
- `README.md` — install options and non-goals  

These are **research drafts only** — not installed into `~/.gemini` or live `wake/` until implementation.

### 4.1 Config surfaces to extend

| Surface | Change (conceptual) |
| --- | --- |
| `channel_projects.json` **or** new `room_profiles.json` | `mode`, timeouts, agy cwd, approval override |
| `wake/state.json` | `agy_conversations[room_id]`, hop/epoch counters, pause flags |
| **`agy` identity profile** | Durable rules so Gemini knows RC dual-peer collab (see §4.0) |
| **`grok` collab inject fragment** | Symmetric rules when posting as `grok` in collab rooms |
| `reply_prompt.txt` or fragment | Collab Mode block when profile matches |
| launchd env | Optional global defaults; prefer per-room over global |
| log dir | `~/logs/rocketchat-dm-wake/agy/{room_id}/` for logs + state files |
| secrets | **New** credentials for RC user `agy`; CLI auth for Gemini unchanged |

### 4.2 Message-flow variants

**C1 flow:**

```
principal → Thinking…
  → Grok (collab inject + prior agy UUID)
      → agy_cli.py (start|conversation)
      → integrate
  → reply file (+ optional UUID trailer)
  → operator strips trailer → chat.update
  → operator persists UUID
```

**C2 flow:**

```
principal → Thinking… (held)
  → Grok plan → task file
  → operator agy_cli.py → gemini.txt + UUID
  → Grok integrate(gemini.txt) → reply file
  → chat.update
```

### 4.3 Slash / control grammar (align Feature 3)

Suggested **collab-specific** commands (operator-native parse, principal-only):

| Command | Effect |
| --- | --- |
| `/agy help` | Collab command list |
| `/agy status` | Room cwd, Grok session, agy UUID (short), last rc, mode, timeouts |
| `/agy start [brief…]` | Force mode=start (new Gemini thread); optional brief as wake text |
| `/agy continue [text…]` | Resume pinned UUID (fail if missing) |
| `/agy new` | Clear agy UUID only (keep Grok session) — or full reset policy flag |
| `/agy clean` | One-shot next turn (no continue/conversation) |
| `/agy cwd` | Show agy/Grok cwd alignment |
| `/cancel` | Kill in-flight wake (shared with Feature 3) |

Non-command principal text in collab rooms: treat as **collab turn** (resume UUID by default).

### 4.4 Coupling to Feature 2 (streaming / telemetry)

Collab without progress UX will feel more broken than normal wakes because nested latency is larger.

Minimum phases for collab rooms:

| Phase | Bubble text sketch |
| --- | --- |
| start | `Thinking… · collab · cwd=…` |
| agy | `Working… · consulting Gemini (agy)…` |
| integrate | `Working… · integrating…` |
| fail | Structured: `agy failed: …` / `timeout` / `no UUID captured` |
| done | Final multi-section answer only |

### 4.5 Coupling to Feature 3 (phone control plane)

Collab is a **specialization** of room mission control:

- `/status` includes agy block when `mode=agy-collab`.  
- `/admin once` may be required if collab approval is not profile-elevated.  
- Mission card could pin last falsification criteria Gemini demanded.

### 4.6 NO_DUPLICATE_POSTS interaction (per-speaker)

Under dual-account collab, the hard rule is **per speaker turn**, not “only one bot may ever speak in the room.”

| Allowed | Forbidden |
| --- | --- |
| `grok` Thinking… → one `chat.update` as `grok` for that wake | `grok` posts final text **and** a second answer bubble for the same wake |
| `agy` Thinking… → one `chat.update` as `agy` for that wake | `agy` double-confirm media / double post |
| Sequential turns: agy bubble, then later grok bubble | Both identities posting the **same** answer body for one wake |
| Phase updates on **that turn’s** msgId | Operator finalize + model `chat.postMessage` of the same answer |
| Optional media attach via ledgered helper as the posting identity | Cross-posting Gemini’s full answer under both avatars |

### 4.7 Repository source of truth

Skill contract: **repo remains source of truth**. RC channel is transport + facilitation.

| Artifact | Belongs in |
| --- | --- |
| Durable proof / code / experiment design | Git under project cwd |
| Ephemeral Gemini objection | May live only in RC bubble + logs |
| agy UUID | Operator state (not committed secrets) |
| Collab decisions that change research | Written back to repo by Grok when authorized |

Default Gemini **read-only** unless principal elevates write scope in the brief or via `/admin` / approval card.

---

## 5. Architecture sketches

### 5.1 Logical components (preferred: C3 @mention peers)

```
                 #grok-agy-collab
         principal / grok / agy members
                      │
         WS events (messages + mentions[])
                      ▼
           ┌──────────────────────┐
           │ Mention dispatcher   │
           │ (collab room policy) │
           └───┬──────────────┬───┘
         @grok │              │ @agy
               ▼              ▼
     ┌─────────────────┐  ┌──────────────────┐
     │ Post as: grok   │  │ Post as: agy     │
     │ Thinking…       │  │ Thinking…        │
     │ Grok CLI wake   │  │ agy CLI (helper) │
     │ session pin     │  │ conversation UUID│
     │ chat.update     │  │ chat.update      │
     └────────┬────────┘  └────────┬─────────┘
              │  body includes     │
              │  @agy  ────────────┘
              │                    │
              └────── @grok ◄──────┘
```

C1/C2 collapse into the **right branch** (“how agy backend runs”), not the room UX.

### 5.2 State model (proposed — long-horizon aware)

```json
{
  "version": 2,
  "rooms": {
    "<roomId>": {
      "grok_session_id": "…",
      "cwd": "/Users/…/IdeaProjects/prime-gap-structure",
      "profile": "agy-collab",
      "collab": {
        "mode": "running" ,
        "epoch": 3,
        "hop_count_epoch": 47,
        "hop_budget_epoch": 100,
        "total_hops": 312,
        "last_speaker": "agy",
        "last_hop_at": "ISO-8601",
        "paused_reason": null,
        "auto_handoff": true
      },
      "agy": {
        "conversation_id": "uuid",
        "updated_at": "ISO-8601",
        "last_mode": "conversation",
        "last_rc": 0,
        "last_error": null
      }
    }
  }
}
```

Exact schema is for a future spec. Research requires: **agy UUID**, **Grok session**, **epoch hop counters**, **pause/auto-handoff flags**, and **last-hop timestamps** so multi-day collab is operable from the phone.

### 5.3 Prompt contracts (two injects)

#### When target is `agy` (posted as `agy`)

```text
You are the Rocket.Chat user "agy" (Antigravity / Gemini Lead Scientist).
Room is a human-like collab floor with principal and grok.
You were @mentioned; answer that turn only.
Backend: local agy CLI (print mode); conversation id: <uuid|NONE>.
cwd: <absolute repo>. Write scope: read-only unless principal elevated.
If you need Grok's next move, end with a real @grok mention and a clear ask.
If you are done or waiting on the human, do NOT mention @grok.
Write final user-facing markdown to Reply file only. Operator posts as agy.
Never claim success if the CLI failed.
```

#### When target is `grok` in a collab room (posted as `grok`)

```text
You are "grok" in a dual-peer collab channel with user "agy" (Gemini).
You were @mentioned. Dual-account mode: do NOT shell out to agy CLI to
impersonate Gemini — agy posts as themselves when tagged.
Address the mention content; if you need Gemini, end with a real @agy mention.
If summarizing for principal, no peer mention required.
Reply file only; operator updates your Thinking bubble.
```

---

## 6. Risks and failure modes

| ID | Risk | Severity | Mitigation |
| --- | --- | --- | --- |
| R1 | Restricted wake cannot run `agy` | High | Collab profile `approval=admin` or allowlisted shell tool; Feature 3 admin-once |
| R2 | Parent wake timeout kills nested agy | High | Per-room `wake_timeout_s` ≥ agy timeout + margin |
| R3 | UUID not captured → silent new threads | High | Operator-owned parse (C1b) or C2; fail visible if start expected continue |
| R4 | Invalid UUID starts new thread (skill hazard) | High | Never pass unvalidated UUID; on mismatch log + `/agy status` |
| R5 | Parallel multi-room agy | Medium | Global agy mutex or `MAX_CONCURRENT=1`; queue |
| R6 | `--dangerously-skip-permissions` blast radius | High | Read-only default prompts; cwd allowlist; no secrets paths in brief |
| R7 | Giant Gemini paste floods phone | Medium | Compact section + optional media attach; length cap |
| R8 | Collab burns `max_turns` | Medium | Profile raise; C2 offloads agy outside Grok turns |
| R9 | Model pretends Gemini answered | High | Skill failure rule + operator can verify log file exists |
| R10 | cwd drift (agency vs repo) | High | Profile forces absolute cwd; refuse collab if cwd missing |
| R11 | Channel auto-create / map miss | Medium | Explicit map; IMP-19 no surprise folders |
| R12 | Dual bot double-post same content | High | Per-speaker one-bubble; no cross-repost |
| R13 | Secrets in collab prompts | High | reply_prompt hygiene (IMP-07); never inject env |
| R14 | TTY/`agy version` health checks | Low | Use print-mode smoke, not interactive version |
| R15 | Feature coupling debt | Medium | Spec collab independently; reuse Feature 2/3 hooks as interfaces |
| R16 | **Runaway @mention spin** (pathology) | **Critical** | Soft epoch budget + no-progress detector + `/pause` — **not** tiny hard hop caps |
| R16b | **Too-tight hop cap kills long collab** | **Critical** | Design budgets for tens–hundreds of turns; principal can raise |
| R17 | Mention not linked (plain `@grok` text) | High | Verify RC creates `mentions[]` on bot posts; test on 8.6 |
| R18 | Wake on non-principal without allowlist | High | Collab rooms: allowlist authors `{principal, grok, agy}` only |
| R19 | Second bot credentials leak | High | secrets file mode 600; token auth preferred (IMP-20 style) |
| R20 | Grok still nests agy CLI | Medium | Collab inject forbids nested agy when dual-account mode on |

---

## 7. Security and trust boundaries

1. **Collab rooms use author allowlist** `{principal, grok, agy}` — not “any server user who can @agy”.  
2. **DMs and non-collab channels stay principal-only** unless explicitly re-specified (do not globalize bot↔bot wakes).  
3. **agy auto-approve** is a local Mac privilege; treat collab rooms as elevated research, not public chat.  
4. Prefer **private** channel membership.  
5. Gemini write scope default **off**; principal elevates explicitly.  
6. Do not route Rocket.Chat secrets into either backend prompt.  
7. Second identity credentials live next to existing secrets; prefer token pair over long-lived password in process env.  
8. MCP `agy_*` remains forbidden for the Gemini backend.  
9. **Anti-runaway** (spin / cost / no-progress) is mandatory; **depth limits must not erase long-horizon value**.  
10. Logs under `~/logs/…/agy/` may contain multi-day research content — retention (IMP-08) must fit long collabs.  
11. Unattended auto-handoff is a privilege of **private collab rooms** only — never default in public channels.

---

## 8. Open questions

1. **Which cwd is the default for `#grok-agy-collab`?** Always `prime-gap-structure`, or a neutral workspace?  
2. **One global collab channel vs per-program channels** (`#pgs-agy`, …)?  
3. **Independent session resets:** `/new` for Grok vs clear agy UUID — confirm UX.  
4. **Double-mention policy** when principal tags both `@agy` and `@grok` in one message?  
5. **Length policy** for long Gemini answers (cap vs file attach as `agy`)?  
6. **C3-A vs C3-B:** two launchd agents vs one multi-identity operator?  
7. **Does REST post with `@grok` create a real mention** on RC 8.6 without UI autocomplete? (Lab must answer.)  
8. **Default soft epoch budget** for long-horizon (e.g. 50 / 100 / 200 hops) before forced principal checkpoint?  
9. **Should `agy` use Thinking…** or post only when complete? Prefer Thinking… for symmetry.  
10. **Model pin** for reproducible Gemini print-mode sessions?  
11. **May principal messages without mentions** still wake someone in collab rooms? (Recommend **no** — tag to talk.)  
12. **Context strategy after 50+ turns:** compress sessions, rolling repo summary inject, or new epoch sessions?  
13. **Unattended overnight:** auto-handoff on by default in collab rooms, or require `/unattended on`?  
14. **Checkpoint path convention** under project cwd for joint notes?  
15. **Profile install path:** named `agy --agent rc_collab` vs `.agents/rules/` vs dedicated collab workspace?  
16. **Should PGS `AGENTS.md` link to RC collab rules**, or keep RC transport strictly outside the domain file?

---

## 9. Recommended direction

### 9.1 Product recommendation

Ship collab as a **long-horizon inter-agent floor**: a private channel with three peers (`principal`, `grok`, **`agy`**), **@mention** handoffs like two humans, and infrastructure that stays correct across **many, many turns** (hours to days). Dual accounts are not cosmetic — they make the multi-day transcript attributable. The principal’s job is **mission + supervision**, not typing every hop.

**Example:** `#grok-agy-collab` → members `{principal, grok, agy}` → profile `agy-collab` → tag-to-talk dispatcher → sticky dual sessions → soft epoch budgets → repo checkpoints.

### 9.2 Technical recommendation (phased)

| Phase | What | Why |
| --- | --- | --- |
| **0 Lab** | Create `agy` user; channel; mention physics; install draft **rc_collab** profile; manual multi-hop (5–10) | Prove handoff + identity + profile load |
| **1 MVP** | **C3** dispatcher + dual auth + CLI backends + **per-turn** timeouts + serial room queue + **high soft hop budget** + pause-on-budget | Short long-horizon (tens of turns) works unattended |
| **2 Trust** | Feature 2 phases per identity; structured fail; `/status` hop counters | Multi-hour confidence on phone |
| **3 Durability** | Resume after restart/sleep; epoch + total hop state; checkpoint cadence to repo; context strategy | **Many, many turns** over days |
| **4 Control** | `/pause` `/resume` `/budget` `/cancel` `/checkpoint` | Principal as supervisor |
| **5 Harden** | Spin detection, daily budgets, token auth, retention | Safe unattended |
| **6 Polish** | Threads per subtopic; Apps-Engine | Optional |

**Note on C1:** nesting `agy` inside a Grok wake is **demoted** for collab rooms. Per-turn timeout math stays; collab **lifetime** is unbounded except by budgets/pause.

### 9.3 Explicit non-recommendations (for MVP)

- Do **not** implement collab via MCP `agy_*`.  
- Do **not** raise **global** wake timeout for all rooms — only per-turn collab profile.  
- Do **not** fake two voices from the single `grok` account (C3-C).  
- Do **not** wake on every message (tag-to-talk).  
- Do **not** use a **tiny hard hop cap** (e.g. 6) as the primary safety — that rejects the value prop.  
- Do **not** leave auto-handoff unbounded with **no** spin/budget controls either.  
- Do **not** treat RC scrollback as the only durable research memory — checkpoint the repo.  
- Do **not** auto-create IdeaProjects folders for casual names (IMP-19).  
- Do **not** let Gemini default to write/edit on the repo from RC.  
- Do **not** open bot↔bot wakes outside collab-profile rooms.

### 9.4 Success signals (when later built)

| Signal | Evidence |
| --- | --- |
| Human-like handoff | `@agy` → `@grok` → … without principal every hop |
| **Long-horizon depth** | Same room sustains **≥50 bot↔bot hops** (or multi-hour) with sticky sessions |
| **Multi-day resume** | Operator restart mid-epoch; next mention continues same agy UUID + Grok pin |
| Distinct avatars | Alternating `agy` / `grok` history is the audit trail |
| Sticky Gemini | Late turn still recalls early marker (or repo checkpoint) |
| Honest failure | Fail posts **as** the failing identity |
| Per-turn timeout survival | Single ~10m agy print completes; collab continues after |
| Per-speaker one bubble | One Thinking… → finalize per wake |
| **Epoch pause, not death** | Soft budget hit → pause + principal ping; `/resume` continues same sessions |
| Tag-to-talk | Untagged notes do not wake |
| Skill fidelity | Zero MCP agy; CLI helper for Gemini backend |
| Checkpoint | Repo contains joint notes written during the collab epoch |

### 9.5 Suggested pre-implementation lab checklist

1. Create RC user `agy` (bot); set password/token; store in a **non-git** secrets path for the lab only.  
2. Create private `#grok-agy-collab`; invite `principal`, `grok`, `agy`; map cwd.  
3. **Mention physics:** post as `agy` via REST with body containing `@grok`; confirm `mentions` array / that a future dispatcher would see target `grok`.  
4. Run one `agy_cli.py --mode start` against project cwd; post stdout **as `agy`** with a trailing `@grok` ask (manual).  
5. Confirm today’s operator **does not** wake on `agy`’s message (documents the filter gap).  
6. Time a long print for timeout sizing; note hop-budget desired default.  
7. Decide C3-A vs C3-B before coding.

---

## 10. Worked example (narrative — preferred UX)

**Room:** `#grok-agy-collab`  
**Members:** `principal`, `grok`, `agy`  
**cwd:** `~/IdeaProjects/prime-gap-structure`  
**State:** `agy.conversation_id = null` on first use  

1. **Principal:** `@agy Strongest objection to chamber-reset as an inference gate; falsifiers only. Marker RC_AGY_MARK_42.`  
2. Dispatcher sees mention `agy` → posts **Thinking… as `agy`** → runs `agy_cli.py --mode start` → captures UUID `9f3c…` → `chat.update` as `agy`:

   > Objection is … Falsifiers: …  
   > `@grok` Does this kill chamber-reset as a gate, or only bound it?

3. Dispatcher sees author `agy` + mention `grok` → **Thinking… as `grok`** → Grok CLI wake (no nested agy) → finalize as `grok`:

   > Bounds it if … Experiment E1 would …  
   > `@agy` Steel-man the opposite: why keep the gate?

4. Handoff continues until a bot **omits** the peer mention or hop budget hits.  
5. **Principal:** `@grok One-paragraph joint summary for the log.` → only Grok wakes; no `@agy` unless Grok chooses to re-open.  
6. Channel history is a readable multi-party transcript; backends keep sticky sessions/UUIDs under the hood.

---

## 11. Relationship to existing new-features package

| Feature | Relationship |
| --- | --- |
| **1 Voice Call** | Orthogonal media plane; collab is text-first |
| **2 Streaming telemetry** | **Dependency for good UX** on long agy |
| **3 Phone control plane** | **Natural command host** for `/agy …` |
| **4 This feature** | Multi-model facilitation surface on RC channels |

This package now includes **[spec.md](./spec.md) (NF-SPEC-04)**. Test plan / implementation plan remain deferred until Phase 0 lab answers R1–R3 (or explicit acceptance of the spec).

---

## 12. Sources / primary interfaces

### 12.1 In-repo / live stack

| Source | Role |
| --- | --- |
| `docs/architecture.md` | Component diagram, cwd policy, operator role |
| `docs/message-flow.md` | Thinking… → reply file → `chat.update` |
| `docs/related-systems.md` | PGS notify adjacency; agency spine |
| `new-features/02-streaming-thinking-telemetry/` | Streaming / single-bubble constraints |
| `new-features/03-phone-control-plane/` | Slash control plane patterns |
| `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` | Wake orchestration |
| `~/.grok/agency/ops/rocketchat/wake/wake_lib.py` | Timeouts, locks, sessions, approval flags |
| `~/.grok/agency/ops/rocketchat/wake/reply_prompt.txt` | Every-wake contract |
| `~/.grok/agency/ops/rocketchat/wake/channel_projects.json` | Channel → project map |
| `~/.grok/agency/ops/rocketchat/NO_DUPLICATE_POSTS.md` | Hard posting rule |

### 12.2 Antigravity collab skill

| Source | Role |
| --- | --- |
| `~/.grok/skills/agy-cli-collab/SKILL.md` | CLI-only collab contract |
| `…/scripts/agy_cli.py` | Preferred helper (modes, UUID capture) |
| `…/references/SMOKE_RESULTS.md` | 2026-07-06 PASS evidence |
| `…/references/TEST_PLAN.md` | Gate + sticky recall cases |
| `~/.local/bin/agy` | Print mode, `--conversation`, `--continue`, `--print-timeout` |

### 12.3 External product constraints (Rocket.Chat)

| Interface | Use |
| --- | --- |
| `chat.postMessage` | Thinking… placeholder only (operator) |
| `chat.update` | Final + optional phase edits |
| WebSocket room events | Wake trigger |
| Private channel membership | Trust boundary |
| Optional Apps-Engine | Future slash autocomplete (C5) |

---

## 13. Conclusion

Facilitating Antigravity collaboration through Rocket.Chat fits this stack once collab is modeled as a **long-horizon, multi-turn inter-agent floor** — three peers in a private channel, not a hidden tool call inside Grok, and not a 5-turn demo.

The preferred product direction is explicit:

1. **Create RC user `agy`.**  
2. **Tag to talk** — `@agy` / `@grok` wakes the matching backend.  
3. **Bots tag each other** for **many, many turns**, with the principal as **intermittent supervisor**.  
4. **Each identity owns its Thinking… → answer bubble** — the channel becomes a multi-day attributable ledger.  
5. **Gemini runtime stays local `agy` CLI** (skill contract; no MCP).  
6. **Collab-only exception** to principal-only wake — allowlisted authors in profiled rooms.  
7. **Durability first-class:** sticky dual sessions, per-turn timeouts (not collab lifetime caps), soft epoch budgets, spin detection, **repo checkpoints**, resume after restart/sleep.  
8. **Safety ≠ shallow depth:** stop runaway spin and cost; do not forbid deep collaboration.

Mediated single-bubble designs (C1) remain lab/fallback only. Build **mention dispatcher + dual identity + long-horizon state + anti-runaway (not anti-depth)** first; then streaming, supervisor commands, and context/checkpoint strategy so tens-to-hundreds of turns remain coherent.
