# Test plan: IMP-23 S5 — In-flight busy chrome + follow-up queue

**Nav:** [Index](../INDEX.md) · [IMP-23 README](./README.md) · [Suggested improvements (S5)](./suggested-improvements.md) · [Implementation](./IMPLEMENTATION.md) · [Impl plan rev2](../../../.hermes/plans/2026-07-17_170815-imp23-s5-inflight-busy-chrome.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-23-S5-TP |
| **Package** | IMP-23 residual **S5** |
| **Status** | **Executed 2026-07-17** (merge gate PASS; S5 Done gate open — L3 not run) |
| **TP revision** | **2** (2026-07-17) — aligned to impl plan rev2 |
| **Primary code** | `ops/rocketchat/wake/wake_inflight_ux.py` (pure) · live `_enqueue_pending` / `_process_pending_item` / `_process_agy_collab_item` in `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` |
| **Primary suite** | `ops/rocketchat/tests/test_wake_inflight_ux_s5.py` |
| **Impl plan** | `.hermes/plans/2026-07-17_170815-imp23-s5-inflight-busy-chrome.md` (rev 2) |

---

## TP revision history

| Rev | Date | Changes |
| --- | --- | --- |
| 1 | 2026-07-17 | Initial S5 test plan |
| **2** | **2026-07-17** | Align to impl rev2: B2 `update_pending`, missing-baseline busy_ack, B5 `retry_of`, `queue_changed`, `apply_decision_to_pending`, required `acked_on_enqueue`, agy parity, clearer merge vs Done gates, L2/L4 operability, fix DoD/fail-criteria contradictions |

### Review findings addressed in rev 2

1. Purpose omitted B2, B5, and double-ack control.  
2. DoD cited I1–I7/I9 only; Pass line and new I9b/I11 disagreed.  
3. “Fail immediately if edit lost” conflicted with L4 soft residual when RC never redelivers edits.  
4. L2 (same mid redelivery) had no practical recipe; made I2 primary proof, L2 opportunistic.  
5. Missing pure cases: empty text still enqueues; retry_of vs processed/in_flight; apply replace paths; `queue_changed` assertions.  
6. Missing I: `acked_on_enqueue` suppresses second 👀; agy process path uses `source_mid`.  
7. Merge gate vs Done gate not separated (PR can land pure-only; Done needs live).  
8. R1/R2 were aspirational without a guaranteed suite — marked optional.  

---

## Purpose

Prove S5 UX and policy:

1. **A** — Same mid redelivery while in-flight → busy ack, **no** second LLM wake.  
2. **B** — Same mid with changed text while in-flight → at most one coalesced `#fu1` follow-up.  
3. **B2** — Same mid with changed text while **pending only** → `update_pending` (in-place text), not drop.  
4. **C** — New mid while room busy → FIFO enqueue + **immediate** 👀 (`acked_on_enqueue`), not only at drain.  
5. **D** — Duplicate pending same mid/same text → idempotent.  
6. **E** — In-flight skip log spam deduped.  
7. **B5** — Empty-reply `retry_of` still requeues **same mid** (no `#fu`, not busy_ack’d away).  
8. **Ack hygiene** — Enqueue-time 👀 does not double-fire at process start.  
9. **Invariants** — Same-room serial; cross-room parallel (no global serial regression).  
10. **Non-goal** — Busy path does not `chat.update` (reactions only).  

Maps to impl plan decision matrix and `suggested-improvements.md` S5 acceptance.

---

## Gates (do not conflate)

| Gate | Required evidence | Blocks |
| --- | --- | --- |
| **Merge (docs PR)** | All **P\*** green; **R0a–R0c** green; docs honest | Merging pure module + tests + docs |
| **Live wire safe** | **I8** once on host; agent starts without import traceback | Kickstart to production |
| **S5 Done (INDEX / IMPLEMENTATION)** | Merge gate + **L1, L3, L5** hard pass; **L2** pass or I2+log note; **L4** pass or residual “no edit stream”; **L6–L8** observed or waived with reason; execution record filled | Claiming S5 complete |

PR **may** merge without full L\* if pure green and residuals listed. Do **not** mark full IMP-23 closed (S3 still open).

---

## Traceability

| Mode | Requirement | Primary tests | Notes |
| --- | --- | --- | --- |
| A | In-flight same text → busy, no second wake | **P5, P5b**, I2, (L2) | L2 opportunistic |
| B | In-flight edit → `#fu1` follow-up | **P6, P7**, I3, I9, (L4) | Needs baseline in `in_flight_texts` |
| B2 | Pending edit → update_pending | **P8b**, I9b | No synthetic mid |
| C | New mid + immediate ack | **P4**, I1, **L3** | L3 is hard live gate |
| D | Dup pending same text | **P8**, I4 | |
| E | Log dedupe | **P10**, I5, L6 | |
| B5 | retry_of same mid | **P15, P15b**, I11 | Must not break S2 |
| Ack | acked_on_enqueue | **I12** | Process path |
| Agy | source_mid / identity | **I13** | Collab process path |
| Serial | same rid FIFO | R2?, **L3** | |
| Parallel | cross-room | R1?, **L5** | Hard live gate |
| No busy update | reactions only | **I6**, L7 | |
| Apply pure | append/replace/cap | **P16–P18** | |

---

## P — Pure unit tests (no live RC)

**Command:**

```bash
cd /Users/velocityworks/IdeaProjects/rocketchat-grok-docs
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py
```

**Load rule:** Prefer mirror `ops/rocketchat/wake/wake_inflight_ux.py` (same pattern as `test_wake_ux_imp23.py`).

**Fixture helper (implement in test file):**

```python
def _subset(**kw):
    base = {"ts": "t0", "file": None, "files": None, "attachments": None, "mentions": None, "u": {"username": "principal"}}
    base.update(kw)
    return base

def _decide(**kw):
    defaults = dict(
        rid="r1", room_name="dm:p", room_type="d", author="principal",
        msg_subset=_subset(), target="grok", collab=False, retry_of=None,
        processed_ids=[], in_flight_ids=[], pending_wakes=[],
        in_flight_texts=None, now_iso="2026-07-17T00:00:00+00:00",
    )
    defaults.update(kw)
    return decide_enqueue(**defaults)
```

| ID | Case | Input (summary) | Expect |
| --- | --- | --- | --- |
| **P1** | `normalize_wake_text` strips / collapses WS | `"  hello   world\n"` | `"hello world"` |
| **P2** | same after normalize | `"hi"` vs `"  hi  "` | `texts_materially_differ` → `False` |
| **P3** | different | `"do A"` vs `"do B"` | `True` |
| **P4** | Fresh mid → enqueue | empty state, text=`hello` | `kind=enqueue`, `queue_changed=True`, `ui_action=ack_start`, `pending_item["mid"]==mid`, `source_mid==mid` |
| **P5** | In-flight same text → busy_ack | `in_flight_ids=[m1]`, `in_flight_texts[m1]=hello`, text=hello | `kind=busy_ack`, `queue_changed=False`, `pending_item is None`, `ui_action=busy` |
| **P5b** | In-flight, baseline **missing** | mid in flight, no `in_flight_texts`, any text | `kind=busy_ack` (never false follow-up) |
| **P6** | In-flight, baseline differs → queue_followup | baseline `do A`, text `do B` | `kind=queue_followup`, `queue_changed=True`, `is_follow_up`, `follow_up_of=m1`, mid=`make_followup_mid(m1,1)`, `ui_action=busy` |
| **P7** | Coalesce second edit | pending has `m1#fu1` text B; new text C; still in-flight | same `#fu1`; text C; apply replaces one row |
| **P8** | Pending same text → busy_ack | mid in pending, same text | `busy_ack`, `queue_changed=False` |
| **P8b** | Pending different text → update_pending | mid pending, new text | `kind=update_pending`, length unchanged, text replaced, `queue_changed=True`, mid **not** `#fu` |
| **P9** | Processed → already_done | mid in processed, no retry_of | `already_done`, no UI, `queue_changed=False` |
| **P10** | Log dedupe TTL | two emits within TTL; one after | True, False, True |
| **P11** | Missing mid → reject | `mid=""` | `reject`, `queue_changed=False` |
| **P11b** | Empty **text** still enqueues | mid set, text `""` | `kind=enqueue` (S5 must not invent empty-text reject; STT/stub is process path) |
| **P12** | Follow-up mid ≠ source | from P6 | `pending_item["mid"] != source_mid` |
| **P13** | Other mid in-flight | inflight `[m0]`, new `m1` | `kind=enqueue` (room serial is drain/lock, not enqueue drop) |
| **P14** | `make_followup_mid` | `(m,1)` stable; `(m,2)` differs | `m#fu1` etc. |
| **P15** | retry_of bypasses processed | `retry_of=m1`, m1 in processed | `enqueue`, mid=`m1` (not `#fu`), `is_empty_reply_retry` / retry fields set, `queue_changed=True` |
| **P15b** | retry_of even if still listed in-flight | `retry_of=m1`, m1 in `in_flight_ids` | still `enqueue` same mid (live clears first; policy must not soft-drop recovery) |
| **P16** | apply no-op | busy_ack decision | pending list equal |
| **P17** | apply append + cap | 30 items + enqueue | len ≤ 30 |
| **P18** | apply replace | update_pending / coalesce follow-up | one row with new text; no duplicate mids |

**Pass:** All P\* green; pure module has no network imports:

```bash
rg -n "urllib|requests|websocket|http.client" ops/rocketchat/wake/wake_inflight_ux.py || true
# expect no matches
```

---

## R — Regression (merge gate)

```bash
python3 ops/rocketchat/tests/test_wake_ux_imp23.py
python3 ops/rocketchat/tests/test_wake_denials_imp22.py
python3 ops/rocketchat/tests/test_multi_round_collab.py
```

| ID | Suite | Expect | Gate |
| --- | --- | --- | --- |
| **R0a** | IMP-23 Wave 1 pure | All pass; **record N/N** | Merge |
| **R0b** | IMP-22 denials | All pass; record N/N | Merge |
| **R0c** | Multi-round collab | All pass; record N/N | Merge |
| **R1** | Cross-room pick (agency usability / wake_lib if available) | Busy head skipped | Optional |
| **R2** | Same-room serial (usability if available) | No overlapping same-rid wakes | Optional |

Optional agency:

```bash
# only if harness present under ~/.grok/agency/ops/rocketchat
python3 tests/test_usability_contracts.py
```

**Pass:** R0\* no FAIL. Optional R1/R2: note skip — do not claim green if not run.

---

## I — Adapter / mock integration (no real RC)

**Goal:** Live wiring without Rocket.Chat. Monkeypatch `schedule_principal_ack`, `schedule_react`, `update_message`, `save_state`, `load_state`, drain spawn.

**Harness:** Agency `tests/` if importable; else skip I\* with reason and rely on L\* for Done gate. **I8 is special:** must run once on live host even without full harness (break import path or rename module briefly / try-import probe).

| ID | Case | Setup | Expect |
| --- | --- | --- | --- |
| **I1** | Enqueue schedules ack_start | `_enqueue_pending` new mid | pending gains row with `acked_on_enqueue=True`; `schedule_principal_ack(mid)` once; returns `True` |
| **I2** | In-flight same → busy | `in_flight_ids=[mid]`, same text | returns `False`; pending length unchanged; `schedule_react` busy once; **no** drain spawn required; no second process |
| **I3** | In-flight edit → follow-up | baseline set + new text | pending has `is_follow_up` + `source_mid`; busy react; returns `True` |
| **I4** | Dup pending same text | mid already pending | no second row; returns `False` |
| **I5** | Log dedupe | 20× same busy path | ≤1 log line per TTL window for that mid/kind (after first) |
| **I6** | No `update_message` on busy/follow-up enqueue | spy | zero calls from `_enqueue_pending` |
| **I7** | Process follow-up acks source | item with `source_mid` + `#fu` mid | process uses `source_mid` for ack when not `acked_on_enqueue` |
| **I8** | Import fallback | `decide_enqueue` unavailable | no crash; legacy enqueue still works |
| **I9** | Coalesce two edits in-flight | sequential edits | exactly one `#fu1`; latest text |
| **I9b** | Pending text update | pending, not in-flight, new text | same mid row updated; no `#fu` |
| **I10** | Second mid drains after first | m1 long mock; m2 enqueue | m2 pending until m1 done then runs |
| **I11** | Empty-reply retry requeue | clear in-flight; `_enqueue_pending(..., retry_of=mid)` | `True`; pending same mid; drain kicked |
| **I12** | `acked_on_enqueue` suppresses process 👀 | pending row flag True | process path does **not** call `schedule_principal_ack` again |
| **I13** | Agy process path | `_process_agy_collab_item` or equivalent with source_mid / flag | ack identity agy/OPERATOR; respects `source_mid` + flag |

**Pass for harness runs:** I1–I7, I9–I13. **I8** required before production kickstart regardless.

---

## L — Live acceptance (Done gate)

**Preconditions:**

1. Merge gate green (P + R0\*).  
2. `wake_inflight_ux.py` on live wake dir.  
3. `rc_operator_agent.py` wire present.  
4. All five operators kickstarted.  
5. `RC_WAKE_MAX_CONCURRENT` not forced to `1`.  
6. `RC_WAKE_REACT` on (default).  

**Ops commands:**

```bash
python3 -c "import sys; sys.path.insert(0, '$HOME/.grok/agency/ops/rocketchat/wake'); import wake_inflight_ux as m; print(m.__file__)"
python3 /Users/velocityworks/IdeaProjects/rocketchat-grok-docs/ops/rocketchat/scripts/rc_wake_digest.py --hours 2
# logs: ~/logs/rocketchat-*-wake/operator-agent.log
```

| ID | Priority | Steps | Pass | Fail / residual |
| --- | --- | --- | --- | --- |
| **L1** | Hard | Long DM tool-ish ask | 👀 + activity bubble + FINAL_OK or FINAL_ERR | Silent forever |
| **L2** | Soft | Prefer: catch natural WS redelivery in logs during L1. Else: accept **I2** as primary + note “no live redelivery observed” | If event seen: one busy react/log; single FINAL; no second bubble for same mid | Double FINAL for same mid = fail |
| **L3** | Hard | During L1, **new** distinct mid same room | Immediate 👀 on second msg; after first FINAL, second wake runs | Second mid never pending/runs = fail |
| **L4** | Soft | Edit first message while running | **If** edit reaches operator: follow-up or pending update; later wake uses new text. **If** no edit event: residual `no_edit_stream` — **not** pure fail, **not** hard Done blocker | Only fail if edit **was** logged as room msg / enqueue decision and then text lost with zero busy signal |
| **L5** | Hard | Long channel wake + simultaneous DM | DM starts without waiting for channel FINAL | DM blocked entire channel wake = fail (global serial regression) |
| **L6** | Observe | ≥10 busy skips if producible | Dedupe visible in logs | Unbounded 1:1 log lines = fail |
| **L7** | Observe | Busy under multi-bot room | No new `update_message` 429 storm from busy chrome | Spike clearly tied to busy path = fail |
| **L8** | Observe | Peer operator (hermes/nie) L3-like | Correct identity reacts; same UX | Peer logs `identity=grok` on react incorrectly = fail |

**Hard fail (any time):**

- New distinct mid dropped entirely (never pending / never runs).  
- `RC_WAKE_MAX_CONCURRENT=1` reintroduced and DMs block on channel.  
- Double LLM finalize for same mid on pure redelivery (A broken).  
- Import crash of operator after deploy.  

**Do not hard-fail S5 on:**

- Kickstart mid-wake stuck bubble (pre-existing S-inflight) — note separately.  
- L4 when no edit stream.  
- L2 when no redelivery observed if I2 green.  

---

## Negative / edge cases

| ID | Case | Expect | Layer |
| --- | --- | --- | --- |
| **E1** | Empty text + attachment-only mid | Enqueue allowed at policy layer (P11b); process STT/stub unchanged | P / live optional |
| **E2** | Follow-up after source mid processed | Synthetic `#fu1` still runnable (not filtered by source processed) | P / I |
| **E3** | `RC_WAKE_REACT=0` | No crash; queue decisions still apply; UI no-ops | I / L optional |
| **E4** | Unknown busy emoji | Fallback `eyes` or no throw | I / L optional |
| **E5** | Pending cap 30 | apply respects cap (P17); coalesce preferred over growth | P |
| **E6** | Whitespace-only text change | normalize → same → busy_ack not follow-up | P2 + P5 |
| **E7** | retry_of must not create `#fu` | P15 | P |

---

## Security / hygiene

| ID | Check | Expect |
| --- | --- | --- |
| **S1** | `log_line` content | No auth tokens / env secrets |
| **S2** | Test fixtures | No real credentials |
| **S3** | Call/voice | No test enables `RC_CALL_ENABLED` or public voice |

---

## Execution record template

Copy into `IMPLEMENTATION.md` when running:

```markdown
### S5 test execution record (TP rev 2)

| Date | Agent | Layer | Result | Notes |
| --- | --- | --- | --- | --- |
| YYYY-MM-DD | | P | PASS/FAIL | N/N |
| | | R0a–c | | counts |
| | | I | | harness? I8? |
| | | L1 | | |
| | | L2 | | pass / I2-only |
| | | L3 | | hard |
| | | L4 | | pass / no_edit_stream |
| | | L5 | | hard |
| | | L6–L8 | | |

Commands:
- …
Log greps:
- decision kinds: enqueue|busy_ack|queue_followup|update_pending|already_done
- `acked_on_enqueue` / react lines
- legacy `enqueue skip in-flight` should decline after deploy
Digest:
- `rc_wake_digest.py --hours …`
Residuals:
- …
```

---

## Definition of done

### Merge (docs PR)

- [ ] All **P1–P18** (incl. P5b, P8b, P11b, P15b) implemented and green  
- [ ] **R0a–R0c** green (counts recorded)  
- [ ] Impl + this test plan linked; no secret fixtures  
- [ ] INDEX/suggested-improvements do not claim full IMP-23 closed  

### Live wire

- [ ] **I8** verified on principal Mac  
- [ ] Operators kickstarted; module import path prints live file  

### S5 Done

- [ ] Merge + live wire  
- [ ] **L1, L3, L5** hard pass  
- [ ] **L2** pass or documented I2-primary  
- [ ] **L4** pass or residual `no_edit_stream`  
- [ ] **L6–L8** observed or waived with reason  
- [ ] **I12** green if harness; else manual confirm single 👀 on queued mid  
- [ ] Execution record filled in IMPLEMENTATION.md  
- [ ] S5 status honest in suggested-improvements.md  

---

## Out of scope

- S3 agy FINAL_ERR rate targets  
- S1/S4 full 429 budget acceptance  
- S10 phase-chrome heartbeat  
- S6 double-seen subscription dedupe (except collision with P8)  
- New DDP edit subscription implementation (residual only if L4 shows no stream)  
- Voice/Call NF-01  

---

## Related commands

```bash
# Pure S5
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py

# Regression
python3 ops/rocketchat/tests/test_wake_ux_imp23.py
python3 ops/rocketchat/tests/test_wake_denials_imp22.py
python3 ops/rocketchat/tests/test_multi_round_collab.py

# Digest
python3 ops/rocketchat/scripts/rc_wake_digest.py --hours 24

# Live module present
python3 -c "import sys; sys.path.insert(0, '$HOME/.grok/agency/ops/rocketchat/wake'); import wake_inflight_ux as m; print(m.__file__)"
```
