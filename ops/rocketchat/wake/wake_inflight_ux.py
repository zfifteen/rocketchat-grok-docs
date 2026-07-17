#!/usr/bin/env python3
"""IMP-23 S5 pure helpers: in-flight busy chrome + follow-up / pending-update policy.

No Rocket.Chat I/O. Safe to unit-test and mirror under docs-repo ops/rocketchat/wake/.
Runtime also loads from ~/.grok/agency/ops/rocketchat/wake/ when deployed.

Decision kinds (see test-plan-s5.md TP rev2):
  enqueue         — new pending row; ui=ack_start
  update_pending  — replace text on existing pending mid; ui=busy
  busy_ack        — no queue change; ui=busy
  queue_followup  — synthetic mid#fu1 follow-up after in-flight edit; ui=busy
  already_done    — mid already processed; no ui
  reject          — missing mid
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class EnqueueDecision:
    """Pure result of enqueue policy for one message attempt."""

    kind: str
    log_line: str
    ui_action: str | None  # "ack_start" | "busy" | None
    pending_item: dict[str, Any] | None
    replace_mid: str | None
    source_mid: str
    follow_up_of: str | None
    queue_changed: bool


def normalize_wake_text(text: str | None) -> str:
    """Strip and collapse internal whitespace for material-equality compares."""
    if text is None:
        return ""
    return _WS_RE.sub(" ", str(text).strip())


def texts_materially_differ(a: str | None, b: str | None) -> bool:
    """True when normalized texts are not equal."""
    return normalize_wake_text(a) != normalize_wake_text(b)


def make_followup_mid(source_mid: str, seq: int = 1) -> str:
    """Stable synthetic mid so processed/in_flight do not collide with source."""
    return f"{source_mid}#fu{int(seq)}"


def _find_pending_by_mid(pending: list, mid: str) -> dict[str, Any] | None:
    for p in pending:
        if isinstance(p, dict) and str(p.get("mid") or "") == mid:
            return p
    return None


def _find_followup_for_source(pending: list, source_mid: str) -> dict[str, Any] | None:
    for p in pending:
        if not isinstance(p, dict):
            continue
        if p.get("is_follow_up") and str(p.get("follow_up_of") or "") == source_mid:
            return p
        if str(p.get("mid") or "") == make_followup_mid(source_mid, 1):
            return p
    return None


def _build_item(
    *,
    mid: str,
    rid: str,
    room_name: str,
    room_type: str | None,
    text: str,
    author: str,
    msg_subset: Mapping[str, Any],
    target: str,
    collab: bool,
    now_iso: str | None,
    retry_of: str | None = None,
    is_follow_up: bool = False,
    follow_up_of: str | None = None,
    source_mid: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "mid": mid,
        "rid": rid,
        "room_name": room_name,
        "room_type": room_type,
        "ts": msg_subset.get("ts"),
        "text": text if text is not None else "",
        "file": msg_subset.get("file"),
        "files": msg_subset.get("files"),
        "attachments": msg_subset.get("attachments"),
        "mentions": msg_subset.get("mentions"),
        "u": msg_subset.get("u") or {"username": author},
        "author": author,
        "target": (target or "grok").strip().lower(),
        "collab": bool(collab),
        "enqueued_at": now_iso,
        "is_empty_reply_retry": bool(retry_of),
        "retry_of": retry_of,
        "is_follow_up": bool(is_follow_up),
        "follow_up_of": follow_up_of,
        "source_mid": source_mid or (follow_up_of if is_follow_up else mid),
        "acked_on_enqueue": False,
    }
    return item


def decide_enqueue(
    *,
    mid: str,
    rid: str,
    room_name: str,
    room_type: str | None,
    text: str | None,
    author: str,
    msg_subset: Mapping[str, Any],
    target: str,
    collab: bool,
    retry_of: str | None,
    processed_ids: list,
    in_flight_ids: list,
    pending_wakes: list,
    in_flight_texts: dict[str, str] | None = None,
    now_iso: str | None = None,
) -> EnqueueDecision:
    """Decide how to handle one enqueue attempt (pure; no I/O)."""
    mid_s = str(mid or "").strip()
    text_s = (text if text is not None else "")
    if isinstance(text_s, str):
        # Keep raw text on pending item; comparisons use normalize.
        pass
    else:
        text_s = str(text_s)

    if not mid_s:
        return EnqueueDecision(
            kind="reject",
            log_line="enqueue reject missing mid",
            ui_action=None,
            pending_item=None,
            replace_mid=None,
            source_mid="",
            follow_up_of=None,
            queue_changed=False,
        )

    # B5 empty-reply recovery: always requeue same mid.
    if retry_of:
        item = _build_item(
            mid=mid_s,
            rid=rid,
            room_name=room_name,
            room_type=room_type,
            text=text_s,
            author=author,
            msg_subset=msg_subset,
            target=target,
            collab=collab,
            now_iso=now_iso,
            retry_of=str(retry_of),
        )
        return EnqueueDecision(
            kind="enqueue",
            log_line=f"enqueue retry_of mid={mid_s} retry_of={retry_of}",
            ui_action="ack_start",
            pending_item=item,
            replace_mid=None,
            source_mid=mid_s,
            follow_up_of=None,
            queue_changed=True,
        )

    processed = {str(x) for x in (processed_ids or []) if x}
    if mid_s in processed:
        return EnqueueDecision(
            kind="already_done",
            log_line=f"enqueue already_done mid={mid_s}",
            ui_action=None,
            pending_item=None,
            replace_mid=None,
            source_mid=mid_s,
            follow_up_of=None,
            queue_changed=False,
        )

    inflight = {str(x) for x in (in_flight_ids or []) if x}
    texts = dict(in_flight_texts or {})
    pending = list(pending_wakes or [])

    if mid_s in inflight:
        baseline = texts.get(mid_s)
        if baseline is None:
            # Missing baseline → busy_ack only (no false follow-up).
            return EnqueueDecision(
                kind="busy_ack",
                log_line=f"enqueue busy_ack in-flight mid={mid_s} (no baseline)",
                ui_action="busy",
                pending_item=None,
                replace_mid=None,
                source_mid=mid_s,
                follow_up_of=None,
                queue_changed=False,
            )
        if not texts_materially_differ(baseline, text_s):
            return EnqueueDecision(
                kind="busy_ack",
                log_line=f"enqueue busy_ack in-flight mid={mid_s}",
                ui_action="busy",
                pending_item=None,
                replace_mid=None,
                source_mid=mid_s,
                follow_up_of=None,
                queue_changed=False,
            )
        # Edit while in-flight → coalesce single follow-up.
        fu_mid = make_followup_mid(mid_s, 1)
        existing_fu = _find_followup_for_source(pending, mid_s)
        if existing_fu is not None:
            fu_mid = str(existing_fu.get("mid") or fu_mid)
        item = _build_item(
            mid=fu_mid,
            rid=rid,
            room_name=room_name,
            room_type=room_type,
            text=text_s,
            author=author,
            msg_subset=msg_subset,
            target=target,
            collab=collab,
            now_iso=now_iso,
            is_follow_up=True,
            follow_up_of=mid_s,
            source_mid=mid_s,
        )
        return EnqueueDecision(
            kind="queue_followup",
            log_line=f"enqueue queue_followup mid={fu_mid} follow_up_of={mid_s}",
            ui_action="busy",
            pending_item=item,
            replace_mid=fu_mid if existing_fu is not None else None,
            source_mid=mid_s,
            follow_up_of=mid_s,
            queue_changed=True,
        )

    existing = _find_pending_by_mid(pending, mid_s)
    if existing is not None:
        old_text = existing.get("text")
        if not texts_materially_differ(old_text, text_s):
            return EnqueueDecision(
                kind="busy_ack",
                log_line=f"enqueue busy_ack pending mid={mid_s}",
                ui_action="busy",
                pending_item=None,
                replace_mid=None,
                source_mid=mid_s,
                follow_up_of=None,
                queue_changed=False,
            )
        item = _build_item(
            mid=mid_s,
            rid=rid,
            room_name=room_name,
            room_type=room_type,
            text=text_s,
            author=author,
            msg_subset=msg_subset,
            target=target,
            collab=collab,
            now_iso=now_iso,
            source_mid=mid_s,
        )
        # Preserve acked_on_enqueue if already set on pending row.
        if existing.get("acked_on_enqueue"):
            item["acked_on_enqueue"] = True
        return EnqueueDecision(
            kind="update_pending",
            log_line=f"enqueue update_pending mid={mid_s}",
            ui_action="busy",
            pending_item=item,
            replace_mid=mid_s,
            source_mid=mid_s,
            follow_up_of=None,
            queue_changed=True,
        )

    item = _build_item(
        mid=mid_s,
        rid=rid,
        room_name=room_name,
        room_type=room_type,
        text=text_s,
        author=author,
        msg_subset=msg_subset,
        target=target,
        collab=collab,
        now_iso=now_iso,
        source_mid=mid_s,
    )
    return EnqueueDecision(
        kind="enqueue",
        log_line=f"enqueue mid={mid_s} room={room_name}",
        ui_action="ack_start",
        pending_item=item,
        replace_mid=None,
        source_mid=mid_s,
        follow_up_of=None,
        queue_changed=True,
    )


def apply_decision_to_pending(
    pending: list,
    decision: EnqueueDecision,
    *,
    max_pending: int = 30,
) -> list:
    """Return new pending list after applying decision (append/replace/no-op)."""
    out = [p for p in list(pending or []) if isinstance(p, dict) or p is not None]
    if not decision.queue_changed or decision.pending_item is None:
        return list(pending or [])

    item = dict(decision.pending_item)
    replace_mid = decision.replace_mid or (
        item.get("mid") if decision.kind in ("update_pending", "queue_followup") else None
    )

    if decision.kind == "queue_followup":
        # Replace existing follow-up mid if present; else append.
        fu_mid = str(item.get("mid") or "")
        replaced = False
        new_list: list = []
        for p in out:
            if isinstance(p, dict) and str(p.get("mid") or "") == fu_mid:
                new_list.append(item)
                replaced = True
            else:
                new_list.append(p)
        if not replaced:
            new_list.append(item)
        out = new_list
    elif decision.kind == "update_pending" or replace_mid:
        rid_mid = str(replace_mid or item.get("mid") or "")
        new_list = []
        replaced = False
        for p in out:
            if isinstance(p, dict) and str(p.get("mid") or "") == rid_mid:
                new_list.append(item)
                replaced = True
            else:
                new_list.append(p)
        if not replaced:
            new_list.append(item)
        out = new_list
    else:
        # enqueue append (also replace if mid already present — safety)
        mid = str(item.get("mid") or "")
        if _find_pending_by_mid(out, mid) is not None:
            new_list = []
            for p in out:
                if isinstance(p, dict) and str(p.get("mid") or "") == mid:
                    new_list.append(item)
                else:
                    new_list.append(p)
            out = new_list
        else:
            out = list(out) + [item]

    if max_pending > 0 and len(out) > max_pending:
        out = out[-max_pending:]
    return out


def should_emit_decision_log(
    *,
    last_logged: dict[str, float],
    mid: str,
    kind: str,
    now: float,
    ttl_s: float = 60.0,
) -> tuple[bool, dict[str, float]]:
    """Dedupe spam; returns (emit?, updated_map)."""
    key = f"{mid}|{kind}"
    store = dict(last_logged or {})
    prev = store.get(key)
    if prev is not None and (now - float(prev)) < float(ttl_s):
        return False, store
    store[key] = float(now)
    # Cap map size
    if len(store) > 200:
        # drop oldest-ish keys
        for k in list(store.keys())[: len(store) - 160]:
            store.pop(k, None)
    return True, store


__all__ = [
    "EnqueueDecision",
    "normalize_wake_text",
    "texts_materially_differ",
    "make_followup_mid",
    "decide_enqueue",
    "apply_decision_to_pending",
    "should_emit_decision_log",
]
