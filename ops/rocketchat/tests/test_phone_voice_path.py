#!/usr/bin/env python3
"""
Fail-closed contracts for the phone Call media path.

These tests exist so we cannot green "Call fixed" on bot/loopback-only evidence.
HTTP LAN join URLs must FAIL url_is_phone_media_safe — that is the iPhone
mediaDevices TypeError class of bug.
"""

from __future__ import annotations

import sys
from pathlib import Path

CALL_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "call"
sys.path.insert(0, str(CALL_DIR))

from rc_call_media import (  # noqa: E402
    assess_jitsi_phone_settings,
    assess_phone_join_url,
    join_url_host_is_phone_safe,
    phone_facing_join_url,
    url_is_browser_secure_context,
    url_is_phone_media_safe,
)


def test_http_lan_is_not_secure_context() -> None:
    assert url_is_browser_secure_context("http://192.168.1.149:8090/Agencyx") is False
    assert url_is_browser_secure_context("http://10.0.0.5:8090/r") is False


def test_https_is_secure_context() -> None:
    assert url_is_browser_secure_context("https://voice.example.com/Agencyx") is True
    assert url_is_browser_secure_context("https://192.168.1.149:8090/Agencyx") is True


def test_loopback_http_is_secure_for_bot_only() -> None:
    assert url_is_browser_secure_context("http://127.0.0.1:8090/Agencyx") is True
    assert url_is_browser_secure_context("http://localhost:8090/Agencyx") is True
    # Phone gate still red — phones cannot open loopback
    assert url_is_phone_media_safe("http://127.0.0.1:8090/Agencyx") is False


def test_current_phone_facing_helper_is_not_media_safe() -> None:
    """
    phone_facing_join_url still emits http://LAN — that must fail the media gate.

    When HTTPS is shipped, update this test to expect PASS on the new scheme.
    """
    url = phone_facing_join_url("abc", lan_ip="192.168.1.149", port=8090)
    assert url.startswith("http://192.168.1.149:8090/")
    assert join_url_host_is_phone_safe(url, lan_ip="192.168.1.149") is True
    assert url_is_phone_media_safe(url, lan_ip="192.168.1.149") is False
    a = assess_phone_join_url(url, lan_ip="192.168.1.149")
    assert a["ok"] is False
    assert a["phone_media_safe"] is False
    assert any("secure" in i or "mediaDevices" in i for i in a["issues"])


def test_https_lan_is_phone_media_safe() -> None:
    url = "https://192.168.1.149:8090/Agencyabc"
    assert url_is_phone_media_safe(url, lan_ip="192.168.1.149") is True
    assert assess_phone_join_url(url, lan_ip="192.168.1.149")["ok"] is True


def test_jitsi_ssl_false_settings_fail_phone_gate() -> None:
    r = assess_jitsi_phone_settings(
        "192.168.1.149:8090",
        False,
        lan_ip="192.168.1.149",
        port=8090,
    )
    assert r["ok"] is False
    assert "jitsi_ssl_not_true_phone_needs_https" in r["issues"]


def test_jitsi_ssl_true_https_domain_passes_settings_gate() -> None:
    r = assess_jitsi_phone_settings(
        "192.168.1.149:8090",
        True,
        lan_ip="192.168.1.149",
        port=8090,
    )
    assert r["ok"] is True
    assert r["issues"] == []


def test_host_safe_is_not_enough() -> None:
    """Regression: older code treated non-loopback host as 'phone safe'."""
    url = "http://192.168.1.149:8090/Agencyx"
    assert join_url_host_is_phone_safe(url) is True
    assert url_is_phone_media_safe(url) is False


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
