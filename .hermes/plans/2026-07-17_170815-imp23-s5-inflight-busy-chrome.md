# IMP-23 S5 — In-flight busy chrome + follow-up queue Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Follow global-code-style 4-phase authoring for every production code module (scaffold → review → one-function + tests + commit → checklist). Plan-only until user asks to implement.

**Goal:** Never silently drop a principal (or peer) ping while a wake is running: surface busy state, acknowledge queue, and run distinct follow-ups after the current wake finalizes.

**Architecture:** Extract pure, unit-testable enqueue policy into `wake_inflight_ux.py` (IMP-22/23 pattern). Live `_enqueue_pending` is a thin adapter: load state → pure `decide_enqueue` → pure `apply_decision_to_pending` → save → cheap UI (reactions only). Room serial / cross-room parallel stay on existing drain + locks (`RC_WAKE_MAX_CONCURRENT` default **16**). No Call/voice. No busy-path `chat.update`.

**Tech Stack:** Python 3 stdlib pure policy; live REST via existing `schedule_react` / `schedule_principal_ack`; state JSON; docs mirror `ops/rocketchat/`; live `~/.grok/agency/ops/rocketchat/`.

**Test plan (authoritative cases):** [`docs/improvements/23-wake-ux-log-deep-dive-2026-07-16/test-plan-s5.md`](../../docs/improvements/23-wake-ux-log-deep-dive-2026-07-16/test-plan-s5.md) — IDs **P\***, **R\***, **I\***, **L\***.

**Evidence:** IMP-23 S5 (308× grok `enqueue skip in-flight`); live `_enqueue_pending` ~`rc_operator_agent.py:2198-2254`.

---

## Revision history

| Rev | Date | Why |
| --- | --- | --- |
| 1 | 2026-07-17 | Initial plan from S5 recommendation |
| **2** | **2026-07-17** | Review pass — see below |

### Rev 2 review findings (addressed in this document)

1. **Pending-not-started edits were missing.** Same mid already in `pending_wakes` (not yet in-flight) with **new text** was only “busy_ack” → text loss. **Fix:** `kind=update_pending` replaces pending row text in place (no synthetic mid).
2. **Empty-reply retry semantics locked to live code.** Recovery (~3052–3098) clears in-flight, does **not** mark processed, requeues **same mid** with `retry_of=mid`. Pure policy: `retry_of` set → always `enqueue` same mid (bypass busy_ack / already_done); never invent a different mid for B5.
3. **Adapter mutation must be pure-tested.** Added `apply_decision_to_pending` so append/replace/coalesce is not live-only.
4. **Caller log lies.** `already queued/processed mid=` on every `False` is wrong for `busy_ack`. Adapter returns richer result or callers log `decision.kind`.
5. **`acked_on_enqueue` is required**, not optional — enqueue-time 👀 + process-time 👀 would double-react.
6. **Agy path parity.** `_process_agy_collab_item` also acks; must use `source_mid` + `acked_on_enqueue` + `OPERATOR`/`COLLAB_AGY` identity.
7. **RC edit delivery is a residual risk.** `stream-room-messages` `changed` may not re-deliver principal edits for the same mid. Wave 1 still implements policy; **L4** may fail if stream never re-enters `handle_principal_message` — document, do not block pure suite. Optional residual: listen for edit events (out of S5 Wave 1).
8. **Cross-link test plan** P/I/L IDs into tasks.
9. **Busy emoji** resolved live-only (`RC_WAKE_REACT_BUSY`, default `repeat`, fallback `eyes`) — do **not** require wake_lib API change in Wave 1 (keeps mirror small).
10. **State keys** documented: `in_flight_texts`, `enqueue_log_dedupe`.
11. **Return value for coalesce:** `update_pending` / follow-up text replace → return `True` if text changed (so a stalled drain can be re-kicked); `busy_ack` same text → `False`.

---

## Current context / root cause (do not re-discover)

### Today (`_enqueue_pending`)

1. No mid → False  
2. mid in `processed_ids` → False  
3. mid in `in_flight_ids` → log `enqueue skip in-flight mid=…` → False (**silent UX**)  
4. mid already in `pending_wakes` → False  
5. Else append pending → True  

In-flight claimed at **start** of `_process_pending_item` (~2515).  
👀 `schedule_principal_ack` at **process** start (~2607 grok / ~2410 agy), **not** at enqueue → queued second mids look dead until drain.

### Failure modes

| # | Scenario | Today | Desired |
| --- | --- | --- | --- |
| A | Same mid redelivery while in-flight | Silent skip + log spam | `busy_ack` + 🔁 once; no second wake |
| B | Same mid **edit** while in-flight | Text discarded | `queue_followup` (synthetic mid); busy react |
| B2 | Same mid **edit** while pending only | Text discarded | `update_pending` replace text; busy or ack as appropriate |
| C | New mid while room busy | Enqueues OK; no 👀 until drain | `enqueue` + immediate 👀 (`acked_on_enqueue`) |
| D | Duplicate pending same mid same text | Silent False | `busy_ack` idempotent |
| E | Log spam | Hundreds of lines | Dedupe per mid/kind TTL |

### Empty-reply retry (do not break B5 / IMP-23 S2)

Live path:

- `_set_in_flight(mid, False)`  
- **does not** `_mark_processed`  
- `_enqueue_pending(..., retry_of=str(mid))` with **same** `_id`  
- on success: interim bubble update + drain thread  

Pure decision when `retry_of` is truthy:

- `kind=enqueue`  
- `pending_item.mid == mid` (source mid, not `#fu`)  
- `is_empty_reply_retry=True`  
- Ignore in-flight/processed busy short-circuits that would drop recovery (in-flight already cleared; if still listed, still allow enqueue for retry_of).

### Non-goals

- S10 phase-chrome heartbeats / busy `chat.update`  
- S1/S4 full host 429 redesign  
- S3 agy FINAL_ERR deep fix  
- Call/voice  
- Global serial drain  
- New DDP edit subscription (unless already trivial; residual only)

### Invariants

- Same room: serial (per-room lock)  
- Cross-room: parallel up to cap (default 16)  
- No double LLM wake for same in-flight mid (same text)  
- 👀 may remain after FINAL (existing contract)  
- `processed_ids` only after a real wake attempt completes (retry path exception already live)  
- Mirror pure + tests in docs repo; full agent stays agency-live  

---

## Proposed approach

### Pure module

| Path | Role |
| --- | --- |
| `ops/rocketchat/wake/wake_inflight_ux.py` | Create (docs mirror) |
| `~/.grok/agency/ops/rocketchat/wake/wake_inflight_ux.py` | Deploy copy |
| `ops/rocketchat/tests/test_wake_inflight_ux_s5.py` | Pure suite → test-plan **P\*** |

```python
# Decision kinds
# - "enqueue"         → append new pending row; ui=ack_start
# - "update_pending"  → replace text on existing pending mid; ui=busy (or ack_start if never acked)
# - "busy_ack"        → no queue change; ui=busy
# - "queue_followup"  → append/replace synthetic follow-up row; ui=busy
# - "already_done"    → mid processed; no ui
# - "reject"          → missing mid

@dataclass(frozen=True)
class EnqueueDecision:
    kind: str
    log_line: str
    ui_action: str | None          # "ack_start" | "busy" | None
    pending_item: dict | None      # row to append or use as replace template
    replace_mid: str | None        # if set, adapter replaces pending row with this mid
    source_mid: str
    follow_up_of: str | None
    queue_changed: bool            # True → adapter should return True (kick drain)

def normalize_wake_text(text: str | None) -> str: ...
def texts_materially_differ(a: str | None, b: str | None) -> bool: ...
def make_followup_mid(source_mid: str, seq: int = 1) -> str:
    return f"{source_mid}#fu{seq}"

def decide_enqueue(
    *,
    mid: str,
    rid: str,
    room_name: str,
    room_type: str | None,
    text: str | None,
    author: str,
    msg_subset: dict,
    target: str,
    collab: bool,
    retry_of: str | None,
    processed_ids: list,
    in_flight_ids: list,
    pending_wakes: list,
    in_flight_texts: dict[str, str] | None = None,
    now_iso: str | None = None,
) -> EnqueueDecision: ...

def apply_decision_to_pending(
    pending: list,
    decision: EnqueueDecision,
    *,
    max_pending: int = 30,
) -> list:
    """Return new pending list: append, replace-by-mid, or no-op. Pure."""

def should_emit_decision_log(
    *,
    last_logged: dict[str, float],
    mid: str,
    kind: str,
    now: float,
    ttl_s: float = 60.0,
) -> tuple[bool, dict[str, float]]: ...
```

### Decision matrix (implement exactly)

| Condition | kind | queue_changed | ui |
| --- | --- | --- | --- |
| not mid | reject | F | — |
| `retry_of` set | enqueue (same mid, retry flags) | T | ack_start |
| mid in processed (no retry) | already_done | F | — |
| mid in in_flight, text **same** (or baseline missing → treat same) | busy_ack | F | busy |
| mid in in_flight, text **differs** | queue_followup (`#fu1`, coalesce if exists) | T | busy |
| mid in pending, text **same** | busy_ack | F | busy |
| mid in pending, text **differs** | update_pending (replace that row’s text/fields) | T | busy |
| else | enqueue | T | ack_start |

**Baseline text for in-flight compare:** `in_flight_texts.get(mid)` else pending row text if any else `""` (missing baseline + any new text → if in_flight, prefer **busy_ack** not follow-up when baseline missing — safer against false follow-ups on first redelivery). Rev2 rule:

- If in-flight and baseline **missing** → **busy_ack** (do not invent follow-up).  
- If in-flight and baseline present and differs → **queue_followup**.

### Follow-up row shape

```python
{
  "mid": make_followup_mid(source_mid, 1),  # always seq=1; coalesce by replace
  "source_mid": source_mid,
  "rid": rid, "room_name": room_name, "room_type": room_type,
  "ts": msg_subset.get("ts"),
  "text": new_text,
  "file": ..., "files": ..., "attachments": ..., "mentions": ...,
  "u": ..., "author": author,
  "target": target, "collab": collab,
  "enqueued_at": now_iso,
  "is_empty_reply_retry": False,
  "retry_of": None,
  "is_follow_up": True,
  "follow_up_of": source_mid,
  "acked_on_enqueue": False,  # busy react on source; process may ack source once
}
```

Normal enqueue row: set `acked_on_enqueue=True` when adapter fires ack_start.

### State keys (per operator state.json)

| Key | Type | Purpose |
| --- | --- | --- |
| `in_flight_texts` | `dict[str,str]` | mid → normalized text at process claim |
| `enqueue_log_dedupe` | `dict[str,float]` | `"mid|kind"` → epoch for log TTL |

Clear `in_flight_texts[mid]` whenever in-flight cleared / processed.

### UI (live only, reactions only)

| ui_action | Call |
| --- | --- |
| ack_start | `schedule_principal_ack(source_mid, identity=OPERATOR or target)` |
| busy | `schedule_react(source_mid, busy_emoji, identity=...)` with `busy_emoji = env RC_WAKE_REACT_BUSY or "repeat"`; on failure optional fallback `"eyes"` |

No `update_message` from enqueue adapter.

### Live adapter (`_enqueue_pending`)

```python
def _enqueue_pending(...) -> bool:
    mid = msg.get("_id")
    ...
    if decide_enqueue is None:
        return _enqueue_pending_legacy(...)  # keep current body as nested fallback

    state = load_state()
    decision = decide_enqueue(
        mid=str(mid),
        rid=rid,
        room_name=room_name,
        room_type=room_type,
        text=(msg.get("msg") or "").strip(),
        author=...,
        msg_subset={...},  # same fields as today
        target=target,
        collab=collab,
        retry_of=retry_of,
        processed_ids=list(state.get("processed_ids") or []),
        in_flight_ids=list(state.get("in_flight_ids") or []),
        pending_wakes=list(state.get("pending_wakes") or []),
        in_flight_texts=dict(state.get("in_flight_texts") or {}),
        now_iso=datetime.now(timezone.utc).isoformat(),
    )
    pending = apply_decision_to_pending(
        list(state.get("pending_wakes") or []), decision, max_pending=30
    )
    if decision.queue_changed:
        # mark acked_on_enqueue on new/updated row when ui is ack_start
        ...
        state["pending_wakes"] = pending
    # log dedupe
    emit, dedupe = should_emit_decision_log(
        last_logged=dict(state.get("enqueue_log_dedupe") or {}),
        mid=str(mid), kind=decision.kind, now=time.time(),
        ttl_s=float(os.environ.get("RC_INFLIGHT_LOG_TTL_S") or 60),
    )
    state["enqueue_log_dedupe"] = dedupe
    save_state(state)
    if emit:
        log(decision.log_line)
    # UI
    if decision.ui_action == "ack_start":
        schedule_principal_ack(decision.source_mid, identity=ident)
    elif decision.ui_action == "busy":
        schedule_react(decision.source_mid, busy_emoji, identity=ident)
    return bool(decision.queue_changed)
```

**Caller logging:** replace bare `already queued/processed` with decision-aware log when possible; at minimum do not claim “processed” on busy_ack.

### Process path changes

1. `ack_mid = item.get("source_mid") or item.get("mid")`  
2. Ack only if `not item.get("acked_on_enqueue")`  
3. Identity: `OPERATOR` / collab target — **not** hardcoded `COLLAB_GROK` on peer bots (fix grok process path that hardcodes COLLAB_GROK at ~2607 while wiring S5).  
4. On in-flight claim: set `in_flight_texts[mid] = normalize_wake_text(caption)`  
5. On clear: pop `in_flight_texts[mid]`  
6. Same for `_process_agy_collab_item`

### Env

| Env | Default | Meaning |
| --- | --- | --- |
| `RC_WAKE_REACT_BUSY` | `repeat` | Busy reaction shortname |
| `RC_INFLIGHT_LOG_TTL_S` | `60` | Log dedupe TTL |
| `RC_FOLLOWUP_MAX_PER_SOURCE` | `1` | Document only (seq always 1) |

---

## Files to change

| Path | Role |
| --- | --- |
| `ops/rocketchat/wake/wake_inflight_ux.py` | Pure policy |
| `ops/rocketchat/tests/test_wake_inflight_ux_s5.py` | Pure tests (P\*) |
| live `wake/wake_inflight_ux.py` | Deploy copy |
| live `wake/rc_operator_agent.py` | Adapter + process ack + in_flight_texts + agy parity |
| `ops/rocketchat/README.md` | Module row |
| `docs/improvements/23-.../IMPLEMENTATION.md` | S5 section + live proof |
| `docs/improvements/23-.../suggested-improvements.md` | S5 status |
| `docs/improvements/23-.../test-plan-s5.md` | Already exists — fill execution record when run |
| `docs/improvements/INDEX.md` | Residual note |
| Optional `ops/rocketchat/wake/OPERATOR_INFLIGHT_HOOKS.md` | Live wire excerpt for PR |

---

## Tasks (TDD; map to test-plan IDs)

### Task 0: Branch + baseline

```bash
cd /Users/velocityworks/IdeaProjects/rocketchat-agents
git checkout main && git pull origin main
git checkout -b feat/imp-23-s5-inflight-busy-chrome
python3 ops/rocketchat/tests/test_wake_ux_imp23.py
python3 ops/rocketchat/tests/test_wake_denials_imp22.py
python3 ops/rocketchat/tests/test_multi_round_collab.py
```

Record actual pass counts (do not assume 16/6/17). **R0\***.

---

### Task 1: Scaffold pure module (Phase 1)

Create `ops/rocketchat/wake/wake_inflight_ux.py`: signatures + comment logic only for every branch in the decision matrix (including B2 `update_pending`, retry_of, missing baseline → busy_ack).

Commit: `scaffold(imp-23-s5): pure inflight enqueue decision API`

---

### Task 2: P1–P3 text helpers

Tests then implement `normalize_wake_text`, `texts_materially_differ`.

```bash
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py
```

Commit: `feat(imp-23-s5): text normalize + material differ`

---

### Task 3: P14 `make_followup_mid`

`f"{source}#fu{seq}"` — default seq 1 for production coalesce.

Commit: `feat(imp-23-s5): follow-up mid helper`

---

### Task 4: P4 enqueue fresh mid

`kind=enqueue`, `queue_changed=True`, `ui_action=ack_start`, `acked` flag left for adapter.

---

### Task 5: P5 / A — in-flight same text → busy_ack

Also: baseline **missing** + in-flight → busy_ack (no false follow-up).

---

### Task 6: P6 / B — in-flight different text → queue_followup

`mid == source#fu1`, `is_follow_up`, `queue_changed=True`.

---

### Task 7: P7 coalesce follow-up

Second edit → same `#fu1`, new text; `apply_decision_to_pending` replaces by mid.

---

### Task 8: P8 pending same text → busy_ack

---

### Task 8b: **P-new / B2** pending different text → update_pending

**Rev2 addition.** Assert pending list length unchanged; text updated; `queue_changed=True`.

---

### Task 9: P9 already_done + P15 retry_of

- processed → already_done  
- `retry_of="m1"` even if m1 processed → enqueue same mid with retry flags (match live)

---

### Task 10: P10 log dedupe + P11 reject + P12 follow-up mid ≠ source + P13 other mid in-flight still enqueues

---

### Task 10b: `apply_decision_to_pending` pure tests

- append on enqueue  
- replace on update_pending / coalesce  
- no-op on busy_ack  
- cap 30  

---

### Task 11: Phase 2 review gate

Checklist:

- [ ] Decision matrix complete (incl. B2, missing baseline, retry_of)  
- [ ] P13: other in-flight mid does not block new mid  
- [ ] No network imports  
- [ ] All pure tests green  
- [ ] Test-plan P\* coverage mapped  

---

### Task 12: Live wire `_enqueue_pending`

Copy module to agency; lazy import; fallback legacy; implement adapter sketch; identity=`OPERATOR` or call `target`.

Static verify:

```bash
python3 -c "import ast; ast.parse(open('$HOME/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py').read())"
python3 -c "import sys; sys.path.insert(0,'$HOME/.grok/agency/ops/rocketchat/wake'); import wake_inflight_ux as m; print(m.make_followup_mid('x',1))"
```

**I1, I2, I4, I5, I6, I8** when harness available.

---

### Task 13: Process path — in_flight_texts, source_mid ack, acked_on_enqueue

Both grok `_process_pending_item` and `_process_agy_collab_item`.

**I3, I7, I9, I10.**

---

### Task 14: Caller log honesty

Sites ~4035, ~4118, ~4222: on False, log `enqueue decision busy_ack|already_done|… mid=` if available (adapter can set last decision thread-local **or** simply improve message to “enqueue skipped mid= (busy or duplicate)” without claiming processed).

---

### Task 15: Full pure + regression

```bash
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py
python3 ops/rocketchat/tests/test_wake_ux_imp23.py
python3 ops/rocketchat/tests/test_wake_denials_imp22.py
python3 ops/rocketchat/tests/test_multi_round_collab.py
```

---

### Task 16: Docs

Update IMPLEMENTATION.md S5, suggested-improvements S5 status, README table, INDEX residual. Reference test-plan execution record template.

---

### Task 17: Deploy + kickstart five operators

Agency skill kickstart list. Confirm import path + no traceback on start.

---

### Task 18: Live acceptance = test-plan **L1–L8**

| L | Action | Pass |
| --- | --- | --- |
| L1 | Long DM wake | 👀 + bubble + FINAL\* |
| L2 | Same-mid redelivery / in-flight skip | busy react or single log; one FINAL |
| L3 | New mid same room while busy | 👀 immediately; runs after first |
| L4 | Edit while running | **If** stream redelivers edit → follow-up; **if not**, record residual “no edit event” (not pure fail) |
| L5 | Channel + DM parallel | DM not blocked |
| L6 | Spam skips | deduped logs |
| L7 | No busy-driven update 429 storm | reactions only |
| L8 | Peer operator | identity correct |

L4 soft-gate: policy green even if RC never delivers edits.

---

### Task 19: PR

Mirror + docs + honesty about live-only agent wire. Self-PR COMMENT not REQUEST_CHANGES.

---

### Task 20: Phase 4 checklist

- [ ] Pure no I/O  
- [ ] Import fallback safe (**I8**)  
- [ ] OPERATOR identity on peer reacts  
- [ ] No global serial  
- [ ] retry_of still works (force empty-reply or unit)  
- [ ] acked_on_enqueue prevents double 👀  
- [ ] B2 pending text update covered  
- [ ] Call/voice untouched  
- [ ] Test-plan execution record filled  
- [ ] Do not close full IMP-23 (S3 still open)  

---

## Risks (updated)

| Risk | Mitigation |
| --- | --- |
| RC never re-sends edits | L4 residual; B2 still helps if anything re-enqueues same mid with new text |
| False follow-up without baseline | Missing baseline → busy_ack only |
| Double 👀 | Required `acked_on_enqueue` |
| B5 retry broken | Explicit retry_of row in matrix + P15 |
| Coalesce race | Single replace-by-mid; seq always 1 |
| Return False skips needed drain | queue_changed True on any mutation; workers re-drain on finish |
| Live agent not in git | Hooks excerpt + IMPLEMENTATION |
| Scope creep S10 | Forbidden busy chat.update |

---

## Acceptance (definition of done)

1. Pure suite covers decision matrix + `apply_decision_to_pending` — green.  
2. Regression R0\* green.  
3. Live L1–L3, L5 pass after kickstart.  
4. L2 no silent black hole.  
5. L4 pass **or** documented “no edit stream” residual.  
6. No cross-room serial regression.  
7. Docs + test-plan execution record updated; PR opened.  
8. IMP-23 **not** marked fully closed (S3 residual remains).  

---

## Commit sequence (summary)

1. scaffold pure API  
2. text helpers + follow-up mid  
3. decide_enqueue matrix (incl. update_pending + retry)  
4. apply_decision_to_pending  
5. log dedupe  
6. pure suite complete  
7. docs  
8. live wire + kickstart (agency)  

---

## Execution handoff

Load: `global-code-style`, `test-driven-development`, `rocketchat-agency-ops`, `subagent-driven-development` (optional), `github-pr-workflow` / `github-api-fallbacks`.

**Authoritative test cases:** `docs/improvements/23-wake-ux-log-deep-dive-2026-07-16/test-plan-s5.md`  
**This plan (rev 2):** `.hermes/plans/2026-07-17_170815-imp23-s5-inflight-busy-chrome.md`

Ready to implement when asked — dispatch task-by-task with two-stage review.
