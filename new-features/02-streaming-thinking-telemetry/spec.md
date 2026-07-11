# Technical Specification: Streaming Thinking bubble + live work telemetry

| Field | Value |
| --- | --- |
| **Spec ID** | NF-SPEC-02 |
| **Version** | 1.1 |
| **Status** | Specification (implementation out of scope for this document package) |
| **Date** | 2026-07-10 · **Last reviewed:** 2026-07-10 |
| **Prior research** | [`./research.md`](./research.md) |
| **Test plan** | [`./test-plan.md`](./test-plan.md) (NF-TP-02) |
| **Implementation plan** | [`./implementation-plan.md`](./implementation-plan.md) (NF-IP-02) |
| **Related** | `wake/rc_operator_agent.py`, `wake/wake_lib.py`, `NO_DUPLICATE_POSTS.md`, usability contracts |
| **Owner surface** | Single answer bubble lifecycle (Thinking… → live updates → final) |

---

## 1. Problem and context

### 1.1 Problem statement

Every principal message currently produces a static **`Thinking...`** placeholder until a full headless Grok wake completes, then a single `chat.update` with the reply-file body (or a generic empty-reply error). During the wake the principal cannot distinguish progress from hang. Worse, wakes that exit `rc=0` with empty reply files and `stopReason=Cancelled` (2026-07-10 incident under headless **`acceptEdits`**, since fixed to restricted **`auto`**) surface only a low-information error after the fact. Structured FINAL_ERR must still surface `stopReason` for any future cancel class.

### 1.2 Context (live stack)

| Element | Current fact |
| --- | --- |
| Placeholder | `post_thinking_placeholder` → `chat.postMessage` text `Thinking...` |
| Finalization | `finalize_thinking_message` → `chat.update` with reply-file body only |
| Wake runner | `_run_wake_once`: subprocess wait; stdout to log; `--output-format json` |
| CLI capability | Grok supports `--output-format streaming-json` (not used in production wakes today) |
| Hard rule | One answer bubble; Grok must not `chat.postMessage` the final answer |
| Health | `health.json` exists but is ops-only, not bubble-facing |

### 1.3 Spec purpose

Define the engineering contract for **time-varying content on the single answer bubble** and **structured terminal telemetry**, without violating the reply-file / no-duplicate contracts.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
| --- | --- |
| G1 | Principal sees non-static progress within ~2 seconds of wake start. |
| G2 | Empty-reply / cancel failures expose **actionable** terminal fields (`stopReason`, `rc`, mode, log id). |
| G3 | Preserve **exactly one** answer bubble per wake (NO_DUPLICATE_POSTS). |
| G4 | Final OK body remains **reply-file source of truth** (not tool-stream junk). |
| G5 | Mobile clients remain usable (throttled updates). |
| G6 | Existing usability contracts remain green (extended, not deleted). |

### 2.2 Non-goals

| ID | Non-goal |
| --- | --- |
| NG1 | Second “status” message as default production UX. |
| NG2 | Dumping full CLI logs or secrets into RC. |
| NG3 | Principal collaborative mid-wake editing of the bubble (v1). |
| NG4 | Replacing reply-file finalization with stream-only answers as default. |
| NG5 | Implementing the feature in this documentation goal. |

---

## 3. Normative requirements

### 3.1 Functional requirements

| ID | Requirement |
| --- | --- |
| **FR-S1** | The operator **shall** continue to create a single placeholder message per wake and finalize that same `msgId` via `chat.update`. |
| **FR-S2** | The operator **shall** transition the bubble through an explicit state machine: at minimum `PLACEHOLDER` → `RUNNING_META` → (`STREAMING_PARTIAL` optional) → `FINAL_OK` \| `FINAL_ERR`. |
| **FR-S3** | While not final, bubble text **shall** be clearly non-final (e.g. prefix `Working…` or equivalent); it **shall not** look like a completed answer. |
| **FR-S4** | On wake start, the operator **should** publish a meta update including room name, approval mode, and cwd basename within **2 seconds**. |
| **FR-S5** | When the reply file is empty at process end, the operator **shall** parse wake log output for `stopReason` (and related JSON fields when present) and include them in `FINAL_ERR`. |
| **FR-S6** | When the reply file is non-empty, `FINAL_OK` **shall** be the reply-file contents after `compose_unified_reply` (final answer only; no `Thinking...` prefix retained). |
| **FR-S7** | The operator **shall always** attempt a final `chat.update` even on wake failure (no eternal Thinking…). |
| **FR-S8** | Optional token/partial streaming **shall** be gated by configuration (`RC_WAKE_STREAM=0\|1`); default **may** ship meta-only first. |
| **FR-S9** | When `RC_WAKE_STREAM=1`, the wake process **shall** use an output format capable of incremental events (`streaming-json` or successor) and the operator **shall** consume stdout incrementally. |
| **FR-S10** | Streaming updates **shall** be rate-limited (see NFR-S2–S4). |
| **FR-S11** | The operator **shall not** post a second message containing the final answer (NO_DUPLICATE_POSTS). |
| **FR-S12** | Telemetry fields written for the bubble **shall not** include secrets, tokens, or full env dumps (IMP-07). |
| **FR-S13** | `health.json` **should** gain `last_stop_reason` and `last_stream_at` (or equivalent) when available. |

### 3.2 Non-functional requirements

| ID | Requirement |
| --- | --- |
| **NFR-S1** | Time from Thinking… post to first meta update **should** be ≤ **2 s**. |
| **NFR-S2** | Minimum interval between non-final `chat.update` calls **shall** default to **750–1000 ms** (`RC_STREAM_MIN_INTERVAL_MS`). |
| **NFR-S3** | Maximum non-final updates per wake **shall** default to **40** (`RC_STREAM_MAX_UPDATES`). |
| **NFR-S4** | Non-final bubble body **shall** be truncated to a configurable max (default **3500** chars). |
| **NFR-S5** | Final update **shall not** be skipped due to rate limits. |
| **NFR-S6** | Feature **shall** work for DM and channel rooms already supported by the operator. |
| **NFR-S7** | Implementation **shall** extend unit/usability tests with multi-update sequences; tests **shall not** be deleted to pass. |

### 3.3 UX content requirements

| ID | Requirement |
| --- | --- |
| **UX-S1** | Meta phase **should** include: phase label, elapsed seconds, mode, cwd basename, optional session short id. |
| **UX-S2** | `FINAL_ERR` **shall** include at least: human one-liner, `rc`, `stopReason` if known, `approval_mode`, wake log basename. |
| **UX-S3** | `FINAL_OK` **shall** be user-facing markdown only (no meta chrome). |

### 3.4 Example normative texts

**RUNNING_META (illustrative):**

```text
Working…
• room: #Prime-Gap-Structure
• cwd: prime-gap-structure
• mode: restricted
• phase: running
• elapsed: 12s
```

**FINAL_ERR (illustrative):**

```text
(Wake did not produce a reply file.)
stopReason: Cancelled
rc: 0
approval_mode: restricted
hint: Headless tool approval cancelled or incomplete turn; retry or elevate if needed.
log: wake-run-1783738937.log
```

---

## 4. Architecture and design decisions

### 4.1 Selected approach (research S1 → S2)

| Phase | Behavior |
| --- | --- |
| **T0** | Structured `FINAL_ERR` with `stopReason` parse (no stream required) |
| **T1** | Operator-owned meta phase updates (S1) |
| **T2** | Optional `streaming-json` partials behind flag (S2) |
| **T3** | Shared telemetry schema with Feature 3 `/status` |

### 4.2 Bubble state machine (normative)

```
IDLE
  → PLACEHOLDER            # "Thinking..."
  → RUNNING_META           # Working… meta
  → STREAMING_PARTIAL      # optional draft (flag)
  → FINAL_OK | FINAL_ERR   # terminal; no further non-final updates
```

Transitions owned exclusively by the operator process.

### 4.3 Decision record

| Decision | Choice | Rationale | Rejected |
| --- | --- | --- | --- |
| D1 Final body source | Reply file for FINAL_OK | Prompt + NO_DUPLICATE contract | Stream-only default |
| D2 Transport | REST `chat.update` | Verified on RC 8.6 own messages | Default DDP-only path |
| D3 Dual message status | Off by default | Spam / duplicate risk | Always-on second bubble |
| D4 Stream format | `streaming-json` when enabled | CLI supports it | Side-channel progress file as sole truth |
| D5 Empty reply | Structured FINAL_ERR | Incident class | Generic one-liner only |

### 4.4 Finalization algorithm (normative)

```
on wake process exit:
  body = read(reply_file).strip()
  stopReason, sessionId = parse_wake_log(log_file)  # best-effort
  if body:
    final = compose_unified_reply(body)
    state = FINAL_OK
  else:
    final = format_final_err(rc, stopReason, approval_mode, log_basename)
    state = FINAL_ERR
  chat.update(msgId, final)  # always attempt
  update health.json telemetry fields
  mark processed (existing rules)
```

### 4.5 Streaming algorithm (when enabled)

```
spawn grok with output_format=streaming-json
for each stdout event (parsed):
  if terminal: break
  if rate_limit_allows and updates < max:
    text = render_partial_or_meta(event)
    chat.update(msgId, text)
on exit: run finalization algorithm (reply file wins)
```

**Open:** exact event schema of `streaming-json` on installed CLI (OD-S1). Implementation **shall** capture a golden fixture before production parser lands.

---

## 5. Integration contracts

### 5.1 Code touch points (implement-time map)

| Location | Contract change |
| --- | --- |
| `post_thinking_placeholder` / `update_message` | Unchanged REST shapes; more call frequency |
| `_run_wake_once` | Incremental stdout consumer + optional callbacks |
| `_process_pending_item` | Phase updates; FINAL_ERR formatting |
| `build_wake_argv` / `wake_lib` | `output_format` parameter when stream flag on |
| `compose_unified_reply` | Still used for FINAL_OK only |
| `reply_prompt.txt` | Document meta/partial visibility; reply file still mandatory for final |
| Usability tests | Multi-update mock sequences |

### 5.2 Compatibility with Feature 3

| Shared field | Use |
| --- | --- |
| `last_stop_reason` | `/status` + FINAL_ERR |
| `last_wake_rc` | already partial in state |
| phase | optional `/status` if wake active |

### 5.3 Compatibility with approval modes

Meta **shall** display effective `approval_mode` for the wake. FINAL_ERR hints **may** reference elevation (`/admin once`) once Feature 3 exists; until then, static hint text is acceptable.

---

## 6. Interfaces and configuration

### 6.1 Environment variables (proposed)

| Variable | Default | Meaning |
| --- | --- | --- |
| `RC_WAKE_STREAM` | `0` | `1` enables streaming-json partials |
| `RC_STREAM_MIN_INTERVAL_MS` | `800` | Throttle |
| `RC_STREAM_MAX_UPDATES` | `40` | Cap non-final updates |
| `RC_STREAM_MAX_CHARS` | `3500` | Truncate non-final body |
| `RC_STREAM_FALLBACK_TO_STDOUT` | `0` | If `1` and reply empty, use last assistant partial |

### 6.2 Log / health fields (proposed)

| Field | Location |
| --- | --- |
| `last_stop_reason` | `health.json` / state |
| `last_stream_at` | `health.json` |
| `last_wake_rc` | existing / reinforce |
| wake log JSON `stopReason` | `wake-run-*.log` (already produced by CLI json mode) |

### 6.3 Operator log lines (proposed)

- `stream phase=running msg=<id>`  
- `stream update n=<k> chars=<n>`  
- `finalize thinking … stopReason=<…> body_len=<…>`  

---

## 7. Phased delivery and acceptance criteria

### 7.1 Phases

| Phase | Deliverable | Gate |
| --- | --- | --- |
| **T0** | FINAL_ERR includes stopReason parse | Repro empty-reply shows Cancelled etc. |
| **T1** | RUNNING_META updates | No bare Thinking… beyond 2s after start |
| **T2** | RC_WAKE_STREAM partials | Long wake shows growing draft; final still reply file |
| **T3** | health.json + Feature 3 alignment | `/status` shows last stopReason |

### 7.2 Acceptance criteria

- [ ] AC-S1: Wake start → meta update visible ≤ 2s (instrumented test or manual).  
- [ ] AC-S2: Forced empty reply + Cancelled JSON → FINAL_ERR contains `stopReason: Cancelled`.  
- [ ] AC-S3: Successful wake → single bubble; body equals reply file; no second answer post.  
- [ ] AC-S4: With stream off, no more than meta+final updates (bounded).  
- [ ] AC-S5: With stream on, updates ≤ max; final still correct.  
- [ ] AC-S6: Usability contracts suite passes.  
- [ ] AC-S7: Secret paths not present in any streamed bubble text under unit fixtures.

### 7.3 Validation strategy

| Layer | Method |
| --- | --- |
| Unit | `format_final_err`, rate limiter, stopReason parser against golden log fixtures |
| Contract | Mock `update_message` call sequences (placeholder → meta* → final) |
| Integration (opt-in) | Live RC wake with `RC_LIVE_THINKING=1` style flag |
| Regression | Existing `test_usability_contracts.py` paths |

---

## 8. Risks, dependencies, mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| RC / mobile update thrash | Medium | Throttle + max updates + truncate |
| streaming-json schema drift | High for T2 | Golden fixture; feature flag |
| Partial looks final | Medium | Mandatory Working… chrome until FINAL_* |
| Race finalize vs last stream event | Medium | Finalize only after process wait returns |
| Secret leakage via tool events | High | Filters; never stream raw env |
| Rate limit final drop | High | Final bypasses throttle |

### Dependencies

- Stable Grok CLI headless output formats on principal Mac  
- RC 8.6 `chat.update` continues to allow operator self-edits  
- Optional: Feature 3 for elevation hints (soft dependency)

---

## 9. Open decisions

| ID | Decision | Default if forced |
| --- | --- | --- |
| **OD-S1** | Exact streaming-json event schema | Capture fixture in implement phase before T2 |
| **OD-S2** | Default `RC_WAKE_STREAM` at general availability | `0` (meta-only) until fixture stable |
| **OD-S3** | Fallback to stdout partial when reply empty | `0` (prefer structured err) |
| **OD-S4** | Meta markdown style (bullets vs code block) | Bullets |
| **OD-S5** | Cancel-from-phone interaction | Defer to Feature 3 `/cancel` |

---

## 10. Traceability

| Spec element | Research anchor |
| --- | --- |
| S1 → S2 phases | Research §4, §7 |
| State machine | Research §4.1 |
| Rate limits | Research §4.3 |
| Reply file truth | Research §4.5 |
| Incident grounding | Research §1.1; wake-run Cancelled logs |
| APIs | Research §2.1–2.2; `update_message` in operator |

---

## 11. Document control

- Normative for a future implementation goal adopting NF-SPEC-02.  
- Prior research retained at `research.md` in this bundle.  
- Any change that would require a second answer bubble **shall** be treated as a breaking change requiring a new spec version and principal approval.
