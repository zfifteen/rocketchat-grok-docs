#!/usr/bin/env python3
"""IMP-B: stream chrome + intentional wake honesty (plan v2)."""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

RUNTIME_WAKE = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"
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


def _wl():
    return _load("wake_lib", RUNTIME_WAKE / "wake_lib.py")


def _would_wake_bot(wl, body: str, peer: str = "feynman") -> bool:
    """Approximate bot-author peer wake: not nonfinal and intentional mention of peer."""
    if wl.looks_like_nonfinal_stream(body):
        return False
    return peer.lower() in wl.intentional_operator_mentions(body)


def test_t2a_thoughts_headed_assign() -> None:
    try:
        wl = _wl()
        body = "*Thoughts*\n@feynman dig residual X"
        assert wl.looks_like_nonfinal_stream(body) is True, body
        assert _would_wake_bot(wl, body) is False
        record("T2a_thoughts_headed_no_wake", True)
    except Exception as e:
        record("T2a_thoughts_headed_no_wake", False, repr(e) + traceback.format_exc())


def test_t2_live_wrapped_intermediate() -> None:
    try:
        wl = _wl()
        body = "*Thoughts*\n\n@feynman dig residual X"
        assert wl.looks_like_nonfinal_stream(body) is True
        assert _would_wake_bot(wl, body) is False
        record("T2_live_wrapped_no_wake", True)
    except Exception as e:
        record("T2_live_wrapped_no_wake", False, repr(e) + traceback.format_exc())


def test_f1_final_compose_wakes() -> None:
    try:
        wl = _wl()
        rule = "────────────────"
        body = f"*Thoughts*\nfoo\n\n{rule}\n\n@feynman dig residual X"
        assert wl.looks_like_nonfinal_stream(body) is False
        assert _would_wake_bot(wl, body) is True
        record("F1_final_compose_wakes", True)
    except Exception as e:
        record("F1_final_compose_wakes", False, repr(e) + traceback.format_exc())


def test_f2_bare_final_wakes() -> None:
    try:
        wl = _wl()
        body = "@feynman dig residual X"
        assert wl.looks_like_nonfinal_stream(body) is False
        assert _would_wake_bot(wl, body) is True
        record("F2_bare_final_wakes", True)
    except Exception as e:
        record("F2_bare_final_wakes", False, repr(e) + traceback.format_exc())


def test_f3_shared_goal() -> None:
    try:
        wl = _wl()
        body = "**Shared goal:** fix thrash\n\n@feynman kill-check Y"
        assert wl.looks_like_nonfinal_stream(body) is False
        assert _would_wake_bot(wl, body) is True
        record("F3_shared_goal_wakes", True)
    except Exception as e:
        record("F3_shared_goal_wakes", False, repr(e) + traceback.format_exc())


def test_f4_for_footer_on_final() -> None:
    try:
        wl = _wl()
        rule = "────────────────"
        body = f"*Thoughts*\nmid\n\n{rule}\n\nSTATUS: done\nFOR: @hermes"
        assert wl.looks_like_nonfinal_stream(body) is False
        assert "hermes" in wl.intentional_operator_mentions(body)
        record("F4_for_footer_final", True)
    except Exception as e:
        record("F4_for_footer_final", False, repr(e) + traceback.format_exc())


def test_t1a_prose_no_wake() -> None:
    try:
        wl = _wl()
        body = "I'll have feynman kill-check that @feynman when free."
        assert wl.looks_like_nonfinal_stream(body) is False
        assert "feynman" not in wl.intentional_operator_mentions(body)
        record("T1a_prose_no_intentional", True)
    except Exception as e:
        record("T1a_prose_no_intentional", False, repr(e) + traceback.format_exc())


def test_r1_collab_return() -> None:
    try:
        wl = _wl()
        body = "@hermes collab-return from `feynman`"
        assert wl.looks_like_nonfinal_stream(body) is False
        assert "hermes" in wl.intentional_operator_mentions(body)
        record("R1_collab_return_wakes_hermes", True)
    except Exception as e:
        record("R1_collab_return_wakes_hermes", False, repr(e) + traceback.format_exc())


def test_w_chrome_helper_shape() -> None:
    """Wrap contract: label + blank + body, never rule on intermediate."""
    try:
        wl = _wl()
        label = getattr(wl, "THOUGHTS_SECTION_LABEL", "*Thoughts*")
        rule = getattr(wl, "THOUGHTS_SECTION_RULE", "────────────────")
        tail = "@feynman dig residual X"
        wrapped = f"{label}\n\n{tail}"
        assert wrapped.startswith(label)
        assert rule not in wrapped
        assert wl.looks_like_nonfinal_stream(wrapped) is True
        record("W_chrome_shape_nonfinal", True)
    except Exception as e:
        record("W_chrome_shape_nonfinal", False, repr(e) + traceback.format_exc())


def main() -> int:
    print("IMP-B stream/intentional tests")
    print(f"  wake_lib={RUNTIME_WAKE / 'wake_lib.py'}")
    for fn in (
        test_t2a_thoughts_headed_assign,
        test_t2_live_wrapped_intermediate,
        test_f1_final_compose_wakes,
        test_f2_bare_final_wakes,
        test_f3_shared_goal,
        test_f4_for_footer_on_final,
        test_t1a_prose_no_wake,
        test_r1_collab_return,
        test_w_chrome_helper_shape,
    ):
        fn()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n{passed}/{len(RESULTS)} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
