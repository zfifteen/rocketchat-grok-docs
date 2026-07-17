#!/usr/bin/env python3
"""
Tests for lobby-free RC Call voice media path.

Drives real shipped helpers (call URL prep, voice room HTTP) — not mocks of RMS.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

CALL_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "call"
VOICE_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "voice_room"
sys.path.insert(0, str(CALL_DIR))

import rc_call_bot as cb  # noqa: E402


def test_is_voice_room_url_rejects_public_jitsi() -> None:
    assert cb._is_voice_room_url("https://meet.jit.si/Agencyabc") is False
    assert (
        cb._is_voice_room_url(
            "http://10.71.11.69:8090/Agency6a51946a059c36f189588a6c"
        )
        is True
    )


def test_jitsi_url_ready_strips_hash_for_voice_room() -> None:
    raw = (
        "http://10.71.11.69:8090/Agencyabc"
        "#config.prejoinPageEnabled=false&userInfo.displayName=%22X%22"
    )
    out = cb._jitsi_url_ready(raw)
    assert "meet.jit.si" not in out
    assert out.startswith("http://10.71.11.69:8090/Agencyabc")
    assert "#" not in out
    assert "name=Grok" in out


def test_prefer_loopback_nav_url_rewrites_lan_for_same_host_bot() -> None:
    raw = "http://10.71.11.69:8090/Agencyabc?name=Grok"
    out = cb.prefer_loopback_nav_url(raw)
    assert out.startswith("http://127.0.0.1:8090/Agencyabc")
    assert "name=Grok" in out
    # RC-facing URL prep still leaves LAN for phones
    ready = cb._jitsi_url_ready(
        "http://10.71.11.69:8090/Agencyabc#config.prejoinPageEnabled=false"
    )
    assert "10.71.11.69" in ready


def test_prefer_loopback_leaves_non_local_hosts() -> None:
    raw = "http://203.0.113.9:8090/Agencyabc?name=Grok"
    assert cb.prefer_loopback_nav_url(raw) == raw


def test_prefer_loopback_leaves_meet_jit_si() -> None:
    raw = "https://meet.jit.si/Agencyabc"
    assert cb.prefer_loopback_nav_url(raw) == raw


def test_jitsi_url_ready_keeps_jitsi_hash_for_meet_jit_si() -> None:
    raw = "https://meet.jit.si/Agencyabc"
    out = cb._jitsi_url_ready(raw)
    assert out.startswith("https://meet.jit.si/Agencyabc#")
    assert "prejoinPageEnabled=false" in out


def test_voice_room_health_endpoint_live() -> None:
    """Requires voice_room server on RC_VOICE_ROOM_PORT (default 8090)."""
    port = 8090
    url = f"http://127.0.0.1:{port}/health"
    with urllib.request.urlopen(url, timeout=5) as resp:
        body = json.loads(resp.read().decode())
    assert body.get("ok") is True
    assert body.get("service") == "rc-voice-room"


def test_voice_room_serves_room_page_for_agency_path() -> None:
    url = "http://127.0.0.1:8090/AgencyPreflightTestRoom"
    with urllib.request.urlopen(url, timeout=5) as resp:
        html = resp.read().decode()
        code = resp.status
    assert code == 200
    assert "Grok Voice Room" in html or "Voice room" in html
    assert "__voiceRoom" in html or "RTCPeerConnection" in html


def test_voice_room_server_module_exists() -> None:
    assert (VOICE_DIR / "server.py").is_file()
    assert (VOICE_DIR / "static" / "room.html").is_file()
    assert (VOICE_DIR / "run_voice_room.sh").is_file()


def test_tts_to_wav_fallback_when_voice_missing() -> None:
    """Shipped tts_to_wav must not FATAL when default 'Ava' is unavailable."""
    prev = cb.SAY_VOICE
    try:
        cb.SAY_VOICE = "Ava"  # often Premium-only / fails with say -v Ava
        out = Path.home() / "logs" / "rocketchat-dm-wake" / "call-media" / "test-tts-fallback.wav"
        path = cb.tts_to_wav("Hello, Grok speaking.", out)
        assert path.is_file()
        assert path.stat().st_size > 1000
    finally:
        cb.SAY_VOICE = prev


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:
                fails += 1
                print("FAIL", name, e)
    raise SystemExit(1 if fails else 0)
