# Operator inflight UX hooks (IMP-23 S5)

**Live file:** `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py`  
**Pure policy (mirrored):** `ops/rocketchat/wake/wake_inflight_ux.py`  
**Tests:** `ops/rocketchat/tests/test_wake_inflight_ux_s5.py`

This excerpt documents the live wire so PRs can review agency-only changes without dumping the full agent.

---

## Import (lazy; safe fallback)

```python
try:
    from wake_inflight_ux import (
        decide_enqueue,
        apply_decision_to_pending,
        should_emit_decision_log,
        normalize_wake_text,
    )
except ImportError:
    decide_enqueue = None
    apply_decision_to_pending = None
    should_emit_decision_log = None
    normalize_wake_text = None
```

If import fails, `_enqueue_pending` keeps **legacy** silent-skip behavior.

---

## `_enqueue_pending` (S5 path)

1. Build `msg_subset` (ts/file/files/attachments/mentions/u).
2. `decision = decide_enqueue(...)` with state: processed, in_flight, pending, `in_flight_texts`.
3. `pending = apply_decision_to_pending(...)`.
4. On `queue_changed` + `ack_start`: set `acked_on_enqueue=True` on the new row.
5. Log via `should_emit_decision_log` (TTL `RC_INFLIGHT_LOG_TTL_S`, default 60).
6. UI:
   - `ack_start` → `schedule_principal_ack(source_mid, identity=OPERATOR|target)`
   - `busy` → `_schedule_busy_react` (`RC_WAKE_REACT_BUSY` default `repeat`, fallback `eyes`)
7. Stash `_LAST_ENQUEUE_KIND[mid] = decision.kind` for honest caller skip logs.
8. Return `bool(decision.queue_changed)`.

Callers on False use `_log_enqueue_skip(mid)` → `enqueue skipped mid=… kind=busy_ack` (never “already processed” for busy).

---

## Process path

### Grok `_process_pending_item`

- `_set_in_flight(mid, active=True, text=caption)` → fills `in_flight_texts`
- Ack: `ack_mid = source_mid or mid` only if `not acked_on_enqueue` and not empty-reply retry
- Identity: `OPERATOR` (not hardcoded grok on peers)

### Agy `_process_agy_collab_item`

- Same in-flight claim/clear + `source_mid` / `acked_on_enqueue` ack

---

## State keys

| Key | Role |
| --- | --- |
| `in_flight_ids` | mids currently waking |
| `in_flight_texts` | mid → normalized text at claim (edit baseline) |
| `enqueue_log_dedupe` | `"mid|kind"` → epoch |
| pending item `acked_on_enqueue` | suppress double 👀 |
| pending item `is_follow_up` / `follow_up_of` / `source_mid` | edit follow-up |

---

## Deploy

```bash
cp ops/rocketchat/wake/wake_inflight_ux.py ~/.grok/agency/ops/rocketchat/wake/
# ensure live rc_operator_agent.py has this wire
# kickstart all five rocketchat-*-operator LaunchAgents
```

## Verify

```bash
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py  # 22/22
python3 -c "import sys; sys.path.insert(0,'$HOME/.grok/agency/ops/rocketchat/wake'); import wake_inflight_ux as m; print(m.__file__)"
# logs: enqueue busy_ack / queue_followup / update_pending / enqueue skipped mid=… kind=
```
