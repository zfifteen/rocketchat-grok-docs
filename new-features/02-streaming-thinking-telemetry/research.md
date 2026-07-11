# Feature 2 — Streaming Thinking bubble + live work telemetry

**Status:** Research only (no runtime implementation in this document set)  
**Date:** 2026-07-10 · **Last reviewed:** 2026-07-10  
**Stack baseline:** Operator `rc_operator_agent.py`; single-bubble contract `Thinking...` → reply file → `chat.update`; Grok CLI headless `--output-format json` (also supports `streaming-json`); RC 8.6 REST `chat.postMessage` / `chat.update`  
**Hard rule preserved:** `~/.grok/agency/ops/rocketchat/NO_DUPLICATE_POSTS.md` — one answer bubble; never a second `chat.postMessage` for the same final answer.

### Downstream documentation (normative chain)

| Layer | Document | ID |
| --- | --- | --- |
| **Spec** | [spec.md](./spec.md) | NF-SPEC-02 |
| **Test plan** | [test-plan.md](./test-plan.md) | NF-TP-02 |
| **Implementation plan** | [implementation-plan.md](./implementation-plan.md) | NF-IP-02 |

**Canonical recommended direction:** T0 structured `FINAL_ERR` (`stopReason`) → T1 meta updates → T2 optional `RC_WAKE_STREAM` partials. Reply file remains FINAL_OK source of truth.

**Live stack fact (2026-07-10):** Restricted wakes use `--permission-mode auto` (not `acceptEdits`). The empty-reply incident used **`acceptEdits`** (historical); do not reintroduce `acceptEdits` as restricted default. See `wake_lib.approval_mode_cli_flags` and `ops/ROCKETCHAT.md`.

---

## 1. Problem framing (against the live stack)

### 1.1 What the principal experiences today

For every principal message in a watched room:

1. Operator posts **`Thinking...`** via `chat.postMessage` (`post_thinking_placeholder`).  
2. Operator builds wake prompt (`reply_prompt.txt` + inject), spawns Grok CLI.  
3. Grok runs **to completion** (or cancel/timeout); ideally writes **reply file**.  
4. Operator reads reply file; **`chat.update`** replaces Thinking… with final body only (`finalize_thinking_message` → `update_message`).

During steps 2–3 the bubble is frozen on `Thinking...`. Long research wakes feel dead. Failures that return `rc=0` with empty reply (e.g. 2026-07-10 `stopReason=Cancelled` under `acceptEdits`) produce only a generic post-hoc string:

> (No reply file content from the wake. The work may have failed silently — please retry.)

### 1.2 Why this is a product gap (not mere polish)

| Gap | Impact |
| --- | --- |
| No intermediate progress | User cannot tell “working” from “stuck operator / dead Mac” |
| Terminal state only after full wake | Multi-minute channel work looks broken |
| `rc=0` + empty reply | Silent failure class; trust collapse (recent incident) |
| Tool activity invisible on phone | Principal cannot see cwd, permission mode, or “writing reply file” |
| No cancel UX | Cannot abort a runaway wake from phone |

### 1.3 Non-negotiable constraints

1. **One bubble** for the answer (NO_DUPLICATE_POSTS).  
2. Final text must **replace** Thinking… (not append “Thinking…\n\nanswer”) — `compose_unified_reply` already enforces final-only.  
3. Grok must not `chat.postMessage` the answer itself (`reply_prompt.txt`).  
4. Restricted approval modes remain (IMP-01); telemetry must not leak secrets (IMP-07).  
5. Phone mobile clients must not thrash on update floods.

---

## 2. Current baseline / interfaces (precise)

### 2.1 Operator message APIs (shipped)

| Function | REST | Purpose |
| --- | --- | --- |
| `post_message_get_id` | `POST /api/v1/chat.postMessage` | Create bubble; capture `message._id` |
| `update_message` | `POST /api/v1/chat.update` body `{roomId, msgId, text}` | In-place edit; verified own messages on RC 8.6 |
| `finalize_thinking_message` | wraps `update_message` | Final body only |
| `_process_pending_item` | orchestration | Thinking → wake → read reply file → finalize |

Source: `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py`.

Rocket.Chat does **not** expose a dedicated “token stream” channel for bot replies. Streaming UX is built by **repeated `chat.update`** (or realtime DDP edits) on the same `msgId`. Clients already render live edits for human edits; the same path applies.

### 2.2 Grok CLI headless outputs

From local `grok --help` (principal Mac install):

| Flag | Values | Relevance |
| --- | --- | --- |
| `--output-format` | `plain`, `json`, **`streaming-json`** | Today production uses **`json`** (single final object with `text`, `stopReason`, `sessionId`, `thought`) |
| `--prompt-file` | path | Wake inject |
| `--max-turns` | N | Default 12 (`RC_WAKE_MAX_TURNS`) |
| `--permission-mode` / `--always-approve` | see IMP-01 | Restricted → `auto` after 2026-07-10 hotfix |

Current wake runner (`_run_wake_once`):

- `subprocess.Popen` with stdout+stderr → **one log file**.  
- `proc.wait(timeout=WAKE_TIMEOUT_S)` — **no line-by-line consumption**.  
- Session id extracted from final JSON blob (`extract_session_id_from_output`).

**Implication:** Streaming requires either:

- switch wake to **`streaming-json`** and parse incremental events, or  
- side-channel files (progress file written by a wrapper / rules), or  
- a custom middleware that does not exist yet.

### 2.3 Health / logs already present (underused in chat)

| Artifact | Path | Fields (example) |
| --- | --- | --- |
| `health.json` | `~/logs/rocketchat-dm-wake/health.json` | `ts`, `ws_connected`, `rooms_count`, `last_wake_at`, `pid`, `approval_mode` |
| `wake-run-*.log` | same log dir | cmd + final JSON |
| `wake-reply-*.txt` | same | final user body |
| `operator-agent.log` | same | drain/wake/finalize lines |
| IMP-12 health script | `scripts/rc_health_check.sh` | exit 0 if fresh + `ws_connected` |

These are **ops-facing**, not bubble-facing.

### 2.4 Usability contracts that streaming must not break

From `tests/USABILITY_CONTRACTS.md` / `test_usability_contracts.py`:

- Thinking then **in-place** update.  
- Failure still updates placeholder (no eternal Thinking…).  
- No canned multi-message spam.  
- Mark processed only after wake attempt.

Any streaming design must keep these tests green (extend them, do not delete).

---

## 3. Candidate technical approaches

### Approach S1 — Coarse phase updates only (no token stream)

**Mechanism:** Operator (not the model) updates the bubble at lifecycle edges:

| Phase | Example bubble text |
| --- | --- |
| queued | `Thinking… (queued)` |
| starting | `Thinking… · cwd=prime-gap-structure · mode=restricted` |
| running | `Working… · wake started · session=…` |
| tools (if detectable) | `Working… · tools active` |
| finalizing | `Working… · writing reply` |
| done | **final answer only** (current finalize) |
| fail | **structured error** with `stopReason` / `rc` / log tail hint |

**Sources of phase signals:** operator code only (no CLI stream parse required). Optional: poll reply file size / mtime.

| Pros | Cons |
| --- | --- |
| Small change; preserves single bubble | No token-level “typing” feel |
| Easy rate limit | Still opaque during long tool loops |
| No dependency on `streaming-json` schema stability | Less “wow” |

**Fit:** Strong **MVP** for trust after silent-fail incident.

---

### Approach S2 — Grok CLI `streaming-json` → throttled `chat.update`

**Mechanism:**

1. Launch wake with `--output-format streaming-json`.  
2. Operator thread reads stdout line-by-line (or NDJSON events).  
3. Map events to bubble text (assistant partials, tool_start/tool_end, final).  
4. Throttle updates (e.g. max 1/s, or every N chars / every event type change).  
5. On process exit, prefer **reply file** as source of truth for final body; fall back to last streamed assistant text.  
6. If `stopReason` ∈ {`Cancelled`, …} and reply empty → structured failure body (not generic only).

| Pros | Cons |
| --- | --- |
| True live progress | Must reverse/stabilize streaming-json event schema |
| Surfaces cancel mid-flight | Mobile update load if unthrottled |
| Aligns with modern agent UIs | Partial text may include tool junk — needs filtering |

**Fit:** **Recommended target** after S1.

**Open schema work:** Capture a real `streaming-json` sample under controlled headless run; document event types before coding production parser. Do not invent fields.

---

### Approach S3 — Dual message (status thread + answer bubble)

Post a second “status” message, stream there, keep Thinking… for final only.

| Pros | Cons |
| --- | --- |
| Clean separation | **Violates spirit of one-bubble UX**; risks duplicate-looking spam |
| Easy to delete status later | Mobile noise |

**Verdict:** Reject for default production; optional debug flag only (`RC_WAKE_DEBUG_STATUS_MSG=1`).

---

### Approach S4 — Realtime DDP `stream-room-messages` edit from operator WS

Operator already holds a WebSocket for subscriptions. Message updates might be pushable via DDP methods instead of REST `chat.update`.

| Pros | Cons |
| --- | --- |
| Possibly lower latency | Undocumented / fragile vs REST |
| Same connection | Auth/method names version-sensitive |

**Verdict:** Research spike only; REST `chat.update` is **verified** on 8.6 — prefer REST for production.

---

### Approach S5 — Side-channel progress file written by model

Prompt instructs Grok to append phases to `wake-progress-{ts}.txt`; operator tails it.

| Pros | Cons |
| --- | --- |
| Works with current `json` format | Model may forget; burns turns |
| Simple parser | Not trustworthy for failure telemetry |

**Verdict:** Optional supplement; never sole source of truth.

---

## 4. Recommended architecture (S1 → S2)

### 4.1 Bubble state machine

```
IDLE
  → PLACEHOLDER          # "Thinking..."
  → RUNNING_META         # phase lines / meta footer
  → STREAMING_PARTIAL    # optional assistant draft (S2)
  → FINAL_OK             # reply file body only
  → FINAL_ERR            # structured error only
```

Transitions owned by operator; Grok never owns the bubble id for text answers.

### 4.2 Proposed text shapes

**Meta phase (not final):**

```text
Working…
• room: #Prime-Gap-Structure
• cwd: …/prime-gap-structure
• mode: restricted
• phase: tools
• elapsed: 12s
```

Keep short — mobile viewport. Avoid dumping env or secrets.

**Final OK:** unchanged — pure user-facing markdown from reply file.

**Final ERR (improve over today):**

```text
(Wake did not produce a reply file.)
stopReason: Cancelled
rc: 0
approval_mode: restricted
hint: Headless permission cancel or max-turns; retry or /admin if elevated tools needed.
log: wake-run-<ts>.log
```

Parse `stopReason` from wake log JSON when present (the recent incident always left it in the log even when reply was empty).

### 4.3 Rate limiting and client safety

| Parameter | Suggested default | Rationale |
| --- | --- | --- |
| `RC_STREAM_MIN_INTERVAL_MS` | 750–1000 | Avoid mobile flicker / rate limits |
| `RC_STREAM_MAX_UPDATES` | 40 per wake | Cap abuse |
| `RC_STREAM_MAX_CHARS` | 3500 while streaming | Truncate partials; full answer on final |
| Final update | always | Contracts require finalize even on fail |

### 4.4 Integration points in code (future work map — not implementing here)

| Location | Change concept |
| --- | --- |
| `_run_wake_once` | Stream-read stdout; callback on events |
| `wake_grok` / `_process_pending_item` | Phase updates; parse stopReason on empty reply |
| `build_wake_argv` | Optional `output_format="streaming-json"` when feature flag on |
| `health.json` | Add `last_stream_at`, `last_stop_reason` |
| `reply_prompt.txt` | Document that partials may appear; final still **reply file only** |
| Tests | Extend thinking contracts with multi-update sequence mock |

### 4.5 Interaction with reply file contract

**Source of truth for FINAL_OK remains the reply file.**  
Reasons:

1. Matches existing NO_DUPLICATE_POSTS and prompt training.  
2. Streaming partials may be tool narration, not the user-facing answer.  
3. Media posts (`rc_post_media.py`) stay separate; bubble stays short status + final prose.

If reply file non-empty and stream partials exist → **prefer reply file**.  
If reply file empty and stream has assistant text → optional fallback (feature flag), with clear “fallback from stream” log line.

---

## 5. Risks and failure modes

| Risk | Mitigation |
| --- | --- |
| Update spam / RC rate limit | Throttle + max updates |
| Mobile battery / flicker | Min interval; fewer meta phases |
| Partial text looks final; user leaves mid-wake | Always show non-final chrome (`Working…` prefix) until FINAL_* |
| streaming-json schema drift | Pin Grok CLI version; golden fixture tests |
| Race: finalize before last stream event | Sequence numbers; finalize after `wait()` returns |
| Leaking secrets via tool output into bubble | Filter paths under `secrets/`; deny known env dumps (IMP-07) |
| Concurrent rooms | Per-room locks (IMP-10) already serialize same room; cap concurrent streams |
| Contract test breakage | Update mocks to allow N updates then final |

---

## 6. Open questions

1. Exact event types and field names of `streaming-json` on the installed Grok CLI build (capture fixture before production).  
2. Does RC 8.6 mobile client coalesce rapid `chat.update` or redraw fully each time?  
3. Should phase meta be markdown code block vs plain lines for readability?  
4. Cancel-from-phone: message reaction vs slash command `/cancel` (ties Feature 3)?  
5. Preserve `thought` field for ops logs only, never bubble?

---

## 7. Recommended direction

### Phase plan

| Phase | Deliverable | Success signal |
| --- | --- | --- |
| **T0** | Structured FINAL_ERR including `stopReason` from wake log | Empty-reply incidents self-explain |
| **T1** | S1 phase updates (queued / running / mode / cwd / elapsed) | No frozen bare `Thinking...` >2s after start |
| **T2** | Flag `RC_WAKE_STREAM=1` + streaming-json partials throttled | Partial prose visible on long wakes |
| **T3** | health.json + optional `/status` (Feature 3) share same telemetry model | One schema for chat and ops |

### Success signals

1. Principal can distinguish “working” from “dead” within 2 seconds of sending.  
2. A cancelled headless wake shows **why**, not only “no reply file.”  
3. Final bubble is still **one** message with **answer only** (or structured error only).  
4. Usability contracts pass with multi-update mock.  
5. No secrets appear in streamed text under test suite.

### Explicit non-goals

- Second answer bubble.  
- Full terminal log dump into RC.  
- Replacing reply-file finalization.  
- Realtime collaborative editing of the bubble by the principal mid-wake (v1).

---

## 8. Sources and primary interfaces

| Kind | Reference |
| --- | --- |
| Operator finalize path | `wake/rc_operator_agent.py` (`post_thinking_placeholder`, `update_message`, `_process_pending_item`) |
| Reply composition | `wake/wake_lib.py` (`THINKING_PLACEHOLDER`, `compose_unified_reply`) |
| Prompt rules | `wake/reply_prompt.txt` |
| Duplicate ban | `ops/rocketchat/NO_DUPLICATE_POSTS.md` |
| Contracts | `tests/USABILITY_CONTRACTS.md` |
| Message flow | `docs/message-flow.md` §A |
| Grok CLI | local `grok --help` → `--output-format streaming-json` |
| RC REST | `chat.postMessage`, `chat.update` (RC 8.6 verified for own messages) |
| Health | `~/logs/rocketchat-dm-wake/health.json`, `scripts/rc_health_check.sh` |
| Incident grounding | 2026-07-10 empty reply + `stopReason: Cancelled` under `acceptEdits` |

---

## 9. Research conclusion

The single-bubble architecture is a **strength**. The missing piece is **time-varying content** on that bubble plus **honest terminal states**. Ship structured errors and coarse phases first (low risk), then optional `streaming-json` partials behind a flag. That turns Thinking… from a dead placeholder into a live work window without abandoning the reply-file / no-duplicate contract that keeps this stack sane.
