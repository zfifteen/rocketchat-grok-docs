# B2 and B7: Epoch Expiry and Pile-up Prevention Spec

## B2: Stale Epoch Re-arm (Stamping Old Epochs)
**Problem**: Solo peer work (e.g., a direct `@hermes` mention without a lead assigning them in the current epoch) can end up stamping a stale epoch because `record_assignee_delivered` blindly adds the peer to `delivered` even if `lead_done` is true or if the peer wasn't explicitly assigned. This makes the state dirty and can cause re-arming of hops.

**Patch Design (`record_assignee_delivered`)**:
Add a hard gate inside `_mut` in `rc_multi_round_collab.py` so that we only update the delivered map if the room has an active epoch and the assignee is explicitly in the assignees list.

```python
    def _mut(st: dict[str, Any]) -> None:
        rooms = st.setdefault("rooms", {})
        rid = str(room_id)
        entry = dict(rooms.get(rid) or {})
        
        # HARD GATE (B2): do not stamp if lead_done is true (closed epoch)
        if entry.get("lead_done"):
            return
            
        # HARD GATE (B2): do not stamp if peer is not an assignee of the active epoch
        assignees = entry.get("assignees") or []
        if who not in assignees:
            return

        delivered = dict(entry.get("delivered") or {})
        delivered[who] = {"mid": mid or "", "ts": ts}
        entry["delivered"] = delivered
        rooms[rid] = entry
```

## B7: Pile-up after DONE / Dense Returns
**Problem**: `should_emit_return_notify` acts as the primary gate for `collab-return`. While B1 restricted the assigner to be a bot, a second belt is needed. We should only emit a `collab-return` if the completing operator is actually an assignee of an open epoch.

**Patch Design (`should_emit_return_notify`)**:
Pass `room_id` and `path` down to `should_emit_return_notify`. 

```python
def should_emit_return_notify(
    *,
    operator: str,
    assigner: str | None,
    room_type: str | None,
    lead_done: bool,
    room_id: str | None = None,
    path: Path | None = None,
    # ...
) -> bool:
    # ... existing checks ...
    
    # SECOND BELT (B7): Only return-notify if the operator is an assignee in an active epoch
    if room_id:
        st = load_shared_state(path=path, env=env)
        rooms = st.get("rooms") or {}
        entry = rooms.get(str(room_id)) or {}
        assignees = entry.get("assignees") or []
        if operator not in assignees:
            return False

    # ... remaining checks ...
```

This ensures that solo asks (like `@agy fix this`) do not automatically re-wake `@grok` when completed, preventing pile-ups and isolating direct peer queries.

## Acceptance Test Plan

1. **Test `record_assignee_delivered_stale_epoch`**:
   - Call `mark_lead_done(room_id)`.
   - Call `record_assignee_delivered(room_id, "agy")`.
   - Assert `delivered` is still empty.
   
2. **Test `record_assignee_delivered_unassigned_peer`**:
   - Open a collab epoch with assignees `["hermes"]`.
   - Call `record_assignee_delivered(room_id, "agy")`.
   - Assert `delivered` for "agy" is not present (only "hermes" could deliver).

3. **Test `should_emit_return_notify_second_belt`**:
   - Open a collab epoch with assignees `["hermes"]`.
   - Invoke `should_emit_return_notify` for operator `"agy"`, assigner `"grok"`, with `lead_done=False`.
   - Assert it returns `False` (agy is not in assignees).
   - Invoke `should_emit_return_notify` for operator `"hermes"`, assigner `"grok"`, with `lead_done=False`.
   - Assert it returns `True`.
