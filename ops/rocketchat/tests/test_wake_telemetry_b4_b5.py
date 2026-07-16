#!/usr/bin/env python3
"""B4 StreamThrottle cool-down + B5 helper probes (pure, no RC network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RUNTIME_WAKE = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"


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


def test_stream_throttle_seconds_since_last_no_updates() -> None:
    t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
    th = t.StreamThrottle()
    assert th.seconds_since_last() == float("inf")


def test_stream_throttle_seconds_since_last_after_update() -> None:
    t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
    th = t.StreamThrottle(min_interval_ms=1, max_updates=20)
    assert th.allow(now=10.0)
    assert abs(th.seconds_since_last(now=15.0) - 5.0) < 1e-6


def test_final_cool_remaining_none_needed() -> None:
    t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
    th = t.StreamThrottle(min_interval_ms=1, max_updates=20)
    th.allow(now=0.0)
    assert th.final_cool_remaining(3.0, now=4.0) == 0.0


def test_final_cool_remaining_some_needed() -> None:
    t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
    th = t.StreamThrottle(min_interval_ms=1, max_updates=20)
    th.allow(now=0.0)
    rem = th.final_cool_remaining(3.0, now=1.0)
    assert abs(rem - 2.0) < 1e-6


def test_final_cool_s_env_override() -> None:
    t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
    assert t.final_cool_s({"RC_FINAL_COOL_S": "5"}) == 5.0
    assert t.final_cool_s({"RC_FINAL_COOL_S": "0.1"}) == 1.0
    assert t.final_cool_s({"RC_FINAL_COOL_S": "99"}) == 8.0


def test_429_acceptance_no_nonfinal_since_final_gap() -> None:
    t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
    th = t.StreamThrottle(min_interval_ms=1, max_updates=20)
    cool = 3.0
    now = 0.0
    for _ in range(4):
        th.allow(now=now)
        now += 0.5
    # last update at 1.5; wait cool
    assert th.final_cool_remaining(cool, now=1.5 + cool) == 0.0


def test_429_acceptance_nonfinal_just_fired() -> None:
    t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
    th = t.StreamThrottle(min_interval_ms=1, max_updates=20)
    cool = 3.0
    th.allow(now=10.0)
    rem = th.final_cool_remaining(cool, now=10.5)
    assert abs(rem - 2.5) < 1e-6


def test_retry_cooldown_and_auto_retry_env() -> None:
    t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
    assert t.retry_cooldown_s({"RC_RETRY_COOLDOWN_S": "30"}) == 30.0
    assert t.wake_auto_retry_enabled({"RC_WAKE_AUTO_RETRY": "0"}) is False
    assert t.wake_auto_retry_enabled({}) is True


def test_extract_salvageable_from_thought_like_body() -> None:
    t = _load("wake_telemetry", RUNTIME_WAKE / "wake_telemetry.py")
    body = (
        "Investigating the wake path briefly.\n\n"
        "- Root cause: stream redelivery enqueues on intermediate @peer\n"
        "- Fix: intentional mention for bot authors\n"
        "- Status: ready to wire\n"
    )
    salvaged = t.extract_salvageable_body(body)
    assert salvaged is not None
    assert "Root cause" in salvaged
