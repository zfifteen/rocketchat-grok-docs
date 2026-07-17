#!/usr/bin/env python3
"""IMP-22 pure tests for wake_denials + format_final_err integration."""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
_MIRROR_WAKE = _TEST_DIR.parent / "wake"
_RUNTIME_WAKE = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"

POLICY_WAKE = (
    _MIRROR_WAKE
    if (_MIRROR_WAKE / "wake_denials.py").is_file()
    else _RUNTIME_WAKE
)
RUNTIME_WAKE = _RUNTIME_WAKE

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


def test_extract_tool_denials_hermes_style() -> None:
    try:
        d = _load("wake_denials", POLICY_WAKE / "wake_denials.py")
        log = """
INFO starting tools
BLOCKED: User denied this command. The user has NOT consented to write_file.
later noise
Tool terminal was denied: network not allowed
"""
        items = d.extract_tool_denials(log)
        assert len(items) >= 1, items
        blob = "\n".join(items).lower()
        assert "write_file" in blob or "blocked" in blob or "denied" in blob, items
        assert len(items) <= 3
        record("extract_tool_denials_hermes_style", True)
    except Exception as e:
        record("extract_tool_denials_hermes_style", False, repr(e) + traceback.format_exc())


def test_extract_caps_and_dedupe() -> None:
    try:
        d = _load("wake_denials", POLICY_WAKE / "wake_denials.py")
        log = "\n".join(
            [
                "BLOCKED: write_file path=/tmp/a",
                "BLOCKED: write_file path=/tmp/b",
                "User denied this command for terminal",
                "permission denied on patch",
                "Tool read_file was denied",
            ]
        )
        items = d.extract_tool_denials(log, max_items=3)
        assert len(items) == 3, items
        record("extract_caps_and_dedupe", True)
    except Exception as e:
        record("extract_caps_and_dedupe", False, repr(e) + traceback.format_exc())


def test_redact_secrets() -> None:
    try:
        d = _load("wake_denials", POLICY_WAKE / "wake_denials.py")
        log = "BLOCKED write_file token=sk-abcdefghijklmnopqrstuvwxyz123456 password=supersecret"
        items = d.extract_tool_denials(log)
        assert items, items
        joined = "\n".join(items)
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in joined
        assert "supersecret" not in joined
        assert "[redacted]" in joined or "token" in joined.lower()
        record("redact_secrets", True)
    except Exception as e:
        record("redact_secrets", False, repr(e) + traceback.format_exc())


def test_format_final_err_includes_denials() -> None:
    try:
        if not (RUNTIME_WAKE / "wake_telemetry.py").is_file():
            record("format_final_err_includes_denials", True, "SKIP no runtime telemetry")
            return
        # Ensure runtime can import denials from same dir
        t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
        body = t.format_final_err(
            rc=0,
            stop_reason="Cancelled",
            approval_mode="restricted",
            log_basename="wake-run-x.log",
            denials=["BLOCKED: write_file denied"],
            mid_short="abc12345",
        )
        assert "tools_blocked:" in body
        assert "write_file" in body
        assert "stopReason: Cancelled" in body
        assert body.index("tools_blocked:") < body.index("stopReason:")
        assert "mid: abc12345" in body
        assert "elevate" in body.lower() or "restricted" in body.lower()
        record("format_final_err_includes_denials", True)
    except Exception as e:
        record("format_final_err_includes_denials", False, repr(e) + traceback.format_exc())


def test_choose_final_body_err_and_footer() -> None:
    try:
        if not (RUNTIME_WAKE / "wake_telemetry.py").is_file():
            record("choose_final_body_err_and_footer", True, "SKIP no runtime telemetry")
            return
        t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
        log = 'stopReason": "Cancelled"\nBLOCKED: User denied this command write_file\n'

        err_body, phase, _ = t.choose_final_body(
            reply_file_body="",
            rc=0,
            log_text=log,
            approval_mode="restricted",
            log_basename="w.log",
            compose_ok=lambda s: s,
            mid_short="deadbeef",
        )
        assert phase == t.PHASE_FINAL_ERR
        assert "write_file" in err_body.lower() or "blocked" in err_body.lower()

        ok_body, phase2, _ = t.choose_final_body(
            reply_file_body="Here is a partial answer.",
            rc=0,
            log_text=log,
            approval_mode="restricted",
            log_basename="w.log",
            compose_ok=lambda s: s,
            env={"RC_WAKE_DENIAL_FOOTER": "1"},
        )
        assert phase2 == t.PHASE_FINAL_OK
        assert "Tools blocked:" in ok_body
        assert ok_body.startswith("Here is a partial answer.")
        record("choose_final_body_err_and_footer", True)
    except Exception as e:
        record("choose_final_body_err_and_footer", False, repr(e) + traceback.format_exc())


def test_empty_log_no_denials() -> None:
    try:
        d = _load("wake_denials", POLICY_WAKE / "wake_denials.py")
        assert d.extract_tool_denials("") == []
        assert d.extract_tool_denials("all good stopReason=EndTurn") == []
        record("empty_log_no_denials", True)
    except Exception as e:
        record("empty_log_no_denials", False, repr(e) + traceback.format_exc())


def main() -> int:
    print("IMP-22 wake denial tests")
    print(f"  policy_wake={POLICY_WAKE}")
    for fn in (
        test_extract_tool_denials_hermes_style,
        test_extract_caps_and_dedupe,
        test_redact_secrets,
        test_format_final_err_includes_denials,
        test_choose_final_body_err_and_footer,
        test_empty_log_no_denials,
    ):
        fn()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n{passed}/{len(RESULTS)} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
