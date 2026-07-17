#!/usr/bin/env python3
"""IMP-23 S5 pure tests: in-flight busy chrome + follow-up queue policy.

Cases map to docs/improvements/23-wake-ux-log-deep-dive-2026-07-16/test-plan-s5.md (TP rev2).
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
_MIRROR_WAKE = _TEST_DIR.parent / "wake"
_RUNTIME_WAKE = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"

POLICY_WAKE = (
    _MIRROR_WAKE if (_MIRROR_WAKE / "wake_inflight_ux.py").is_file() else _RUNTIME_WAKE
)

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    extra = f" — {detail}" if detail and not ok else ""
    print(f"  {status}  {name}{extra}")


def _load(name: str, path: Path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _mod():
    return _load("wake_inflight_ux", POLICY_WAKE / "wake_inflight_ux.py")


def _subset(**kw):
    base = {
        "ts": "t0",
        "file": None,
        "files": None,
        "attachments": None,
        "mentions": None,
        "u": {"username": "principal"},
    }
    base.update(kw)
    return base


def _decide(m, **kw):
    defaults = dict(
        rid="r1",
        room_name="dm:p",
        room_type="d",
        author="principal",
        msg_subset=_subset(),
        target="grok",
        collab=False,
        retry_of=None,
        processed_ids=[],
        in_flight_ids=[],
        pending_wakes=[],
        in_flight_texts=None,
        now_iso="2026-07-17T00:00:00+00:00",
    )
    defaults.update(kw)
    return m.decide_enqueue(**defaults)


def test_normalize_strips_and_collapses_ws() -> None:
    try:
        m = _mod()
        assert m.normalize_wake_text("  hello   world\n") == "hello world"
        assert m.normalize_wake_text(None) == ""
        record("P1_normalize", True)
    except Exception as e:
        record("P1_normalize", False, repr(e) + traceback.format_exc())


def test_texts_same_after_normalize() -> None:
    try:
        m = _mod()
        assert m.texts_materially_differ("hi", "hi") is False
        assert m.texts_materially_differ("hi", "  hi  ") is False
        record("P2_texts_same", True)
    except Exception as e:
        record("P2_texts_same", False, repr(e) + traceback.format_exc())


def test_texts_differ() -> None:
    try:
        m = _mod()
        assert m.texts_materially_differ("do A", "do B") is True
        assert m.texts_materially_differ("", "x") is True
        record("P3_texts_differ", True)
    except Exception as e:
        record("P3_texts_differ", False, repr(e) + traceback.format_exc())


def test_decide_enqueue_fresh_mid() -> None:
    try:
        m = _mod()
        d = _decide(m, mid="m1", text="hello")
        assert d.kind == "enqueue"
        assert d.queue_changed is True
        assert d.ui_action == "ack_start"
        assert d.pending_item is not None
        assert d.pending_item["mid"] == "m1"
        assert d.source_mid == "m1"
        record("P4_enqueue_fresh", True)
    except Exception as e:
        record("P4_enqueue_fresh", False, repr(e) + traceback.format_exc())


def test_decide_inflight_same_text_busy_ack() -> None:
    try:
        m = _mod()
        d = _decide(
            m,
            mid="m1",
            text="hello",
            in_flight_ids=["m1"],
            in_flight_texts={"m1": "hello"},
        )
        assert d.kind == "busy_ack"
        assert d.queue_changed is False
        assert d.pending_item is None
        assert d.ui_action == "busy"
        assert "busy" in d.log_line.lower() or "in-flight" in d.log_line.lower()
        record("P5_inflight_same_busy", True)
    except Exception as e:
        record("P5_inflight_same_busy", False, repr(e) + traceback.format_exc())


def test_decide_inflight_missing_baseline_busy_ack() -> None:
    try:
        m = _mod()
        d = _decide(
            m,
            mid="m1",
            text="anything new",
            in_flight_ids=["m1"],
            in_flight_texts=None,
        )
        assert d.kind == "busy_ack"
        assert d.queue_changed is False
        record("P5b_missing_baseline_busy", True)
    except Exception as e:
        record("P5b_missing_baseline_busy", False, repr(e) + traceback.format_exc())


def test_decide_inflight_edit_queues_followup() -> None:
    try:
        m = _mod()
        d = _decide(
            m,
            mid="m1",
            text="do B",
            in_flight_ids=["m1"],
            in_flight_texts={"m1": "do A"},
        )
        assert d.kind == "queue_followup"
        assert d.queue_changed is True
        assert d.ui_action == "busy"
        assert d.pending_item is not None
        assert d.pending_item["is_follow_up"] is True
        assert d.pending_item["follow_up_of"] == "m1"
        assert d.pending_item["text"] == "do B"
        assert d.pending_item["mid"] == m.make_followup_mid("m1", 1)
        assert d.pending_item["mid"] != "m1"
        record("P6_inflight_edit_followup", True)
    except Exception as e:
        record("P6_inflight_edit_followup", False, repr(e) + traceback.format_exc())


def test_decide_coalesce_existing_followup() -> None:
    try:
        m = _mod()
        fu = m.make_followup_mid("m1", 1)
        pending = [
            {
                "mid": fu,
                "follow_up_of": "m1",
                "text": "do B",
                "is_follow_up": True,
                "source_mid": "m1",
                "rid": "r1",
            }
        ]
        d = _decide(
            m,
            mid="m1",
            text="do C",
            in_flight_ids=["m1"],
            in_flight_texts={"m1": "do A"},
            pending_wakes=pending,
        )
        assert d.kind == "queue_followup"
        assert d.pending_item is not None
        assert d.pending_item["mid"] == fu
        assert d.pending_item["text"] == "do C"
        out = m.apply_decision_to_pending(list(pending), d)
        fu_rows = [p for p in out if isinstance(p, dict) and p.get("mid") == fu]
        assert len(fu_rows) == 1
        assert fu_rows[0]["text"] == "do C"
        record("P7_coalesce_followup", True)
    except Exception as e:
        record("P7_coalesce_followup", False, repr(e) + traceback.format_exc())


def test_decide_pending_same_text_busy() -> None:
    try:
        m = _mod()
        pending = [{"mid": "m1", "text": "hello", "rid": "r1"}]
        d = _decide(m, mid="m1", text="hello", pending_wakes=pending)
        assert d.kind == "busy_ack"
        assert d.queue_changed is False
        record("P8_pending_same_busy", True)
    except Exception as e:
        record("P8_pending_same_busy", False, repr(e) + traceback.format_exc())


def test_decide_pending_different_text_update() -> None:
    try:
        m = _mod()
        pending = [{"mid": "m1", "text": "old", "rid": "r1", "room_name": "dm:p"}]
        d = _decide(m, mid="m1", text="new ask", pending_wakes=pending)
        assert d.kind == "update_pending"
        assert d.queue_changed is True
        assert d.pending_item is not None
        assert d.pending_item["mid"] == "m1"
        assert d.pending_item["text"] == "new ask"
        assert "#fu" not in d.pending_item["mid"]
        out = m.apply_decision_to_pending(list(pending), d)
        assert len(out) == 1
        assert out[0]["text"] == "new ask"
        record("P8b_pending_update", True)
    except Exception as e:
        record("P8b_pending_update", False, repr(e) + traceback.format_exc())


def test_decide_processed_already_done() -> None:
    try:
        m = _mod()
        d = _decide(m, mid="m1", text="x", processed_ids=["m1"])
        assert d.kind == "already_done"
        assert d.queue_changed is False
        assert d.ui_action is None
        assert d.pending_item is None
        record("P9_already_done", True)
    except Exception as e:
        record("P9_already_done", False, repr(e) + traceback.format_exc())


def test_log_dedupe_ttl() -> None:
    try:
        m = _mod()
        store: dict[str, float] = {}
        e1, store = m.should_emit_decision_log(
            last_logged=store, mid="m1", kind="busy_ack", now=1000.0, ttl_s=60.0
        )
        e2, store = m.should_emit_decision_log(
            last_logged=store, mid="m1", kind="busy_ack", now=1010.0, ttl_s=60.0
        )
        e3, store = m.should_emit_decision_log(
            last_logged=store, mid="m1", kind="busy_ack", now=1070.0, ttl_s=60.0
        )
        assert e1 is True and e2 is False and e3 is True
        record("P10_log_dedupe", True)
    except Exception as e:
        record("P10_log_dedupe", False, repr(e) + traceback.format_exc())


def test_decide_reject_empty_mid() -> None:
    try:
        m = _mod()
        d = _decide(m, mid="", text="hi")
        assert d.kind == "reject"
        assert d.queue_changed is False
        record("P11_reject_empty_mid", True)
    except Exception as e:
        record("P11_reject_empty_mid", False, repr(e) + traceback.format_exc())


def test_empty_text_still_enqueues() -> None:
    try:
        m = _mod()
        d = _decide(m, mid="m1", text="")
        assert d.kind == "enqueue"
        assert d.queue_changed is True
        record("P11b_empty_text_enqueue", True)
    except Exception as e:
        record("P11b_empty_text_enqueue", False, repr(e) + traceback.format_exc())


def test_followup_mid_not_source() -> None:
    try:
        m = _mod()
        d = _decide(
            m,
            mid="m1",
            text="do B",
            in_flight_ids=["m1"],
            in_flight_texts={"m1": "do A"},
        )
        assert d.pending_item is not None
        assert d.pending_item["mid"] != d.source_mid
        record("P12_followup_mid_neq_source", True)
    except Exception as e:
        record("P12_followup_mid_neq_source", False, repr(e) + traceback.format_exc())


def test_other_mid_inflight_still_enqueues() -> None:
    try:
        m = _mod()
        d = _decide(m, mid="m1", text="hi", in_flight_ids=["m0"])
        assert d.kind == "enqueue"
        record("P13_other_inflight_enqueue", True)
    except Exception as e:
        record("P13_other_inflight_enqueue", False, repr(e) + traceback.format_exc())


def test_make_followup_mid_stable() -> None:
    try:
        m = _mod()
        assert m.make_followup_mid("abc123", 1) == "abc123#fu1"
        assert m.make_followup_mid("abc123", 1) == m.make_followup_mid("abc123", 1)
        assert m.make_followup_mid("abc123", 2) != m.make_followup_mid("abc123", 1)
        record("P14_followup_mid_stable", True)
    except Exception as e:
        record("P14_followup_mid_stable", False, repr(e) + traceback.format_exc())


def test_retry_of_bypasses_processed() -> None:
    try:
        m = _mod()
        d = _decide(
            m,
            mid="m1",
            text="orig",
            processed_ids=["m1"],
            retry_of="m1",
        )
        assert d.kind == "enqueue"
        assert d.queue_changed is True
        assert d.pending_item is not None
        assert d.pending_item["mid"] == "m1"
        assert "#fu" not in d.pending_item["mid"]
        assert d.pending_item.get("is_empty_reply_retry") is True
        assert d.pending_item.get("retry_of") == "m1"
        record("P15_retry_bypasses_processed", True)
    except Exception as e:
        record("P15_retry_bypasses_processed", False, repr(e) + traceback.format_exc())


def test_retry_of_bypasses_inflight() -> None:
    try:
        m = _mod()
        d = _decide(
            m,
            mid="m1",
            text="orig",
            in_flight_ids=["m1"],
            in_flight_texts={"m1": "orig"},
            retry_of="m1",
        )
        assert d.kind == "enqueue"
        assert d.pending_item is not None
        assert d.pending_item["mid"] == "m1"
        record("P15b_retry_bypasses_inflight", True)
    except Exception as e:
        record("P15b_retry_bypasses_inflight", False, repr(e) + traceback.format_exc())


def test_apply_noop_busy() -> None:
    try:
        m = _mod()
        pending = [{"mid": "x", "text": "t"}]
        d = _decide(
            m,
            mid="m1",
            text="hello",
            in_flight_ids=["m1"],
            in_flight_texts={"m1": "hello"},
        )
        assert d.kind == "busy_ack"
        out = m.apply_decision_to_pending(list(pending), d)
        assert out == pending
        record("P16_apply_noop", True)
    except Exception as e:
        record("P16_apply_noop", False, repr(e) + traceback.format_exc())


def test_apply_append_cap() -> None:
    try:
        m = _mod()
        pending = [{"mid": f"old{i}", "text": "t"} for i in range(30)]
        d = _decide(m, mid="m_new", text="hi")
        out = m.apply_decision_to_pending(list(pending), d, max_pending=30)
        assert len(out) <= 30
        assert any(p.get("mid") == "m_new" for p in out if isinstance(p, dict))
        record("P17_apply_cap", True)
    except Exception as e:
        record("P17_apply_cap", False, repr(e) + traceback.format_exc())


def test_apply_replace_update_pending() -> None:
    try:
        m = _mod()
        pending = [{"mid": "m1", "text": "old", "rid": "r1"}]
        d = _decide(m, mid="m1", text="new", pending_wakes=pending)
        assert d.kind == "update_pending"
        out = m.apply_decision_to_pending(list(pending), d)
        assert len(out) == 1
        assert out[0]["text"] == "new"
        assert out[0]["mid"] == "m1"
        record("P18_apply_replace", True)
    except Exception as e:
        record("P18_apply_replace", False, repr(e) + traceback.format_exc())


def main() -> int:
    print("IMP-23 S5 inflight UX pure tests")
    print(f"  policy_wake={POLICY_WAKE}")
    if not (POLICY_WAKE / "wake_inflight_ux.py").is_file():
        print("  FAIL  wake_inflight_ux.py missing")
        return 1
    tests = [
        test_normalize_strips_and_collapses_ws,
        test_texts_same_after_normalize,
        test_texts_differ,
        test_decide_enqueue_fresh_mid,
        test_decide_inflight_same_text_busy_ack,
        test_decide_inflight_missing_baseline_busy_ack,
        test_decide_inflight_edit_queues_followup,
        test_decide_coalesce_existing_followup,
        test_decide_pending_same_text_busy,
        test_decide_pending_different_text_update,
        test_decide_processed_already_done,
        test_log_dedupe_ttl,
        test_decide_reject_empty_mid,
        test_empty_text_still_enqueues,
        test_followup_mid_not_source,
        test_other_mid_inflight_still_enqueues,
        test_make_followup_mid_stable,
        test_retry_of_bypasses_processed,
        test_retry_of_bypasses_inflight,
        test_apply_noop_busy,
        test_apply_append_cap,
        test_apply_replace_update_pending,
    ]
    for t in tests:
        t()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n{passed}/{len(RESULTS)} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
