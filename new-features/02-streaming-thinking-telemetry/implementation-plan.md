# Implementation plan: Streaming Thinking bubble + live work telemetry

| Field | Value |
| --- | --- |
| **ID** | NF-IP-02 |
| **Feature** | Streaming Thinking bubble + live work telemetry |
| **Spec** | [NF-SPEC-02](./spec.md) (**source of truth for flags & shalls**) |
| **Test plan** | [NF-TP-02](./test-plan.md) (**source of truth for validation gates**) |
| **Research** | [research.md](./research.md) |
| **Runtime home** | `~/.grok/agency/ops/rocketchat/wake/` (`rc_operator_agent.py`, `wake_lib.py`, `reply_prompt.txt`) |
| **Status** | Implementation-planning documentation only · **Last reviewed:** 2026-07-10 |

---

## 1. Overview and goals

### 1.1 Problem

Static `Thinking...` hides progress and masks failures (`rc=0` + empty reply + `stopReason=Cancelled`). Principal cannot distinguish work from hang.

### 1.2 Primary objective

Evolve the **single answer bubble** through PLACEHOLDER → RUNNING_META → optional STREAMING_PARTIAL → FINAL_OK|FINAL_ERR, with reply-file truth for OK, structured errors for empty reply, rate limits, and no second answer bubble.

### 1.3 Success metrics

| Metric | Target |
| --- | --- |
| Time to first meta update | ≤ 2 s after wake start |
| Eternal Thinking… on failure | 0 |
| FINAL_OK source | Reply file only (default) |
| Non-final updates when stream off | Bounded (meta + final) |
| Usability contracts | Still pass |
| Secrets in stream text | 0 under fixtures |

### 1.4 Why ship first (org priority)

Highest trust ROI vs external dependencies: pure operator changes; validates NF-TP-02 T0 in hours–days; unblocks better phone experience immediately.

---

## 2. Assumptions

| Assumption | Note |
| --- | --- |
| `chat.update` remains valid for grok’s own messages on RC 8.6 | Verified today |
| Reply-file + NO_DUPLICATE_POSTS stay sacred | Non-negotiable |
| `streaming-json` schema needs capture (OD-S1) | Blocks T2 only, not T0/T1 |
| Restricted wake uses `--permission-mode auto` | Post-2026-07-10 hotfix |

---

## 3. Design execution summary

```
_process_pending_item:
  post Thinking...
  on_start → update meta (mode, cwd, phase)
  run wake (json | streaming-json)
    [optional] stream events → throttled updates
  read reply file
  if body: FINAL_OK
  else: FINAL_ERR(parse stopReason from log)
  chat.update final (always)
  health.json fields
```

**Flags (defaults production-safe):**

| Flag | Default | Meaning |
| --- | --- | --- |
| `RC_WAKE_STREAM` | `0` | Partials off until T2 stable |
| `RC_STREAM_MIN_INTERVAL_MS` | `800` | Throttle |
| `RC_STREAM_MAX_UPDATES` | `40` | Cap |
| `RC_STREAM_MAX_CHARS` | `3500` | Non-final truncate |
| `RC_STREAM_FALLBACK_TO_STDOUT` | `0` | Prefer structured err |

---

## 4. Phased work breakdown

### Phase T0 — Structured FINAL_ERR (no stream)  
**Effort:** 1–2 d  
**Risk:** Low

| # | Task | Deliverables | Validation (NF-TP-02) |
| --- | --- | --- | --- |
| T0.1 | Pure helper `parse_wake_terminal(log_text) → stopReason, session hints` | `wake_lib.py` or `wake_telemetry.py` | Unit + golden Cancelled fixture |
| T0.2 | Pure helper `format_final_err(rc, stopReason, mode, log_name)` | Same | TP-S-03, E-S-01, E-S-18 |
| T0.3 | Wire into `_process_pending_item` empty-reply branch | `rc_operator_agent.py` | TP-S-04 always finalize |
| T0.4 | Golden fixtures from real/historic wake-run logs | `tests/fixtures/wake-*.json` or text | CI |
| T0.5 | Extend usability failure test expectations if body shape changes | `test_usability_contracts.py` | TP-S-11 |

**Exit:** Empty Cancelled wake shows stopReason in bubble.  
**Rollback:** Revert helper call; restore prior generic string.

---

### Phase T1 — RUNNING_META updates  
**Effort:** 2–3 d  
**Depends on:** T0

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| T1.1 | Bubble state enum / phase constants | Small module or constants in agent | Unit |
| T1.2 | `update_thinking_meta(msgId, phase, **fields)` with Working… chrome | Operator | TP-S-02 |
| T1.3 | Call meta at drain start (before/while wake) with mode, cwd basename, room | `_process_pending_item` | TP-S-01 timing |
| T1.4 | Optional elapsed heartbeat every N s (still rate-limited) | Timer thread or loop | Count bounds TP-S-06 |
| T1.5 | Contract tests: ordered updates placeholder → meta → final | Mock update list | Multi-update sequence |
| T1.6 | `reply_prompt.txt` note: meta may appear; final still reply file | Prompt | Manual read |

**Exit:** No bare Thinking… &gt;2 s after start on healthy path.  
**Rollback:** Skip meta calls via `RC_WAKE_META=0` flag (add if needed).

---

### Phase T2 — Optional streaming-json partials  
**Effort:** 3–5 d  
**Depends on:** T1 + OD-S1 fixture capture

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| T2.0 | Capture real `streaming-json` sample from installed `grok` CLI | Fixture + short schema note in tests/README | OD-S1 close |
| T2.1 | Extend `build_wake_argv` / `_run_wake_once` for stream mode | `wake_lib.py`, agent | Flag off = identical argv to today except documented |
| T2.2 | Line/event parser + rate limiter class | Pure unit-tested | TP-S-07, E-S-throttle |
| T2.3 | Wire stream consumer callbacks to meta/partial updates | Agent | TP-S-08 truncate |
| T2.4 | Finalization: reply file wins over partials | Agent | TP-S-05 |
| T2.5 | Secret/redaction filter on stream text | Filter unit tests | TP-S-09, E-S-secret, AC-S7 |
| T2.6 | Default `RC_WAKE_STREAM=0` in launchd; document enable | Plist / ROCKETCHAT.md | Config review |

**Exit:** With flag=1, partials appear, caps hold, final correct; with flag=0, behavior = T1.  
**Rollback:** `RC_WAKE_STREAM=0` (default).

---

### Phase T3 — Telemetry share-out  
**Effort:** 1–2 d  
**Depends on:** T0; best after NF-IP-03 P0 for `/status`

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| T3.1 | Write `last_stop_reason`, `last_stream_at` to health/state | health.json schema | TP-S-10 |
| T3.2 | Align field names with control-plane `/status` card | Shared constants | Cross-feature |
| T3.3 | Ops doc: how to read wake-run + bubble states | ROCKETCHAT.md snippet | Review |

**Exit:** health.json useful for watchdog and `/status`.

---

## 5. File and integration map

| File | Phases | Change |
| --- | --- | --- |
| `wake/wake_lib.py` | T0–T2 | parse/format helpers; argv output_format |
| `wake/rc_operator_agent.py` | T0–T3 | meta/stream/finalize wiring |
| `wake/reply_prompt.txt` | T1–T2 | Document visibility |
| `wake/rc_config.py` | T1–T2 | Optional centralize stream env |
| `tests/test_usability_contracts.py` | T0–T2 | Multi-update + err body |
| `tests/test_rc_integration.py` | T2 | argv shape if output_format changes |
| launchd operator plist | T2–T3 | Optional env keys |
| `NO_DUPLICATE_POSTS.md` | T1 | Affirm still one bubble |

**Integration contracts:**

- Do not call `chat.postMessage` for final answer  
- `compose_unified_reply` only for FINAL_OK  
- Per-room locks (IMP-10) unchanged  
- Approval mode display in meta must match `resolve_approval_mode` result for that wake  

---

## 6. Dependencies and sequencing

| Other feature | Interaction |
| --- | --- |
| NF-IP-03 | T3 fields feed `/status`; ship T0 before or with P0 |
| NF-IP-01 | Independent; do not block voice on stream |
| Grok CLI upgrade | Re-capture streaming-json fixture |

**Recommended global order:** **T0 → T1 → (control plane P0) → T2 → T3**.

---

## 7. Rollout, flags, rollback

### Launch sequence

1. Deploy T0 behind no flag (safe improvement).  
2. Deploy T1; monitor operator log for update failures.  
3. Deploy T2 code with `RC_WAKE_STREAM=0`.  
4. Enable stream on one machine/session for soak.  
5. Optionally set stream=1 in launchd if stable.

### Rollback

| Phase | Action |
| --- | --- |
| T0–T1 | Revert commit or feature-gate meta/err format |
| T2 | `RC_WAKE_STREAM=0` immediately via kickstart env |
| Bad update storm | Lower max updates / raise interval; or disable meta heartbeat |

**RTO:** flag flip &lt; 5 minutes.

---

## 8. Validation mapping (NF-TP-02)

| Phase | Gate cases |
| --- | --- |
| T0 | TP-S-03,04,05,12; E-S-01,05,18 |
| T1 | TP-S-01,02,06 |
| T2 | TP-S-07,08; E-S-throttle; fixtures |
| T3 | TP-S-10 |
| Always | TP-S-09, TP-S-11 (usability) |

---

## 9. Risks and ops impact

| Risk | Mitigation |
| --- | --- |
| Mobile update thrash | Defaults throttle; stream off |
| Schema drift streaming-json | Fixture + flag |
| Partial looks final | Mandatory Working… chrome tests |
| Secret leak in stream | Redaction + fixtures |
| Finalize race | Finalize only after `proc.wait` |
| Contract test breakage | Update mocks, never delete |

**Ops impact:** Slightly more `chat.update` traffic; richer operator logs; easier incident debug.

---

## 10. Suggested PR stack

| PR | Scope |
| --- | --- |
| PR1 | T0 helpers + fixtures + empty-reply wire + tests |
| PR2 | T1 meta updates + contract multi-update |
| PR3 | T2 stream plumbing default off + redaction |
| PR4 | T3 health fields + docs |

Each PR must keep usability suite green.

---

## 11. Effort summary

| Phase | Eng-days |
| --- | --- |
| T0 | 1–2 |
| T1 | 2–3 |
| T2 | 3–5 |
| T3 | 1–2 |
| **Total** | **~7–12** |

---

## 12. Open decisions

| ID | Decision | Blocks |
| --- | --- | --- |
| OD-S1 | streaming-json event schema | T2.0 |
| OD-S2 | Default stream at GA | T2.6 (keep 0) |
| OD-S3 | Stdout fallback | Leave 0 |
| OD-S5 | Cancel UX | Defer NF-IP-03 `/cancel` |

---

## 13. References

- NF-SPEC-02 state machine, FR-S*, rate limits  
- NF-TP-02 TP-S-* / E-S-*  
- `rc_operator_agent.py`: `update_message`, `_run_wake_once`, `_process_pending_item`  
- `wake_lib.py`: `compose_unified_reply`, `build_wake_argv`, `THINKING_PLACEHOLDER`  
- Incident: 2026-07-10 Cancelled empty reply  
