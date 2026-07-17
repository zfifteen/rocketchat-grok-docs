#!/usr/bin/env python3
"""
NF-SPEC-06 message reactions as wake ack — unit tests (no live RC).

Usage:
  python3 ~/.grok/agency/ops/rocketchat/tests/test_nf06_reactions.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from pathlib import Path
from unittest.mock import MagicMock, patch

WAKE_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def _load(name: str, path: Path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    # Fresh load for env-sensitive modules when needed
    if name in sys.modules and name != "rc_operator_agent":
        return sys.modules[name]
    if name == "rc_operator_agent" and name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_wake_react_env_gates() -> None:
    try:
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        assert wl.wake_react_enabled({"RC_WAKE_REACT": "1"}) is True
        assert wl.wake_react_enabled({"RC_WAKE_REACT": "0"}) is False
        assert wl.wake_react_enabled({"RC_WAKE_REACT": "off"}) is False
        assert wl.wake_react_enabled({}) is True  # default on
        assert wl.wake_react_emoji("start", {}) == "eyes"
        assert wl.wake_react_emoji("ok", {}) == "white_check_mark"
        assert wl.wake_react_emoji("err", {}) == "warning"
        assert (
            wl.wake_react_emoji("start", {"RC_WAKE_REACT_START": "hourglass"})
            == "hourglass"
        )
        record("wake_react_env_gates", True)
    except Exception as e:
        record("wake_react_env_gates", False, repr(e) + traceback.format_exc())


def test_react_message_posts_body() -> None:
    try:
        with patch.dict(os.environ, {"RC_WAKE_REACT": "1"}, clear=False):
            op = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
            calls: list[tuple] = []

            def fake_rest(method, path, body=None, *, identity="grok"):
                calls.append((method, path, body, identity))
                return {"success": True}

            op._rest_with_auth_retry = fake_rest  # type: ignore[method-assign]
            ok = op.react_message("mid123", "eyes", should_react=True, identity="grok")
            assert ok is True
            assert len(calls) == 1
            method, path, body, ident = calls[0]
            assert method == "POST"
            assert path == "/api/v1/chat.react"
            assert body == {
                "messageId": "mid123",
                "emoji": "eyes",
                "shouldReact": True,
            }
            assert ident == "grok"
        record("react_message_posts_body", True)
    except Exception as e:
        record("react_message_posts_body", False, repr(e) + traceback.format_exc())


def test_react_disabled_no_http() -> None:
    try:
        with patch.dict(os.environ, {"RC_WAKE_REACT": "0"}, clear=False):
            # Re-import wake_lib helpers via agent (reads os.environ at call time)
            op = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
            calls: list = []

            def fake_rest(*a, **k):
                calls.append((a, k))
                return {"success": True}

            op._rest_with_auth_retry = fake_rest  # type: ignore[method-assign]
            ok = op.react_message("mid123", "eyes")
            assert ok is False
            assert calls == []
        record("react_disabled_no_http", True)
    except Exception as e:
        record("react_disabled_no_http", False, repr(e) + traceback.format_exc())


def test_react_http_error_returns_false() -> None:
    try:
        with patch.dict(os.environ, {"RC_WAKE_REACT": "1"}, clear=False):
            op = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")

            def boom(*a, **k):
                raise RuntimeError("network down")

            op._rest_with_auth_retry = boom  # type: ignore[method-assign]
            ok = op.react_message("mid", "eyes")
            assert ok is False
        record("react_http_error_returns_false", True)
    except Exception as e:
        record(
            "react_http_error_returns_false", False, repr(e) + traceback.format_exc()
        )


def test_schedule_terminal_unreact_then_ok() -> None:
    try:
        with patch.dict(os.environ, {"RC_WAKE_REACT": "1"}, clear=False):
            op = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
            seq: list[tuple] = []

            def fake_react(msg_id, emoji, *, should_react=True, identity="grok"):
                seq.append((msg_id, emoji, should_react, identity))
                return True

            op.react_message = fake_react  # type: ignore[method-assign]
            # Run terminal path synchronously by calling _run logic via schedule + join
            import threading

            threads_before = threading.active_count()
            op.schedule_wake_react_terminal("t1", op.PHASE_FINAL_OK, identity="grok")
            # Join daemon threads briefly
            for t in threading.enumerate():
                if t.name.startswith("rc-react-term") and t is not threading.current_thread():
                    t.join(timeout=2.0)
            assert ("t1", "eyes", False, "grok") in seq or any(
                s[0] == "t1" and s[2] is False for s in seq
            ), seq
            assert any(
                s[0] == "t1" and s[1] == "white_check_mark" and s[2] is True
                for s in seq
            ), seq
            _ = threads_before
        record("schedule_terminal_unreact_then_ok", True)
    except Exception as e:
        record(
            "schedule_terminal_unreact_then_ok",
            False,
            repr(e) + traceback.format_exc(),
        )


def main() -> int:
    test_wake_react_env_gates()
    test_react_message_posts_body()
    test_react_disabled_no_http()
    test_react_http_error_returns_false()
    test_schedule_terminal_unreact_then_ok()
    failed = sum(1 for _, s, _ in RESULTS if s != "PASS")
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
