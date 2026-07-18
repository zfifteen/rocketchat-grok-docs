# Implementation Plan: Always-on activity phase chrome

| Field | Value |
| --- | --- |
| **ID** | UX-IP-PHASE-CHROME |
| **Related review** | [2026-07-14 Heavy review](2026-07-14-rc-integration-heavy-review.md) (H4, M13; trust UX) |
| **Related feature** | NF-02 streaming / telemetry ([new-features/02-…](../../new-features/02-streaming-thinking-telemetry/)) |
| **Runtime home** | `~/.grok/agency/ops/rocketchat/wake/` |
| **Primary files** | `wake_telemetry.py`, `rc_operator_agent.py`, `wake_lib.py` (compose finals), tests under `ops/rocketchat/tests/` |
| **Status** | Plan only · **Created:** 2026-07-14 · not implemented |

---

### Project Title

Always-on **phase chrome** on the single Rocket.Chat activity bubble (liveness + phase + elapsed), with **answer-first / error-first** finals.

---

### Overview

Today the operator posts one activity bubble (`…`) and either:

1. **Stream on (default):** paints thought chunks when available; **no meta heartbeat** while stream mode is active until thoughts arrive — tool-heavy wakes sit on `…` for a long time; or  
2. **Stream off:** runs `format_running_meta` + heartbeat (Working…, cwd, elapsed).

The principal’s highest-pain failure mode is **“looks alive, actually stuck or empty.”** The math-research incident and review finding **M13** are the same UX class: silence is not progress.

This plan evolves the **existing** single-bubble path (no second `chat.postMessage` for the answer) so that:

- From first paint until FINAL, the bubble always shows **phase chrome** (phase + elapsed + room/cwd short).
- Optional thought text is **secondary** under chrome, not a replacement for liveness.
- FINAL_OK is **answer-first** (thoughts optional below or omitted by flag).
- FINAL_ERR is **error-first** (stopReason / short diagnosis above any thoughts).

It reuses machinery already present: `format_running_meta`, `wake_meta_enabled`, `StreamThrottle`, `stream_finalized`, `finalize_thinking_message`, `compose_final_with_thoughts`.

---

### Key Themes Alignment

- **One bubble / NO_DUPLICATE_POSTS** — progress stays on the same `msgId` (`chat.update` only).
- **Reply-file truth** — FINAL_OK still comes from the reply file (or salvage); chrome is non-final only.
- **Phone-first trust** — principal can tell working vs failed at a glance.
- **NF-02 evolution** — completes RUNNING_META under default stream-on (gap in current code at `rc_operator_agent.py` ~2359–2360: meta HB only when `not stream_on`).
- **Review-driven** — addresses M13 (long `…`), partially H4/M5 (error buried under thoughts) without waiting for full crash-safety track.

---

### Objectives

**Primary Objective**  
Ship always-on phase chrome on the Grok activity bubble so that, for every wake, the principal sees a non-empty status line within ~2s of start and at least every heartbeat until FINAL, then a final body that leads with answer or error—not a silent `…`.

**Secondary Objectives**

- Unify intermediate body layout: chrome always; thoughts optional under chrome.
- Flip FINAL composition to **answer-first** (and **error-first** on FINAL_ERR).
- Keep RC update budget under existing throttle caps (no 429 regression).
- Cover with unit tests + one usability contract; opt-in live DM smoke.
- Document flags in `ROCKETCHAT.md` and NF-02 / message-flow as needed.

---

### Success Metrics

| Kind | Metric | Target |
| --- | --- | --- |
| **Quantitative** | Time to first non-`…` status paint | ≤ 2 s after activity bubble post (meta or chrome+empty thoughts) |
| **Quantitative** | Silent `…` duration with meta on | 0 continuous silence longer than `RC_STREAM_HEARTBEAT_S` (default 15s) while wake runs |
| **Quantitative** | Intermediate `chat.update` rate | Still bounded by stream throttle (default min interval ~2s, max updates ~12 mid-wake) |
| **Quantitative** | Usability / NF-02 tests | Existing suite green; new phase-chrome tests pass |
| **Qualitative** | Principal glance test | Can say “still working” vs “failed with reason” without reading full thoughts |
| **Qualitative** | No second final bubble | On happy path and FINAL_ERR path, still one agent msgId (fallback second post remains last-resort only — out of scope to delete here; track under review H4) |
| **Validation** | Phone DM smoke | One restricted wake with no thoughts for ≥20s shows ticking elapsed; empty Cancelled shows error-first |

---

### Mathematical / Theoretical Foundations (if applicable)

Not applicable (product UX + operator control flow). Invariant only:

\[
\text{published non-final body} = \text{chrome}(+ \text{optional thoughts tail})
\]
\[
\text{FINAL\_OK body} = \text{answer}(+ \text{optional thoughts section})
\]
\[
\text{FINAL\_ERR body} = \text{error block}(+ \text{optional thoughts section})
\]

---

### Assumptions and Priors

| Assumption | Evidence |
| --- | --- |
| `chat.update` on grok’s own messages works on RC 8.6 | Live operator production path |
| `format_running_meta` / `RC_WAKE_META` already exist and default on | `wake_telemetry.py:48–52`, `format_running_meta` |
| Stream default on **disables** meta HB today | `rc_operator_agent.py:2359–2360` (`if … and not stream_on`) |
| Thoughts replace meta once text exists | `_push_meta` returns early when `stream_on and thoughts.text.strip()` (~2289–2290) |
| FINAL currently puts thoughts **above** answer | `compose_final_with_thoughts` in `wake_lib.py:638–675` |
| NO_DUPLICATE_POSTS remains non-negotiable | `ops/rocketchat/NO_DUPLICATE_POSTS.md` |
| Restricted mode stays `--permission-mode auto` | IMP-01; out of scope for this plan |

---

### Novel Hypotheses

| Hypothesis | Basis |
| --- | --- |
| **H1:** Always-on chrome reduces “is it hung?” false reports more than denser thought streams | Principal complaints + M13; silence is the failure, not lack of tokens |
| **H2:** Answer-first finals improve mobile completion rate of reading the answer | Mobile scroll; FINAL_ERR buried under long *Thoughts* (review M5) |

These are product hypotheses; Phase 5 manual soak validates subjectively, not A/B.

---

### Design

#### Intermediate bubble (non-final)

```text
Working · #math-research · 0:48 · tools
────────────────
(optional thought tail, throttled, truncated)
```

| Element | Source |
| --- | --- |
| Verb / phase | `starting` \| `running` \| `tools` \| `thinking` \| `finalizing` (start with starting/running/thinking; tools optional later) |
| Room | short room name |
| Elapsed | `monotonic - wake_t0` as `m:ss` |
| Optional line 2 | short cwd basename / approval mode (already in `format_running_meta`) |
| Thoughts | Only if stream on and thought buffer non-empty; **below** chrome, never instead of chrome |

**Critical control-flow change:** Meta heartbeat runs whenever `wake_meta_enabled()` and bubble exists — **including when `RC_WAKE_STREAM=1`**. When thoughts exist, paint `chrome + thoughts tail`, not thoughts alone.

#### Final bubble

**FINAL_OK (default):**

```text
<answer from reply file>

*Thoughts*          ← optional, flag-gated or only if non-empty
…
────────────────
```

Preferred order for this UX plan: **answer first**, then thoughts (invert current `compose_final_with_thoughts`). Flag `RC_FINAL_THOUGHTS_POSITION=below|above|omit` with default **`below`**.

**FINAL_ERR:**

```text
**Wake failed** · stopReason=Cancelled · rc=0
(short hint)

*Thoughts* (optional, truncated)
```

Error block must be in the first ~500 characters so mobile clients show it without scrolling past a monologue.

#### Publish serialization (minimal scope)

To avoid regressing H4 while changing intermediate paints:

- Single **bubble lock** (threading.Lock) around “compose body → `update_message`” for both meta and thought flush.
- Re-check `stream_finalized` **immediately before** send and **after** acquire lock.
- FINAL holds the same lock for the final update.

Full “never second post” remediation stays under review **H4**; this plan only reduces last-writer races for the new dual paints.

#### Flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `RC_WAKE_META` | `1` (existing) | Master for phase chrome / heartbeat |
| `RC_WAKE_STREAM` | `1` (existing) | Thought tail under chrome |
| `RC_STREAM_HEARTBEAT_S` | `15` (existing) | Chrome repaint interval when nothing else dirty |
| `RC_PHASE_CHROME` | `1` (new) | Kill switch for “chrome always with thoughts”; `0` = legacy stream-replaces-meta |
| `RC_FINAL_THOUGHTS_POSITION` | `below` (new) | `below` \| `above` \| `omit` |
| `RC_FINAL_ERR_THOUGHTS` | `tail` (new) | `omit` \| `tail` (truncated) |

---

### Implementation Phases

#### Phase 0: Spec freeze (docs only)

- Tasks:
  - Confirm layout strings and phase vocabulary with principal (optional one-message sign-off).
  - Record non-goals: collab agy path parity can follow; no new bubble; no reactions change.
- Deliverables: this plan (done); optional short UX contract bullet in `tests/USABILITY_CONTRACTS.md` draft.
- Estimated effort: 0.5 d
- Validation: plan linked from reviews README / NF-02 if desired.

#### Phase 1: Pure formatters + unit tests

- Tasks:
  - Add `format_phase_chrome(...)` → single status line(s) (wrap or refactor `format_running_meta`).
  - Add `compose_intermediate_bubble(chrome, thoughts, max_chars)`.
  - Add `compose_final_answer_first(answer, thoughts, position=...)`.
  - Add `compose_final_error_first(err_body, thoughts, ...)`.
- Deliverables: `wake_telemetry.py` / `wake_lib.py` helpers; tests in `test_nf02_streaming_telemetry.py` or new `test_phase_chrome.py`.
- Estimated effort: 0.5–1 d
- Validation: pure unit tests; no operator process required.

#### Phase 2: Operator intermediate path (stream + meta coexistence)

- Tasks:
  - Start meta HB when meta enabled **even if** `stream_on`.
  - Change `_flush_thoughts` to publish chrome+thoughts via shared helper.
  - Change `_push_meta` to not skip when thoughts empty under stream; when thoughts present and `RC_PHASE_CHROME=1`, still paint chrome header.
  - Introduce bubble publish lock + finalized re-check before send.
  - Immediate force chrome paint after placeholder post (`phase=starting`).
- Deliverables: `rc_operator_agent.py` `_process_pending_item` changes (Grok path first).
- Estimated effort: 1–2 d
- Validation:
  - Unit/integration with mocked `update_message` recording bodies over time.
  - Assert: with stream on and zero thought events for 20s wall-clock in fake clock, ≥1 heartbeat body with increasing elapsed.
  - Assert: thought events produce bodies that **start with** chrome prefix.

#### Phase 3: Final body order (answer-first / error-first)

- Tasks:
  - Wire `compose_final_*` into `finalize_thinking_message` / `choose_final_body` consumers.
  - FINAL_ERR: keep structured err text first; optional truncated thoughts after rule.
  - Update any tests that snapshot full final strings (usability, nf02).
- Deliverables: `wake_lib.py` / `rc_operator_agent.py` finalize path.
- Estimated effort: 0.5–1 d
- Validation: golden string tests; FINAL_ERR fixture places `stopReason` before any long thought dump.

#### Phase 4: Agy parity (optional, small)

- Tasks: If agy path posts a placeholder, apply same chrome helper (no stream). Skip if collab remains off.
- Deliverables: minimal `_process_agy_collab_item` meta HB or single starting chrome.
- Estimated effort: 0.5 d
- Validation: mocked agy finalize still one bubble.

#### Phase 5: Docs, flags, soak

- Tasks:
  - `ROCKETCHAT.md` Access / NF-02 table: stream + meta coexistence; new flags.
  - `docs/message-flow.md` intermediate state diagram update.
  - Point review M13 as addressed when shipped; leave H4 residual noted if second-post fallback remains.
  - Live DM: long tool wake + Cancelled empty wake.
- Deliverables: docs; optional CHANGELOG.
- Estimated effort: 0.5 d
- Validation: principal glance test; no 429 storm in 5 consecutive wakes.

**Total estimated effort:** ~3–5 engineer-days for Phases 1–3 + 5 (core ship). Phase 4 optional.

---

### Tools and Technologies

| Item | Value |
| --- | --- |
| Language | Python 3.13 (operator venv) |
| Runtime | `~/.grok/agency/ops/rocketchat/.venv` |
| Tests | `cd ~/.grok/agency/ops/rocketchat && .venv/bin/python -m pytest tests/test_nf02_streaming_telemetry.py tests/test_usability_contracts.py -q` |
| Lint | project norms; `py_compile` on touched modules |
| Docs | this repo `rocketchat-agents` |
| Benchmarking | count `chat.update` calls in mock; wall elapsed to first chrome in integration test |

---

### Validation and Testing Strategy

**Unit / Integration**

- Formatter pure tests (chrome line, truncation, answer-first, error-first).
- Operator path with mocked REST: sequence of update bodies under (a) stream on, no thoughts (b) stream on, thoughts (c) stream off (d) FINAL_OK (e) FINAL_ERR.
- Race smoke: set `stream_finalized` mid fake flusher; assert no post-final body applied when lock+recheck implemented.

**Usability contracts**

- Extend §7: intermediate must not remain lone `…` longer than heartbeat when meta on.
- Keep §8 no-dupe: still one intentional final path (document fallback as known residual).

**Manual / Acceptance**

| Check | Pass criteria |
| --- | --- |
| DM long wake | Chrome ticks elapsed ≥ twice before final |
| Channel wake | Room name appears in chrome |
| Empty Cancelled | Error-first visible without scrolling thoughts |
| Happy path answer | Answer at top; thoughts below if any |
| Kill switch | `RC_PHASE_CHROME=0` restores legacy stream-replaces-meta |

**Static**

- No secrets in chrome (cwd may be path — already true for meta; do not add tokens).

---

### Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Extra updates → RC 429 | Medium | Final stuck on thoughts | Shared throttle; chrome shares thought interval; heartbeat only if last paint aged |
| Chrome + thoughts exceeds RC size | Medium | Truncated / failed update | Single max_chars budget; prefer chrome fixed + thoughts tail |
| Answer-first surprises users who liked Thoughts-first | Low | Preference | Flag `RC_FINAL_THOUGHTS_POSITION=above` |
| Last-writer race worsens | Medium | Lost FINAL | Bubble lock + recheck (Phase 2) |
| Scope creep into crash recovery (C3) | Medium | Delay UX ship | Explicit non-goal; link review for separate track |
| Agy path forgotten | Low | Inconsistent UX | Phase 4 optional; collab off by default |

---

### Timeline

| Milestone | Target | Dependencies | Status |
| --- | --- | --- | --- |
| Plan accepted | Day 0 | Principal OK | [ ] |
| Phase 1 formatters + tests | Day 1 | — | [ ] |
| Phase 2 operator intermediate | Day 2–3 | Phase 1 | [ ] |
| Phase 3 final order | Day 3–4 | Phase 1 | [ ] |
| Phase 5 docs + live soak | Day 4–5 | Phase 2–3 | [ ] |
| Phase 4 agy (optional) | After core | Phase 2 | [ ] |

---

### Non-goals (this plan)

- Fixing state.json RMW, crash-after-dequeue, media ledger (review C2/C3/H3).
- Removing finalize fallback second post entirely (H4 full fix).
- Dual-identity collab product.
- Changing 👀 reaction behavior.
- LiveKit / voice UX.
- True token streaming (RC has no token channel).

---

### References and Resources

**Repo / runtime examined**

| Path | Relevance |
| --- | --- |
| `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` | `_process_pending_item`, `_push_meta`, `_flush_thoughts`, meta HB only when `not stream_on` |
| `~/.grok/agency/ops/rocketchat/wake/wake_telemetry.py` | `format_running_meta`, stream/meta flags, throttles, heartbeats |
| `~/.grok/agency/ops/rocketchat/wake/wake_lib.py` | `compose_final_with_thoughts` (thoughts above answer today) |
| `~/.grok/agency/ops/rocketchat/NO_DUPLICATE_POSTS.md` | One answer bubble rule |
| `~/.grok/agency/ops/rocketchat/tests/USABILITY_CONTRACTS.md` | §7 bubble contract |
| `rocketchat-agents/new-features/02-streaming-thinking-telemetry/implementation-plan.md` | NF-IP-02 prior T0/T1 framing |
| `rocketchat-agents/docs/reviews/2026-07-14-rc-integration-heavy-review.md` | M13, H4, M5 |

**External:** none required.

---

### Suggested commit sequence (when implementing)

1. `feat(wake): pure phase chrome + answer-first composers + unit tests`
2. `feat(wake): always-on meta with stream; bubble publish lock`
3. `feat(wake): FINAL answer-first / error-first wiring`
4. `docs: phase chrome flags + message-flow + review cross-link`

---

### Open decisions (principal)

1. Default final thoughts position: **`below`** (recommended) vs keep `above`?
2. Should chrome show **cwd basename** on mobile (longer) or room-only (shorter)?
3. Ship Grok path only first, or require agy parity in same PR?
