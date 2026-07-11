# Test plan: Streaming Thinking bubble + live work telemetry

| Field | Value |
| --- | --- |
| **ID** | NF-TP-02 |
| **Feature** | Streaming Thinking bubble + live work telemetry |
| **Spec** | [`./spec.md`](./spec.md) (NF-SPEC-02) |
| **Implementation plan** | [`./implementation-plan.md`](./implementation-plan.md) (NF-IP-02) |
| **Research** | [`./research.md`](./research.md) |
| **Related** | `wake/rc_operator_agent.py` (`update_message`, `_process_pending_item`), `compose_unified_reply`, `NO_DUPLICATE_POSTS.md`, usability contracts |
| **Type** | Unit + contract (mock RC) + optional live RC smoke |
| **Status** | Test-planning documentation only · **Last reviewed:** 2026-07-10 |
| **Flags under test** | `RC_WAKE_STREAM`, `RC_STREAM_MIN_INTERVAL_MS`, `RC_STREAM_MAX_UPDATES`, `RC_STREAM_MAX_CHARS`, `RC_STREAM_FALLBACK_TO_STDOUT` |

---

## 1. Scope and traceability

### 1.1 In scope

- Bubble state machine: PLACEHOLDER → RUNNING_META → optional STREAMING_PARTIAL → FINAL_OK | FINAL_ERR  
- Rate limits and final-update guarantee  
- `stopReason` structured empty-reply errors  
- Reply-file as FINAL_OK source of truth  
- Single-bubble / no-duplicate rules  
- Secret non-leakage in stream text  

### 1.2 Out of scope

- Implementing streaming in operator (this package)  
- DDP-only transports as default  
- Second status bubble as production default  

### 1.3 Requirement map

| Spec | Cases |
| --- | --- |
| FR-S1–S4, AC-S1 | TP-S-01, TP-S-02 |
| FR-S5–S7, AC-S2 | TP-S-03, TP-S-04 |
| FR-S6, AC-S3 | TP-S-05 |
| FR-S8–S10, AC-S4–S5 | TP-S-06, TP-S-07, TP-S-08 |
| FR-S11–S12, AC-S7 | TP-S-09, E-S-secret |
| FR-S13 | TP-S-10 |
| NFR-S2–S5 | TP-S-07, E-S-throttle |
| AC-S6 | TP-S-11 |

---

## 2. Test strategy and layers

| Layer | Proves | Tools |
| --- | --- | --- |
| **L0 Unit** | `format_final_err`, stopReason parser, rate limiter pure functions | pytest/unittest |
| **L1 Contract** | Mock `postMessage`/`update_message`; assert update sequence | Existing usability contract style |
| **L2 Golden fixtures** | Parse real/captured wake-run JSON / streaming-json samples | Files under test fixtures |
| **L3 Live opt-in** | Real RC bubble edits | Flag like `RC_LIVE_THINKING=1` |
| **L4 Regression** | Full usability contracts | `test_usability_contracts.py` |

---

## 3. Preconditions

- Ability to load operator modules or extract pure helpers under test  
- Mock RC layer that records `(roomId, msgId, text)` updates in order  
- Fixture wake logs:  
  - `stopReason: Cancelled`, empty reply  
  - `stopReason: EndTurn`, non-empty reply  
  - malformed JSON  
- For L3: live RC + operator (principal-gated)

---

## 4. Concrete test cases

### TP-S-01 — Placeholder then meta within 2s

| | |
| --- | --- |
| **Phase** | T1 |
| **Preconditions** | Mock clock or wall clock; wake start instrumented |
| **Steps** | Enqueue principal message; observe first non-placeholder update. |
| **Expected** | First update is PLACEHOLDER `Thinking...`; meta `Working…` (or equivalent) within **2 s** of wake start (AC-S1, FR-S4). |
| **Pass** | Timed assertion or recorded timestamps |

### TP-S-02 — Meta content fields

| | |
| --- | --- |
| **Phase** | T1 |
| **Steps** | Capture RUNNING_META text. |
| **Expected** | Includes non-final chrome; mode; cwd basename or room; phase/elapsed as specified (UX-S1). Not final answer prose. |
| **Pass** | Regex / field presence |

### TP-S-03 — Empty reply + Cancelled → FINAL_ERR

| | |
| --- | --- |
| **Phase** | T0 |
| **Preconditions** | Wake mock: rc=0, reply file empty, log contains `"stopReason": "Cancelled"` |
| **Steps** | Run finalize path. |
| **Expected** | Single `chat.update` final body contains `stopReason: Cancelled` (or structured equivalent), `rc`, mode, log basename (FR-S5, AC-S2). |
| **Pass** | Body assertions; **not** only generic “no reply file” without stopReason |

### TP-S-04 — Always finalize on failure

| | |
| --- | --- |
| **Phase** | T0 |
| **Preconditions** | Wake mock rc=1, empty reply, no stopReason |
| **Steps** | Process pending item. |
| **Expected** | Placeholder still updated (FR-S7); never left as eternal Thinking… |
| **Pass** | Final update called once with FINAL_ERR |

### TP-S-05 — FINAL_OK from reply file only

| | |
| --- | --- |
| **Phase** | T0–T2 |
| **Preconditions** | Reply file body `HELLO_FINAL`; stream partials say `PARTIAL_DRAFT` |
| **Steps** | Complete wake with stream on or off. |
| **Expected** | Final bubble == compose_unified_reply(reply file); no `Thinking...` prefix; partials discarded for final (FR-S6, AC-S3). |
| **Pass** | Exact body match |

### TP-S-06 — Stream flag off bounds updates

| | |
| --- | --- |
| **Phase** | T1 |
| **Preconditions** | `RC_WAKE_STREAM=0` |
| **Steps** | Long wake simulation. |
| **Expected** | Updates limited to placeholder + meta (+ elapsed meta if any) + final; no token flood (AC-S4). |
| **Pass** | Count updates ≤ policy |

### TP-S-07 — Stream flag on rate limit

| | |
| --- | --- |
| **Phase** | T2 |
| **Preconditions** | `RC_WAKE_STREAM=1`; emit 100 synthetic stream events in 1 s |
| **Steps** | Consume stream through operator updater. |
| **Expected** | Non-final updates ≤ `RC_STREAM_MAX_UPDATES`; min interval respected; **final still applied** (NFR-S2–S5, AC-S5). |
| **Pass** | Counter + timestamps |

### TP-S-08 — Truncate non-final body

| | |
| --- | --- |
| **Phase** | T2 |
| **Steps** | Stream partial longer than `RC_STREAM_MAX_CHARS`. |
| **Expected** | Non-final bubble truncated; final full reply file unrestricted by stream max (or separately capped by RC). |
| **Pass** | len(non_final) ≤ max |

### TP-S-09 — No second answer bubble

| | |
| --- | --- |
| **Phase** | All |
| **Steps** | Successful wake; inspect all `chat.postMessage` vs `chat.update` calls. |
| **Expected** | Exactly one initial post for Thinking…; answer only via update; no second postMessage of final (FR-S11, NO_DUPLICATE). |
| **Pass** | Call log |

### TP-S-10 — health.json telemetry fields

| | |
| --- | --- |
| **Phase** | T3 |
| **Steps** | After FINAL_ERR with Cancelled, read health/state. |
| **Expected** | `last_stop_reason` (or equivalent) set; `last_stream_at` if stream used (FR-S13). |
| **Pass** | JSON fields |

### TP-S-11 — Usability contracts still pass

| | |
| --- | --- |
| **Phase** | All |
| **Steps** | Run `test_usability_contracts.py` (and integration suite). |
| **Expected** | All existing contracts pass; multi-update mocks added if needed (AC-S6). |
| **Pass** | Exit 0 |

### TP-S-12 — compose_unified_reply interaction

| | |
| --- | --- |
| **Phase** | T0 |
| **Steps** | Reply file starts with `Thinking...\n\nbody`. |
| **Expected** | Final bubble strips Thinking prefix per existing helper rules. |
| **Pass** | Unit against real `compose_unified_reply` |

### TP-S-13 — Concurrent rooms (if multi-wake)

| | |
| --- | --- |
| **Phase** | T2 |
| **Preconditions** | RC_WAKE_MAX_CONCURRENT > 1 or serial rooms |
| **Steps** | Two rooms wake; stream both. |
| **Expected** | Updates apply to correct msgId/room; no cross-talk. |
| **Pass** | Mock dual rooms |

---

## 5. Edge cases and negative / failure cases

| ID | Edge / failure | Expected |
| --- | --- | --- |
| **E-S-01** | Malformed wake log (no JSON) | FINAL_ERR still produced; stopReason=unknown/omitted cleanly |
| **E-S-02** | stopReason present but reply non-empty | FINAL_OK from reply; stopReason may log-only |
| **E-S-03** | chat.update fails mid-stream | Log error; still attempt final; no crash of operator loop |
| **E-S-04** | chat.update fails on final | Logged; processed-id policy per existing contracts (document) |
| **E-S-05** | Wake timeout (rc=124) | FINAL_ERR mentions timeout; not silent Thinking… |
| **E-S-06** | Resume session failure retry | Meta may show new session; final still correct |
| **E-S-07** | Empty principal message with attachment only | Existing STT path; stream rules still apply |
| **E-S-08** | Reply file written late after process exit race | Document: read after wait(); no TOCTOU empty final if file appears later — read once after exit |
| **E-S-09** | Partial contains secret-like string `sk-` / path `secrets/rocketchat.env` | Filtered or redacted (AC-S7, FR-S12) |
| **E-S-secret** | Tool event dumps env | Must not appear in any update text (fixture) |
| **E-S-10** | Unicode / emoji heavy partial | No crash; valid RC text |
| **E-S-11** | Extremely rapid principal double message | Per-room queue: two bubbles sequential; no interleaved msgId corruption |
| **E-S-12** | RC_STREAM_MAX_UPDATES=0 | Meta-only or immediate final policy documented; no div-by-zero |
| **E-S-13** | Stream events after process already waited | Ignored; final already sent |
| **E-S-14** | Working… chrome missing (looks final) | Fail UX check TP-S-02 |
| **E-S-15** | Fallback stdout enabled, empty reply, partial present | If flag on: final from partial + log “fallback”; if off: FINAL_ERR |
| **E-S-16** | Operator restart mid-wake | Lock TTL / stale reclaim; no eternal Thinking if possible (document gap) |
| **E-S-throttle** | Interval 800 ms, 5 events at t=0 | ≤ 1–2 non-final updates in first 800 ms window |
| **E-S-17** | Message edit permission revoked | Fail closed; log; operator continues |
| **E-S-18** | stopReason EndTurn but empty reply | FINAL_ERR (empty still empty); not fake OK |

---

## 6. Fixtures to manufacture (implement-time)

| Fixture | Content |
| --- | --- |
| `wake-cancelled.json` | CLI json with Cancelled + empty reply |
| `wake-ok.json` | EndTurn + sessionId |
| `stream-events.ndjson` | Synthetic streaming-json lines (after schema capture OD-S1) |
| `secret-leak-events.ndjson` | Events containing fake secrets for filter tests |

---

## 7. Pass / fail and exit criteria

| Phase | Exit when |
| --- | --- |
| T0 | TP-S-03,04,05,12 + E-S-01,05,18 pass |
| T1 | TP-S-01,02,06 + rate meta bounds |
| T2 | TP-S-07,08 + stream fixtures + E-S-throttle |
| T3 | TP-S-10 + Feature 3 status alignment if present |

**Hard fails:** eternal Thinking…; second final postMessage; secrets in bubble; final skipped due to throttle.

**Evidence:** ordered update transcripts from mock RC; fixture hashes; live screenshots optional.

---

## 8. Open / blocked

| Item | Note |
| --- | --- |
| OD-S1 streaming-json schema | T2 cases blocked until golden capture |
| Mobile redraw performance | L3 manual only |

---

## 9. References

- NF-SPEC-02 FR-S*, AC-S*, state machine §4  
- Research incident: empty reply + Cancelled under acceptEdits  
- `NO_DUPLICATE_POSTS.md`  
- Usability: thinking_then_in_place_update_flow, thinking_failure_still_updates_placeholder  
