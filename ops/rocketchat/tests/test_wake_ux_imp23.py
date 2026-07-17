#!/usr/bin/env python3
"""IMP-23 pure tests: S1 backoff, S2 salvage/retry skip, S7 cwd."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import traceback
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
_MIRROR_WAKE = _TEST_DIR.parent / "wake"
_RUNTIME_WAKE = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"

POLICY_WAKE = (
    _MIRROR_WAKE if (_MIRROR_WAKE / "wake_ux_imp23.py").is_file() else _RUNTIME_WAKE
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


def test_salvage_structured() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        body = (
            "Looking into it.\n\n"
            "- Root cause: stream redelivery\n"
            "- Fix: intentional mention\n"
            "- Status: ready\n"
        )
        salv = m.extract_salvageable_body(body)
        assert salv is not None and "Root cause" in salv
        record("salvage_structured", True)
    except Exception as e:
        record("salvage_structured", False, repr(e) + traceback.format_exc())


def test_salvage_cancelled_mid_length() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        # 90 chars unstructured — only salvageable when Cancelled
        text = "x" * 90
        assert m.extract_salvageable_body(text) is None
        assert m.extract_salvageable_body(text, stop_reason="Cancelled") is not None
        record("salvage_cancelled_mid_length", True)
    except Exception as e:
        record("salvage_cancelled_mid_length", False, repr(e) + traceback.format_exc())


def test_skip_retry_when_final_ok() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        assert m.should_skip_empty_reply_retry(
            phase="FINAL_OK",
            reply_file_empty=True,
            stop_reason="Cancelled",
            rc=0,
            already_retry=False,
        )
        record("skip_retry_when_final_ok", True)
    except Exception as e:
        record("skip_retry_when_final_ok", False, repr(e) + traceback.format_exc())


def test_skip_retry_when_strong_stream() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        stream = (
            "Summary of the fix:\n\n"
            "- Wire should_skip_empty_reply_retry into the operator\n"
            "- Prefer stream salvage over a second Cancelled wake\n"
            "- Keep one bubble\n"
        )
        assert m.should_skip_empty_reply_retry(
            phase="FINAL_ERR",
            reply_file_empty=True,
            stop_reason="Cancelled",
            rc=0,
            already_retry=False,
            stream_text=stream,
        )
        record("skip_retry_when_strong_stream", True)
    except Exception as e:
        record("skip_retry_when_strong_stream", False, repr(e) + traceback.format_exc())


def test_allow_retry_when_truly_empty() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        assert not m.should_skip_empty_reply_retry(
            phase="FINAL_ERR",
            reply_file_empty=True,
            stop_reason="Cancelled",
            rc=0,
            already_retry=False,
            stream_text="short",
        )
        record("allow_retry_when_truly_empty", True)
    except Exception as e:
        record("allow_retry_when_truly_empty", False, repr(e) + traceback.format_exc())


def test_rate_limit_backoff() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        b = m.RateLimitBackoff(base_s=2.0, max_s=10.0)
        assert b.allow_nonfinal(now=100.0)
        wait = b.note_429(now=100.0)
        assert wait >= 2.0
        assert not b.allow_nonfinal(now=100.5)
        assert b.allow_nonfinal(now=100.0 + wait + 0.01)
        b.note_success()
        assert b.allow_nonfinal(now=200.0)
        record("rate_limit_backoff", True)
    except Exception as e:
        record("rate_limit_backoff", False, repr(e) + traceback.format_exc())


def test_validate_wake_cwd() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        ok, reason = m.validate_wake_cwd(None)
        assert ok and reason == "default"
        with tempfile.TemporaryDirectory() as td:
            ok2, _ = m.validate_wake_cwd(td)
            assert ok2
        ok3, reason3 = m.validate_wake_cwd("/no/such/cwd/imp23-test")
        assert not ok3 and "missing" in reason3
        err = m.format_missing_cwd_err("/no/such", mid_short="abcd1234")
        assert "cwd_missing" in err and "abcd1234" in err
        record("validate_wake_cwd", True)
    except Exception as e:
        record("validate_wake_cwd", False, repr(e) + traceback.format_exc())


def test_final_cool_sleep_clamp() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        assert m.final_cool_sleep_s(0.0) == 1.0
        assert m.final_cool_sleep_s(3.5) == 3.5
        assert m.final_cool_sleep_s(99.0) == 8.0
        record("final_cool_sleep_clamp", True)
    except Exception as e:
        record("final_cool_sleep_clamp", False, repr(e) + traceback.format_exc())


def test_cross_process_bucket() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        with tempfile.TemporaryDirectory() as td:
            bucket = Path(td) / "rc-update.bucket"
            assert m.cross_process_update_wait(bucket, min_gap_s=0.5, now=1000.0) == 0.0
            m.cross_process_update_touch(bucket, now=1000.0)
            # Force mtime via touch content; function uses st_mtime
            wait = m.cross_process_update_wait(bucket, min_gap_s=0.5, now=1000.1)
            assert wait > 0
        record("cross_process_bucket", True)
    except Exception as e:
        record("cross_process_bucket", False, repr(e) + traceback.format_exc())


def main() -> int:
    print("IMP-23 wake UX pure tests")
    print(f"  policy_wake={POLICY_WAKE}")
    for fn in (
        test_salvage_structured,
        test_salvage_cancelled_mid_length,
        test_skip_retry_when_final_ok,
        test_skip_retry_when_strong_stream,
        test_allow_retry_when_truly_empty,
        test_rate_limit_backoff,
        test_validate_wake_cwd,
        test_final_cool_sleep_clamp,
        test_cross_process_bucket,
    ):
        fn()
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
