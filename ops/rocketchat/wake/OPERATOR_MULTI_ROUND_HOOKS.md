# rc_operator_agent.py — multi-round hooks (issue #2)

Canonical path: `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py`

This file is a **review excerpt** of the wired hooks; the full agent remains runtime-only.

## Import

```python
from rc_multi_round_collab import (
    multi_round_enabled,
    playbook_inject_block,
    resolve_return_notify_target,
    should_emit_return_notify,
    build_return_notify_text,
    reply_declares_lead_done,
    message_is_collab_return,
    room_lead_done,
    mark_lead_done,
    maybe_clear_lead_done_on_new_work,
    should_skip_lead_llm_on_collab_return,
    should_skip_lead_llm_on_peer_closeout_ack,
    principal_multi_mention_lead_only,
    extract_peer_assignees_from_text,
    open_collab_epoch,
    record_assignee_delivered,
    room_epoch,
    summary_from_reply,
    GROK_LEAD as MR_GROK_LEAD,
    COLLAB_RETURN_MARKER,
)
```

## `_maybe_multi_round_after_wake`

```python
def _maybe_multi_round_after_wake(
    *,
    rid: str,
    room_name: str,
    room_type: str | None,
    mid: str | None,
    author: str,
    trigger_text: str,
    reply_body: str,
    phase: str,
    rc: int,
) -> None:
    """
    After a normal LLM wake finalizes:

    - If this process is lead (grok) and reply declares plain-language DONE → mark room.
    - If this process is a peer and return-notify is allowed → post @assigner|@grok
      so the next hop runs without principal re-tagging (cross-process via tag-to-talk).
    """
    if not multi_round_enabled():
        return
    if not rid:
        return
    op = (OPERATOR or "").strip().lower() or "grok"
    # Lead DONE (plain language) — suppress future automatic return-notify in this room.
    if op == MR_GROK_LEAD and reply_declares_lead_done(reply_body):
        mark_lead_done(
            rid,
            at=datetime.now(timezone.utc).isoformat(),
            mid=mid,
        )
        log(f"multi-round lead DONE marked room={room_name or rid} mid={mid}")
        return

    # Lead kickoff: open a collab epoch when the lead assigns ≥1 peer with @tags.
    if op == MR_GROK_LEAD and not message_is_collab_return(trigger_text):
        peers = extract_peer_assignees_from_text(reply_body)
        if peers:
            try:
                ep = open_collab_epoch(
                    rid,
                    assignees=peers,
                    opened_by=op,
                    mid=mid,
                )
                log(
                    f"multi-round epoch opened epoch={ep} assignees={peers} "
                    f"room={room_name or rid} mid={mid}"
                )
            except Exception as e:
                log(f"multi-round open epoch failed mid={mid}: {e}")

    lead_done = room_lead_done(rid)
    if not should_emit_return_notify(
        operator=op,
        assigner=author,
        room_type=room_type,
        lead_done=lead_done,
        reply_body=reply_body,
        trigger_text=trigger_text,
        phase=phase,
        rc=rc,
    ):
        if lead_done:
            log(
                f"multi-round return-notify suppressed lead_done=1 "
                f"room={room_name or rid} mid={mid} op={op}"
            )
        elif phase == PHASE_FINAL_ERR or (rc is not None and int(rc) != 0):
            log(
                f"multi-round return-notify suppressed quality_gate "
                f"phase={phase} rc={rc} room={room_name or rid} mid={mid} op={op}"
            )
        return

    # Peer delivery bookkeeping for the active epoch (assignee dedupe / observability).
    try:
        record_assignee_delivered(rid, op, mid=mid)
    except Exception as e:
        log(f"multi-round record delivered failed mid={mid}: {e}")

    target = resolve_return_notify_target(
        author, lead=MR_GROK_LEAD, completing_operator=op
    )
    ep = None
    try:
        ep = room_epoch(rid)
    except Exception:
        ep = None
    text = build_return_notify_text(
        target=target,
        completing_operator=op,
        source_mid=mid,
        room_name=room_name,
        summary=summary_from_reply(reply_body),
        epoch=ep,
    )
    # Post as this process's operator identity (identity="grok" maps to local operator
    # secrets for hermes/agy/claude/grok; "agy" dual-peer path is intentionally avoided).
    posted = post_message_get_id(rid, text, identity=COLLAB_GROK)
    log(
        f"multi-round return-notify target=@{target} from={op} mid={mid} "
        f"room={room_name or rid} posted={bool(posted)} "
        f"marker={COLLAB_RETURN_MARKER} epoch={ep or '-'}"
    )


```

## `handle_principal_message` — principal multi-@ lead-only

```python
            return

        # Issue #2 P0: principal multi-@ of lead+peers → only lead enqueues.
        # Peers wait for an explicit lead assign (new mid). Direct principal→@peer
        # (lead not mentioned) still wakes that peer.
        if multi_round_enabled() and mid and principal_multi_mention_lead_only(
            author=user,
            operator=OPERATOR,
            text=text,
            room_type=room_type,
        ):
            log(
                f"multi-round skip peer enqueue principal multi-@ lead-only "
                f"op={OPERATOR} room={room_name or rid} mid={mid} author={user}"
            )
            _mark_processed(
                mid,
                rid,
                msg.get("ts") if isinstance(msg.get("ts"), str) else None,
                rc=0,
            )
            return

```

