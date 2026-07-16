# B4 + B5 Spec — `chat.update` rate-limit throttle & empty-reply recovery
**Author:** claude  
**Date:** 2026-07-15  
**Collab:** #21 operator-interaction-bugs-2026-07-15  
**Bugs:** B4 (P1 — HTTP 429 on `chat.update`), B5 (P1 — Cancelled / empty-reply recovery churn)  
**Residuals covered:** B6 (P2), B8 (P2), B9 (P2) — notes only, no implementation

---

## B4 — HTTP 429 on `chat.update` (thought-stream thrash)

### Root cause (traced from runtime)

`rc_operator_agent.py` runs two concurrent update paths on the same bubble:

1. **`_thought_flusher` thread** — fires on `RC_THOUGHT_FLUSH_MS` interval (default 2 s) and calls `update_thinking_meta` → `update_message` with `retries=0` when there is accumulated thought text.
2. **`_meta_hb` thread** (non-streaming mode) — fires on `RC_STREAM_HEARTBEAT_S` interval (default 15 s) and calls `update_thinking_meta` → `update_message` with `retries=0`.
3. **`finalize_thinking_message`** — the FINAL update calls `update_message` with `retries=5`, preceded by a hard `time.sleep(1.0)` cool-down.

Evidence from `wake_telemetry.py` comment at line 25–26:
> *"Live logs: 10–13 updates in ~20 s → 429 on finalize."*

What happens in practice (heavy multi-agent bursts):
- Thought stream accumulates fast during tool calls. The flusher fires every 2 s, hitting the bubble **~5–6 times before any RC window resets**.
- RC's per-user `chat.update` rate limit appears to be roughly 5–8 calls per 10 s window (observed, not documented publicly).
- When the LLM finishes and `finalize_thinking_message` attempts its `chat.update`, RC returns HTTP 429. The `time.sleep(1.0)` cool-down is too short when the flusher has just fired.
- `StreamThrottle` (`wake_telemetry.py`, class `StreamThrottle`) caps at `DEFAULT_MAX_UPDATES = 12` total mid-wake updates but does **not** enforce a minimum gap between the last non-final update and the FINAL call. That gap is only the hard 1 s sleep in `finalize_thinking_message`.

### Requirements

| ID | Requirement |
|----|-------------|
| R4-1 | Non-final `chat.update` rate must be capped so that at most N calls (env `RC_STREAM_MAX_UPDATES`, default 12) occur in any given wake, AND the last non-final update must finish at least `RC_FINAL_COOL_S` seconds (default **3.0**) before the FINAL update attempt. |
| R4-2 | `finalize_thinking_message` must enforce the cool-down dynamically: measure `time.monotonic()` since the last non-final update (tracked in `StreamThrottle.last_update_at`) and sleep the remainder if < `RC_FINAL_COOL_S`. The current hard `sleep(1.0)` becomes a floor, not the actual gate. |
| R4-3 | `StreamThrottle` must expose a `seconds_since_last(now)` helper and a `final_cool_remaining(cool_s, now)` helper so `finalize_thinking_message` can query it without coupling. |
| R4-4 | Multi-agent burst: when four operators all call `chat.update` concurrently for different messages in the same room, RC still rate-limits per-user. Each operator sends under a different RC auth identity (`grok`, `hermes`, `agy`, `claude`), so the per-user budget is separate. No cross-operator coordination is needed. Confirm this in acceptance. |
| R4-5 | `RC_FINAL_COOL_S` env var (float, default 3.0, floor 1.0) controls the minimum gap between last non-final update and FINAL. |
| R4-6 | If the cool-down would exceed 8 s (e.g. a very recent thought flush), log a warning but still wait (don't skip the cool-down). |

### Proposed change

**`wake_telemetry.py` — extend `StreamThrottle`:**

```python
DEFAULT_FINAL_COOL_S = 3.0

def final_cool_s(env: dict[str, str] | None = None) -> float:
    source = env if env is not None else os.environ
    try:
        return max(1.0, float((source.get("RC_FINAL_COOL_S") or str(DEFAULT_FINAL_COOL_S)).strip()))
    except ValueError:
        return DEFAULT_FINAL_COOL_S

# In StreamThrottle:
def seconds_since_last(self, *, now: float | None = None) -> float:
    t = time.monotonic() if now is None else now
    if self.updates == 0:
        return float("inf")
    return t - self.last_update_at

def final_cool_remaining(self, cool_s: float, *, now: float | None = None) -> float:
    """Seconds to sleep before the FINAL update to avoid 429."""
    elapsed = self.seconds_since_last(now=now)
    return max(0.0, cool_s - elapsed)
```

**`rc_operator_agent.py` — `finalize_thinking_message`:**

Replace the hard `time.sleep(1.0)` with a dynamic cool-down:

```python
# Pass the completed thought_throttle into finalize_thinking_message (new kwarg):
#   finalize_thinking_message(..., stream_throttle=thought_throttle)
cool = stream_throttle.final_cool_remaining(final_cool_s()) if stream_throttle else 1.0
cool = max(cool, 1.0)  # floor still 1 s even when no prior updates
if cool > 8.0:
    log(f"final cool-down capped at 8.0s (was {cool:.1f}s)")
    cool = 8.0
time.sleep(cool)
```

### Test plan (pure unit tests — no RC network)

All tests live in `ops/rocketchat/tests/test_multi_round_collab.py` or a new `test_wake_telemetry.py`.

| Test name | What it checks |
|-----------|----------------|
| `test_stream_throttle_seconds_since_last_no_updates` | `seconds_since_last()` returns `inf` when `updates == 0`. |
| `test_stream_throttle_seconds_since_last_after_update` | After one `allow()`, `seconds_since_last(now=t+5)` ≈ 5. |
| `test_final_cool_remaining_none_needed` | When last update was 4 s ago and cool_s=3.0, returns 0.0. |
| `test_final_cool_remaining_some_needed` | When last update was 1 s ago and cool_s=3.0, returns ≈ 2.0. |
| `test_final_cool_s_env_override` | `RC_FINAL_COOL_S=5` returns 5.0; `RC_FINAL_COOL_S=0.1` returns 1.0 (floor). |
| `test_429_acceptance_no_nonfinal_since_final_gap` | Simulate: flusher updates up to max, then assert `final_cool_remaining` == 0 after `cool_s` elapsed. |
| `test_429_acceptance_nonfinal_just_fired` | Simulate: flusher updates 0.5 s before FINAL → assert cool remaining ≈ cool_s − 0.5. |

### Acceptance criteria

1. `final_cool_remaining` returns 0 when last non-final was ≥ `RC_FINAL_COOL_S` ago.
2. `finalize_thinking_message` never sleeps less than 1 s and no more than 8 s before its `chat.update`.
3. All 7 unit tests pass.
4. Live smoke (if safe): one long collab wake with `RC_STREAM_MAX_UPDATES=4` and `RC_FINAL_COOL_S=3` — no 429 logged on finalize.

---

## B5 — Cancelled wakes / empty-reply recovery churn

### Root cause (traced from runtime)

**Recovery path (`rc_operator_agent.py` lines 2586–2650):**

When a wake ends with `stopReason=Cancelled`, `rc=0`, and an empty reply file, the operator:

1. Releases the in-flight lock on the original `mid`.
2. Re-enqueues the same `mid` as a retry message (`is_empty_reply_retry=True`).
3. Posts an interim bubble update: `"(First attempt ended incomplete — retrying once…)"`.
4. Spawns a `_drain_pending_wakes` thread to run the retry immediately.

**The churn problems:**

- **Double-wake without reply:** If the retry also Cancels with an empty reply, the code path hits `should_retry_empty = False` (because `is_empty_reply_retry=True`), so the operator finalizes a `FINAL_ERR` — but the room already saw the interim "retrying…" bubble. Two stalls visible.
- **Trigger condition too broad:** Any `rc=0` + `Cancelled` + empty reply triggers the retry, including wakes cancelled legitimately (e.g. principal cancelled a tool). The distinction between *operator-cancelled* (bad) and *agent-cancelled* (tool prompt rejected) is not gated.
- **Retry always targets `target="grok"`** in `_enqueue_pending` (line 2622), even when the wake was triggered by a `@claude` or `@hermes` assign. That means if claude's wake is retried, it re-enqueues under grok's processing path. (See also B8 note on drain target.)
- **No minimum content threshold for salvage vs retry decision:** `choose_final_body` already salvages non-empty headless text (>80 chars, structured). But if the LLM streamed substantial thought text yet wrote nothing to the reply file, the salvage path is attempted and may succeed — then the retry is not triggered. The gap is when thought text is short/empty AND no reply file.

### Requirements

| ID | Requirement |
|----|-------------|
| R5-1 | Before triggering the single auto-retry, check if the headless wake streamed substantive thought text (`len(thought_text.strip()) >= 80`). If so, use thought text as salvage candidate (pass to `extract_salvageable_body`) before falling back to retry. This avoids a second wake when the LLM clearly did work. |
| R5-2 | Retry enqueue must use the completing operator's identity as `target`, not hardcoded `"grok"`. Pass `operator` (e.g. `"claude"`) through the retry call so the retry wake runs under the right identity. |
| R5-3 | Rate-limit retries per room: no more than one empty-reply retry per room within `RC_RETRY_COOLDOWN_S` seconds (default 60). Track `last_retry_at[room_id]` in local state. If a retry is already pending for this room, finalize with `FINAL_ERR` and log, rather than queuing a second retry. |
| R5-4 | Add `is_empty_reply_retry` to the log line so operators can trace retry chains without forensics. |
| R5-5 | Interim bubble text ("retrying once…") must be distinct from the final FINAL_ERR body; the current text `"(First attempt ended incomplete…)"` already matches `_EMPTY_FAILURE_TEMPLATES` patterns, so return-notify suppression works correctly — confirm in tests. |
| R5-6 | Optional (free if easy): expose `RC_WAKE_AUTO_RETRY=0` env var to disable empty-reply auto-retry room-wide (e.g. for high-volume channels where retries cause more thrash than they fix). |

### Proposed change sketch

**Add thought-text salvage before retry (R5-1):**

```python
# Before: should_retry_empty check
# After: also try to salvage accumulated thoughts
if not reply_body and thoughts.text.strip():
    salvaged_from_thoughts = extract_salvageable_body(thoughts.text)
    if salvaged_from_thoughts:
        reply_body = salvaged_from_thoughts
        log(f"thought-stream salvage chars={len(reply_body)} room={room_name}")
        # Re-run choose_final_body with salvaged content
        final_body, phase, _ = choose_final_body(
            reply_file_body=reply_body, rc=rc,
            log_text=log_text, approval_mode=approval_mode,
            log_basename=log_basename, compose_ok=compose_unified_reply,
        )
```

**Fix retry target (R5-2):**

```python
# current:
if _enqueue_pending(retry_msg, rid, room_name, room_type, target="grok", ...)
# proposed:
retry_target = OPERATOR_USERNAME  # the completing operator's identity
if _enqueue_pending(retry_msg, rid, room_name, room_type, target=retry_target, ...)
```

**Per-room retry rate-limit (R5-3):**

```python
# In local operator state (state.json):
_retry_timestamps: dict[str, float] = {}  # room_id → monotonic time

def _can_retry_room(room_id: str, cooldown_s: float = 60.0) -> bool:
    last = _retry_timestamps.get(room_id, 0.0)
    return (time.monotonic() - last) >= cooldown_s

def _record_retry(room_id: str) -> None:
    _retry_timestamps[room_id] = time.monotonic()
```

### Test plan

| Test name | What it checks |
|-----------|----------------|
| `test_thought_salvage_before_retry` | When reply_body empty but thoughts.text is ≥ 80 chars structured, salvage succeeds and `should_retry_empty` is False. |
| `test_thought_salvage_too_short` | Thoughts < 80 chars, no structured markers → salvage fails → retry triggered (if other conditions met). |
| `test_retry_target_is_operator_not_grok` | Recovery re-enqueue uses the completing operator's username, not "grok". |
| `test_per_room_retry_cooldown_blocks_second_retry` | Retry registered for room_A; second Cancelled wake for room_A within 60 s → no retry queued, FINAL_ERR shown. |
| `test_per_room_retry_cooldown_allows_after_expiry` | After cooldown expires, next Cancelled wake for same room → retry allowed. |
| `test_rc_wake_auto_retry_off` | `RC_WAKE_AUTO_RETRY=0` → no retry enqueued even on clean Cancelled + empty reply. |
| `test_interim_bubble_matches_failure_template` | Interim "First attempt ended incomplete" text matches `_EMPTY_FAILURE_TEMPLATES` so return-notify is suppressed. |
| `test_final_err_after_retry_cancel` | Retry wake also Cancels → FINAL_ERR finalized; no second retry; `is_empty_reply_retry=True` in log. |

### Acceptance criteria

1. All 8 unit tests pass.
2. No second retry is queued when the first retry also Cancels.
3. Retry target identity matches the completing operator (not hardcoded "grok").
4. Per-room cooldown prevents retry storms: ≥ 2 consecutive Cancelled wakes in one room within 60 s → only one retry attempt total.
5. Thought-stream salvage prevents a retry when the LLM streamed ≥ 80 chars of structured content.

---

## Residuals — B6 / B8 / B9 (notes only, no implementation this turn)

### B6 — Duplicate room-msg log / double-seen

Observed: same `room msg author=…` log lines twice in rapid succession for the same `mid`. Most likely cause: the RC WebSocket re-delivers the `room-messages` event on reconnect, and the dedup (`already queued/processed`) fires correctly after the first enqueue but not before the second log write. No message storms observed as a result (dedup works). Fix candidate: move the `log()` call to after the dedup check, not before. Low urgency.

### B8 — Drain log always says `target=grok`

`_drain_pending_wakes` logs a fixed `target=grok` string regardless of which operator's identity is dequeuing. This is a logging-only issue; routing itself uses the actual stored target. Fix: thread the actual `target` field from the queue item through the drain log call. Straightforward one-liner once B5 fixes retry target.

### B9 — Hard wake failure `rc=-6`

`rc=-6` is a platform-level signal (child process killed, e.g. SIGKILL from macOS process limits or out-of-memory). Not recoverable at the operator layer. Recommendation: add `rc < 0` as a distinct log category (`WAKE_HARD_FAIL`) and health-snapshot field so /status shows it visibly. Do not auto-retry on `rc < 0`; the retry path (B5) already gates on `rc == 0`.

---

## Summary for grok

- **B4:** `StreamThrottle` needs `final_cool_remaining()` helper; `finalize_thinking_message` needs dynamic cool-down (env `RC_FINAL_COOL_S`, default 3 s, floor 1 s). 7 unit tests planned.
- **B5:** Three issues — thought-stream salvage before retry, retry target hardcoded to grok, no per-room retry rate-limit. 8 unit tests planned.
- **B6/B8/B9:** Root causes identified; low-risk, short patches noted above. Not implemented this turn.

No code landed yet (design spec only). Patches are straightforward and testable in `ops/rocketchat/tests/`. Ready to implement if grok re-assigns or if I get a free round.

STATUS: done  
FOR: @grok  
