#!/usr/bin/env python3
"""
NF-SPEC-02 Streaming Thinking Telemetry — unit/contract tests on shipped code.

Usage:
  python3 ~/.grok/agency/ops/rocketchat/tests/test_nf02_streaming_telemetry.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

WAKE_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"
FIXTURES = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "tests" / "fixtures"
SCRATCH = Path(
    os.environ.get(
        "RC_TEST_SCRATCH",
        "/var/folders/k_/spz3zlj566sc4qh29g0tk6jh0000gn/T/grok-goal-4d949303cfcf/implementer",
    )
)
SCRATCH.mkdir(parents=True, exist_ok=True)

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def _load(name: str, path: Path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    # Always reload so tests pick up salvage / telemetry edits in the same process.
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_wake_terminal_fixtures() -> None:
    try:
        tel = _load("wake_telemetry", WAKE_DIR / "wake_telemetry.py")
        cancelled = (FIXTURES / "wake-cancelled.log").read_text(encoding="utf-8")
        term = tel.parse_wake_terminal(cancelled)
        assert term.stop_reason == "Cancelled", term
        assert term.session_id  # present on fixture

        endturn = (FIXTURES / "wake-endturn.log").read_text(encoding="utf-8")
        term2 = tel.parse_wake_terminal(endturn)
        assert term2.stop_reason == "EndTurn"

        # empty / garbage
        assert tel.parse_wake_terminal("").stop_reason is None
        assert tel.parse_wake_terminal("cmd: nothing").stop_reason is None

        # streaming-json: reconstruct text from type=text chunks (end has no text)
        stream_log = "\n".join(
            [
                "cmd: grok ...",
                '{"type":"thought","data":"hmm"}',
                '{"type":"text","data":"- Status: project is healthy and fully documented. "}',
                '{"type":"text","data":"Git is clean, public GitHub is live, and feature specs through NF-10 are in the tree."}',
                '{"type":"end","stopReason":"Cancelled","sessionId":"s1"}',
            ]
        )
        term3 = tel.parse_wake_terminal(stream_log)
        assert term3.stop_reason == "Cancelled"
        assert "healthy" in (term3.text or "")
        assert tel.is_salvageable_wake_text(term3.text), term3.text
        # choose_final_body can salvage reconstructed stream text when reply empty
        body, phase, _ = tel.choose_final_body(
            reply_file_body="",
            rc=0,
            log_text=stream_log,
            approval_mode="restricted",
            log_basename="s.log",
            compose_ok=lambda x: x,
        )
        assert phase == tel.PHASE_FINAL_OK, body
        assert "healthy" in body

        record("parse_wake_terminal_fixtures", True)
    except Exception as e:
        record("parse_wake_terminal_fixtures", False, repr(e) + traceback.format_exc())


def test_format_final_err_structure() -> None:
    try:
        tel = _load("wake_telemetry", WAKE_DIR / "wake_telemetry.py")
        body = tel.format_final_err(
            rc=0,
            stop_reason="Cancelled",
            approval_mode="restricted",
            log_basename="wake-run-123.log",
        )
        assert "stopReason: Cancelled" in body
        assert "rc: 0" in body
        assert "approval_mode: restricted" in body
        assert "log: wake-run-123.log" in body
        assert "hint:" in body
        assert body.startswith("(")

        body2 = tel.format_final_err(
            rc=1,
            stop_reason=None,
            approval_mode="admin",
            log_basename="x.log",
        )
        assert "rc=1" in body2 or "rc: 1" in body2
        assert "stopReason: unknown" in body2

        record("format_final_err_structure", True)
    except Exception as e:
        record("format_final_err_structure", False, repr(e) + traceback.format_exc())


def test_choose_final_body_ok_vs_err() -> None:
    try:
        tel = _load("wake_telemetry", WAKE_DIR / "wake_telemetry.py")
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        cancelled = (FIXTURES / "wake-cancelled.log").read_text(encoding="utf-8")

        ok_body, phase, term = tel.choose_final_body(
            reply_file_body="Hello principal",
            rc=0,
            log_text=cancelled,
            approval_mode="restricted",
            log_basename="w.log",
            compose_ok=wl.compose_unified_reply,
        )
        assert phase == tel.PHASE_FINAL_OK
        assert ok_body == "Hello principal"
        assert term.stop_reason == "Cancelled"  # still parseable

        # Short Cancelled monologue (fixture) — not salvageable → FINAL_ERR
        err_body, phase2, term2 = tel.choose_final_body(
            reply_file_body="",
            rc=0,
            log_text=cancelled,
            approval_mode="restricted",
            log_basename="wake-run-cancelled.log",
            compose_ok=wl.compose_unified_reply,
        )
        assert phase2 == tel.PHASE_FINAL_ERR
        assert "Cancelled" in err_body
        assert "wake-run-cancelled.log" in err_body
        assert term2.stop_reason == "Cancelled"
        assert "Wake ended without a reply file" in err_body or "stopReason:" in err_body

        record("choose_final_body_ok_vs_err", True)
    except Exception as e:
        record("choose_final_body_ok_vs_err", False, repr(e) + traceback.format_exc())


def test_choose_final_body_salvages_cancelled_with_text() -> None:
    """Shipped choose_final_body must salvage non-empty Cancelled JSON text."""
    try:
        tel = _load("wake_telemetry", WAKE_DIR / "wake_telemetry.py")
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        # Prefer live artifact from PGS channel failure; fall back to synthetic.
        artifact = (
            Path.home()
            / "logs"
            / "rocketchat-dm-wake"
            / "wake-run-1783911317.log"
        )
        if artifact.is_file() and artifact.stat().st_size > 500:
            log_text = artifact.read_text(encoding="utf-8", errors="replace")
        else:
            log_text = (
                "cmd: ['grok']\n\n"
                + json.dumps(
                    {
                        "text": (
                            "- **BLOCKED:** no shell tool in this auditor session\n"
                            "- **HEAD:** main\n"
                            "- **Uncommitted:** unresolved without git status\n"
                            "- **Verdict:** REJECT completeness until parent shell runs "
                            "`git status -sb`\n"
                            "- **Next:** operator/parent should run git status for full inventory"
                        ),
                        "stopReason": "Cancelled",
                        "sessionId": "sess-test-salvage",
                    },
                    indent=2,
                )
                + "\n"
            )

        body, phase, term = tel.choose_final_body(
            reply_file_body="",  # empty reply file — the bug
            rc=0,
            log_text=log_text,
            approval_mode="restricted",
            log_basename="wake-run-1783911317.log",
            compose_ok=wl.compose_unified_reply,
        )
        assert phase == tel.PHASE_FINAL_OK, (phase, body[:200])
        assert term.stop_reason == "Cancelled"
        assert body.strip()
        assert "Wake ended without a reply file" not in body
        assert "Thinking" not in body[:20]
        # Must include salvageable content (bullets or substantive text)
        assert len(body) >= 80
        # Silent salvage (no "Recovered from wake…" footnote — principal 2026-07-16)
        assert "Recovered from wake output" not in body
        assert "BLOCKED" in body or "-" in body or "Verdict" in body

        # Too-short text still FINAL_ERR
        short = json.dumps(
            {"text": "Checking the repo now.", "stopReason": "Cancelled"}
        )
        err_b, err_p, _ = tel.choose_final_body(
            reply_file_body="",
            rc=0,
            log_text=short,
            approval_mode="restricted",
            log_basename="short.log",
            compose_ok=wl.compose_unified_reply,
        )
        assert err_p == tel.PHASE_FINAL_ERR
        assert "Cancelled" in err_b

        record("choose_final_body_salvages_cancelled_with_text", True)
    except Exception as e:
        record(
            "choose_final_body_salvages_cancelled_with_text",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_stream_throttle_and_flags() -> None:
    try:
        tel = _load("wake_telemetry", WAKE_DIR / "wake_telemetry.py")
        assert tel.wake_stream_enabled({"RC_WAKE_STREAM": "0"}) is False
        assert tel.wake_stream_enabled({"RC_WAKE_STREAM": "1"}) is True
        assert tel.wake_stream_enabled({}) is True  # default on
        assert tel.wake_meta_enabled({"RC_WAKE_META": "1"}) is True
        assert tel.wake_meta_enabled({"RC_WAKE_META": "0"}) is False

        th = tel.StreamThrottle(min_interval_ms=10_000, max_updates=3)
        t0 = 100.0
        assert th.allow(now=t0, force=True) is True  # first
        assert th.allow(now=t0 + 0.001) is False  # too soon
        assert th.allow(now=t0 + 11.0) is True
        assert th.allow(now=t0 + 22.0) is True
        assert th.allow(now=t0 + 33.0) is False  # max 3
        # Defaults must stay sparse enough to avoid RC 429 on finalize
        assert tel.DEFAULT_MIN_INTERVAL_MS >= 1500
        assert tel.DEFAULT_MAX_UPDATES <= 20
        assert tel.DEFAULT_THOUGHT_FLUSH_MS >= 1500

        meta = tel.format_running_meta(
            room_name="dm:principal",
            cwd="/Users/x/IdeaProjects/foo",
            approval_mode="restricted",
            phase="running",
            elapsed_s=12,
        )
        assert meta.startswith("Working…") or meta.startswith("Working...")
        assert "restricted" in meta
        assert "foo" in meta
        assert "12s" in meta

        record("stream_throttle_and_flags", True)
    except Exception as e:
        record("stream_throttle_and_flags", False, repr(e) + traceback.format_exc())


def test_thought_accumulator_and_format() -> None:
    try:
        tel = _load("wake_telemetry", WAKE_DIR / "wake_telemetry.py")
        assert tel.parse_streaming_json_line("") is None
        assert tel.parse_streaming_json_line("not json") is None
        assert tel.parse_streaming_json_line('{"type":"thought","data":"Hi"}') == {
            "type": "thought",
            "data": "Hi",
        }
        acc = tel.ThoughtAccumulator()
        assert acc.consume_event({"type": "text", "data": "nope"}) is False
        assert acc.consume_event({"type": "thought", "data": "Hello "}) is True
        assert acc.consume_event({"type": "thought", "data": "world"}) is True
        assert acc.text == "Hello world"
        body = acc.format(max_chars=20)
        assert "Hello" in body or body.endswith("world")
        long = "x" * 100
        assert tel.format_thought_intermediate(long, max_chars=10).startswith("…")
        assert tel.format_thought_intermediate("") == tel.ACTIVITY_PLACEHOLDER
        record("thought_accumulator_and_format", True)
    except Exception as e:
        record(
            "thought_accumulator_and_format",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_operator_final_err_on_empty_reply() -> None:
    """Drive real _process_pending_item with mocked RC/wake; assert FINAL_ERR fields."""
    try:
        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
        tel = _load("wake_telemetry", WAKE_DIR / "wake_telemetry.py")
        tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        cancelled = (FIXTURES / "wake-cancelled.log").read_text(encoding="utf-8")
        try:
            # isolate state/logs
            agent.LOG_DIR = tmp / "logs"
            agent.LOG_DIR.mkdir(parents=True)
            agent.LOG_PATH = agent.LOG_DIR / "operator-agent.log"
            agent.LOCK_DIR = agent.LOG_DIR / "wake.lock.d"
            agent.STATE_PATH = tmp / "state.json"
            agent.HEALTH_PATH = agent.LOG_DIR / "health.json"
            agent.PROMPT_TEMPLATE = WAKE_DIR / "reply_prompt.txt"

            updates: list[tuple[str, str]] = []  # (msg_id, body)
            posts: list[str] = []

            def post_thinking(room_id: str, **_kw) -> str:
                posts.append("…")
                return "msg-bubble-1"

            def finalize(room_id: str, mid: str, body: str, **_kw) -> bool:
                updates.append((mid, body))
                return True

            def update_meta(room_id: str, mid: str, body: str, **_kw) -> bool:
                updates.append((mid, body))
                return True

            log_path = tmp / "wake-run-fixture.log"
            log_path.write_text(cancelled, encoding="utf-8")

            agent.post_thinking_placeholder = post_thinking
            agent.finalize_thinking_message = finalize
            agent.update_thinking_meta = update_meta
            agent.schedule_principal_ack = lambda *a, **k: None
            agent.wake_grok = lambda prompt, **k: (0, None, log_path, cancelled)
            agent.write_health_snapshot = lambda **k: None
            agent.force_clear_wake_lock()
            # Force meta path: stream off so starting Working… still posts
            os.environ["RC_WAKE_STREAM"] = "0"
            os.environ["RC_WAKE_META"] = "1"

            msg = {
                "_id": "m-err-1",
                "rid": "room-x",
                "msg": "do work",
                "u": {"username": "principal"},
            }
            agent._enqueue_pending(msg, "room-x", "dm:principal", "d")
            agent._drain_pending_wakes()

            assert posts, "placeholder must post"
            assert updates, "must update bubble"
            # all updates same msg id
            ids = {u[0] for u in updates}
            assert ids == {"msg-bubble-1"}, ids
            # at least one non-final meta before final
            bodies = [u[1] for u in updates]
            assert any(
                b.startswith("Working") for b in bodies[:-1]
            ) or any("Working" in b for b in bodies[:-1]), bodies
            final = bodies[-1]
            assert "Cancelled" in final, final
            assert "rc:" in final or "rc=" in final
            assert "approval_mode" in final
            assert "log:" in final or "wake-run" in final

            record("operator_final_err_on_empty_reply", True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        record(
            "operator_final_err_on_empty_reply",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_operator_final_ok_reply_file() -> None:
    try:
        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
        tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        try:
            agent.LOG_DIR = tmp / "logs"
            agent.LOG_DIR.mkdir(parents=True)
            agent.LOG_PATH = agent.LOG_DIR / "operator-agent.log"
            agent.LOCK_DIR = agent.LOG_DIR / "wake.lock.d"
            agent.STATE_PATH = tmp / "state.json"
            agent.HEALTH_PATH = agent.LOG_DIR / "health.json"
            agent.PROMPT_TEMPLATE = WAKE_DIR / "reply_prompt.txt"

            updates: list[tuple[str, str]] = []

            agent.post_thinking_placeholder = lambda rid, **_k: "msg-ok-1"
            agent.finalize_thinking_message = (
                lambda rid, mid, body, **_k: updates.append((mid, body)) or True
            )
            agent.update_thinking_meta = (
                lambda rid, mid, body, **_k: updates.append((mid, body)) or True
            )

            def fake_wake(prompt, **k):
                # Write reply file path embedded in prompt
                # Operator creates reply file path before wake; find empty files in LOG_DIR
                for p in agent.LOG_DIR.glob("wake-reply-*.txt"):
                    p.write_text("Final answer from reply file.", encoding="utf-8")
                logp = agent.LOG_DIR / "wake-run-ok.log"
                logp.write_text(
                    '{\n  "stopReason": "EndTurn",\n  "sessionId": "s1"\n}\n',
                    encoding="utf-8",
                )
                return (0, "s1", logp, logp.read_text())

            agent.wake_grok = fake_wake
            agent.write_health_snapshot = lambda **k: None
            agent.force_clear_wake_lock()

            msg = {
                "_id": "m-ok-1",
                "rid": "room-ok",
                "msg": "hello",
                "u": {"username": "principal"},
            }
            agent._enqueue_pending(msg, "room-ok", "general", "c")
            agent._drain_pending_wakes()

            assert updates
            assert all(u[0] == "msg-ok-1" for u in updates)
            final = updates[-1][1]
            assert "Final answer from reply file" in final
            assert "stopReason" not in final  # FINAL_OK is answer only
            assert not final.startswith("Working")

            record("operator_final_ok_reply_file", True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        record(
            "operator_final_ok_reply_file",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_bubble_lifecycle_meta_then_final() -> None:
    """placeholder → ≥1 meta → final; same msgId."""
    try:
        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
        tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        try:
            agent.LOG_DIR = tmp / "logs"
            agent.LOG_DIR.mkdir(parents=True)
            agent.LOG_PATH = agent.LOG_DIR / "op.log"
            agent.LOCK_DIR = agent.LOG_DIR / "wake.lock.d"
            agent.STATE_PATH = tmp / "state.json"
            agent.HEALTH_PATH = agent.LOG_DIR / "health.json"
            agent.PROMPT_TEMPLATE = WAKE_DIR / "reply_prompt.txt"

            sequence: list[tuple[str, str, str]] = []  # kind, mid, body

            def post_thinking(rid: str, **_kw) -> str:
                sequence.append(("post", "msg-life", "…"))
                return "msg-life"

            def meta(rid, mid, body, **_kw):
                sequence.append(("meta", mid, body))
                return True

            def fin(rid, mid, body, **_kw):
                sequence.append(("final", mid, body))
                return True

            agent.post_thinking_placeholder = post_thinking
            agent.update_thinking_meta = meta
            agent.finalize_thinking_message = fin
            agent.wake_grok = lambda prompt, **k: (
                1,
                None,
                tmp / "empty.log",
                '{"stopReason":"Cancelled"}',
            )
            (tmp / "empty.log").write_text(
                '{"stopReason":"Cancelled"}', encoding="utf-8"
            )
            agent.write_health_snapshot = lambda **k: None
            agent.force_clear_wake_lock()

            msg = {
                "_id": "m-life",
                "rid": "r-life",
                "msg": "task",
                "u": {"username": "principal"},
            }
            # ensure meta enabled; stream off so starting meta still runs
            os.environ["RC_WAKE_META"] = "1"
            os.environ["RC_WAKE_STREAM"] = "0"
            agent._enqueue_pending(msg, "r-life", "Agency", "c")
            agent._drain_pending_wakes()

            kinds = [s[0] for s in sequence]
            assert "post" in kinds
            assert "meta" in kinds, sequence
            assert kinds[-1] == "final"
            mids = {s[1] for s in sequence if s[0] in ("meta", "final")}
            assert mids == {"msg-life"}
            assert any("Working" in s[2] for s in sequence if s[0] == "meta")
            assert "Cancelled" in sequence[-1][2]

            record("bubble_lifecycle_meta_then_final", True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        record(
            "bubble_lifecycle_meta_then_final",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_source_wires_telemetry() -> None:
    try:
        src = (WAKE_DIR / "rc_operator_agent.py").read_text(encoding="utf-8")
        assert "wake_telemetry" in src
        assert "choose_final_body" in src
        assert "update_thinking_meta" in src
        assert "format_running_meta" in src
        assert (WAKE_DIR / "wake_telemetry.py").is_file()
        record("source_wires_telemetry", True)
    except Exception as e:
        record("source_wires_telemetry", False, repr(e))


def test_meta_finalized_guard_and_join() -> None:
    """
    Race fix: meta heartbeat must not overwrite FINAL_* after finalize.

    Static: meta_finalized set + join before finalize_thinking_message.
    Dynamic: after wake returns, a delayed update_thinking_meta must not
    land after final body (final is last body for the msg id).
    """
    try:
        src = (WAKE_DIR / "rc_operator_agent.py").read_text(encoding="utf-8")
        # Order: stream_finalized.set before finalize_thinking_message in process path
        start = src.index("def _process_pending_item")
        end = src.index("\ndef _drain_pending_wakes", start)
        body = src[start:end]
        assert "stream_finalized" in body
        assert ".join(" in body
        fin_idx = body.index("finalize_thinking_message")
        set_idx = body.index("stream_finalized.set()")
        assert set_idx < fin_idx, "stream_finalized must be set before finalize"
        assert "if stream_finalized.is_set()" in body

        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
        tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        try:
            agent.LOG_DIR = tmp / "logs"
            agent.LOG_DIR.mkdir(parents=True)
            agent.LOG_PATH = agent.LOG_DIR / "op.log"
            agent.LOCK_DIR = agent.LOG_DIR / "wake.lock.d"
            agent.STATE_PATH = tmp / "state.json"
            agent.HEALTH_PATH = agent.LOG_DIR / "health.json"
            agent.PROMPT_TEMPLATE = WAKE_DIR / "reply_prompt.txt"

            updates: list[tuple[str, str]] = []
            import time as _time

            def slow_meta(rid, mid, body, **_kw):
                # Simulate slow RC update that would race finalize if unguarded
                _time.sleep(0.05)
                updates.append(("meta", mid, body))
                return True

            def fin(rid, mid, body, **_kw):
                updates.append(("final", mid, body))
                return True

            agent.post_thinking_placeholder = lambda rid, **_k: "msg-race"
            agent.update_thinking_meta = slow_meta
            agent.finalize_thinking_message = fin
            agent.wake_grok = lambda prompt, **k: (
                0,
                None,
                tmp / "r.log",
                '{"stopReason":"EndTurn"}',
            )
            (tmp / "r.log").write_text(
                '{"stopReason":"EndTurn","text":"x"}', encoding="utf-8"
            )
            # Write reply so FINAL_OK
            def wake_and_write(prompt, **k):
                for p in agent.LOG_DIR.glob("wake-reply-*.txt"):
                    p.write_text("OK final body", encoding="utf-8")
                lp = tmp / "r.log"
                lp.write_text('{"stopReason":"EndTurn"}', encoding="utf-8")
                return (0, "sid", lp, lp.read_text())

            agent.wake_grok = wake_and_write
            agent.write_health_snapshot = lambda **k: None
            agent.schedule_principal_ack = lambda *a, **k: None
            agent.force_clear_wake_lock()
            os.environ["RC_WAKE_META"] = "1"
            os.environ["RC_WAKE_STREAM"] = "0"  # meta heartbeat path under test
            # Short heartbeat so a second meta might try during wake (still mocked fast)
            os.environ["RC_STREAM_HEARTBEAT_S"] = "0.01"

            agent._enqueue_pending(
                {
                    "_id": "m-race",
                    "rid": "r-race",
                    "msg": "go",
                    "u": {"username": "principal"},
                },
                "r-race",
                "dm",
                "d",
            )
            agent._drain_pending_wakes()
            _time.sleep(0.15)  # allow any late meta attempt

            assert updates, "expected bubble updates"
            kinds = [u[0] for u in updates]
            assert kinds[-1] == "final", f"last must be final, got {kinds}"
            final_body = updates[-1][2]
            assert "OK final body" in final_body or final_body.strip()
            # No Working… after final
            after_final = False
            for kind, _mid, body in updates:
                if after_final and kind == "meta":
                    raise AssertionError(f"meta after final: {body[:80]!r}")
                if kind == "final":
                    after_final = True

            record("meta_finalized_guard_and_join", True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            os.environ.pop("RC_STREAM_HEARTBEAT_S", None)
    except Exception as e:
        record(
            "meta_finalized_guard_and_join",
            False,
            repr(e) + traceback.format_exc(),
        )


def main() -> int:
    print("NF-02 Streaming Thinking Telemetry tests")
    print(f"wake_dir={WAKE_DIR}")
    print(f"scratch={SCRATCH}")
    for t in (
        test_parse_wake_terminal_fixtures,
        test_format_final_err_structure,
        test_choose_final_body_ok_vs_err,
        test_choose_final_body_salvages_cancelled_with_text,
        test_stream_throttle_and_flags,
        test_thought_accumulator_and_format,
        test_operator_final_err_on_empty_reply,
        test_operator_final_ok_reply_file,
        test_bubble_lifecycle_meta_then_final,
        test_source_wires_telemetry,
        test_meta_finalized_guard_and_join,
    ):
        t()
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} passed")
    out = SCRATCH / "nf02-unit-contract.out"
    out.write_text(
        "\n".join(f"{s}\t{n}\t{d}" for n, s, d in RESULTS) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
