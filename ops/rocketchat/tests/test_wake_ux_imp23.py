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
            # Function uses st_mtime (wall clock of write), not the `now` written
            # into the file. Measure remaining against real mtime + synthetic now.
            mtime = bucket.stat().st_mtime
            wait = m.cross_process_update_wait(
                bucket, min_gap_s=0.5, now=mtime + 0.1
            )
            assert 0.35 <= wait <= 0.45, wait
            assert (
                m.cross_process_update_wait(bucket, min_gap_s=0.5, now=mtime + 0.5)
                == 0.0
            )
        record("cross_process_bucket", True)
    except Exception as e:
        record("cross_process_bucket", False, repr(e) + traceback.format_exc())


def test_secret_redaction_bearer() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        body = (
            "Summary of auth fix:\n\n"
            "- authorization: Bearer abc.def.ghi\n"
            "- token: super-secret-value\n"
            "- sk-abcdefghijklmnop\n"
        )
        salv = m.extract_salvageable_body(body)
        assert salv is not None
        assert "abc.def.ghi" not in salv
        assert "super-secret-value" not in salv
        assert "sk-abcdefghijklmnop" not in salv
        assert "[redacted]" in salv
        record("secret_redaction_bearer", True)
    except Exception as e:
        record("secret_redaction_bearer", False, repr(e) + traceback.format_exc())


def test_trailing_structured_section() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        body = (
            "- early scratch bullet that should be dropped\n"
            "Long monologue about tools and retries with enough filler text.\n\n"
            "## Final report\n\n"
            "- Root cause: stream redelivery after Cancelled stopReason\n"
            "- Fix: intentional mention plus salvage of stream text\n"
            "- Status: ready for principal review of the bubble\n"
        )
        salv = m.extract_salvageable_body(body)
        assert salv is not None
        assert salv.lstrip().startswith("## Final report")
        assert "early scratch" not in salv
        assert "Root cause" in salv
        record("trailing_structured_section", True)
    except Exception as e:
        record(
            "trailing_structured_section", False, repr(e) + traceback.format_exc()
        )


def test_skip_retry_when_rc_nonzero() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        assert m.should_skip_empty_reply_retry(
            phase="FINAL_ERR",
            reply_file_empty=True,
            stop_reason="Cancelled",
            rc=1,
            already_retry=False,
            stream_text="short",
        )
        assert m.should_skip_empty_reply_retry(
            phase="FINAL_ERR",
            reply_file_empty=True,
            stop_reason="EndTurn",
            rc=0,
            already_retry=False,
            stream_text="short",
        )
        record("skip_retry_when_rc_nonzero", True)
    except Exception as e:
        record("skip_retry_when_rc_nonzero", False, repr(e) + traceback.format_exc())


def test_cwd_not_a_directory() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        with tempfile.NamedTemporaryFile() as tf:
            ok, reason = m.validate_wake_cwd(tf.name)
            assert not ok and "not a directory" in reason
        record("cwd_not_a_directory", True)
    except Exception as e:
        record("cwd_not_a_directory", False, repr(e) + traceback.format_exc())


def test_rate_limit_backoff_escalation() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        b = m.RateLimitBackoff(base_s=2.0, max_s=10.0)
        w1 = b.note_429(now=0.0)
        w2 = b.note_429(now=0.0)
        w3 = b.note_429(now=0.0)
        w4 = b.note_429(now=0.0)
        assert w1 == 2.0 and w2 == 4.0 and w3 == 8.0 and w4 == 10.0
        record("rate_limit_backoff_escalation", True)
    except Exception as e:
        record(
            "rate_limit_backoff_escalation", False, repr(e) + traceback.format_exc()
        )


def test_default_shared_update_bucket() -> None:
    try:
        m = _load("wake_ux_imp23", POLICY_WAKE / "wake_ux_imp23.py")
        import os

        old = os.environ.pop("RC_UPDATE_BUCKET", None)
        try:
            p = m.default_shared_update_bucket()
            assert p.name == "rc-update.bucket"
            assert p.parts[-2] == "rocketchat-shared"
            os.environ["RC_UPDATE_BUCKET"] = "/tmp/custom-rc-update.bucket"
            # reload to pick env in function (reads os.environ each call)
            assert m.default_shared_update_bucket() == Path(
                "/tmp/custom-rc-update.bucket"
            )
        finally:
            if old is None:
                os.environ.pop("RC_UPDATE_BUCKET", None)
            else:
                os.environ["RC_UPDATE_BUCKET"] = old
        record("default_shared_update_bucket", True)
    except Exception as e:
        record(
            "default_shared_update_bucket", False, repr(e) + traceback.format_exc()
        )


def test_digest_line_epoch_and_filter() -> None:
    """S14: only count ISO-stamped lines inside the since window."""
    try:
        import importlib.util as iu

        dig_path = _TEST_DIR.parent / "scripts" / "rc_wake_digest.py"
        if not dig_path.is_file():
            dig_path = (
                Path.home()
                / ".grok"
                / "agency"
                / "ops"
                / "rocketchat"
                / "scripts"
                / "rc_wake_digest.py"
            )
        spec = iu.spec_from_file_location("rc_wake_digest", dig_path)
        assert spec and spec.loader
        dig = iu.module_from_spec(spec)
        spec.loader.exec_module(dig)
        assert dig._line_epoch("[2026-07-16T12:00:00Z] phase=FINAL_OK") is not None
        assert dig._line_epoch("no stamp phase=FINAL_OK") is None
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "operator-agent.log"
            log.write_text(
                "[2020-01-01T00:00:00Z] phase=FINAL_OK old\n"
                "[2099-01-01T00:00:00Z] phase=FINAL_OK new\n"
                "phase=FINAL_OK nostamp\n",
                encoding="utf-8",
            )
            # since far in the past → only lines with ts >= since; old+new match,
            # nostamp dropped
            n_all = dig._count(log, r"phase=FINAL_OK", since=0.0)
            assert n_all == 2
            # since after old stamp → only new
            n_new = dig._count(
                log, r"phase=FINAL_OK", since=dig._line_epoch(
                    "[2099-01-01T00:00:00Z] x"
                )
                - 1.0,
            )
            assert n_new == 1
        record("digest_line_epoch_and_filter", True)
    except Exception as e:
        record(
            "digest_line_epoch_and_filter", False, repr(e) + traceback.format_exc()
        )


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
        test_secret_redaction_bearer,
        test_trailing_structured_section,
        test_skip_retry_when_rc_nonzero,
        test_cwd_not_a_directory,
        test_rate_limit_backoff_escalation,
        test_default_shared_update_bucket,
        test_digest_line_epoch_and_filter,
    ):
        fn()
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
