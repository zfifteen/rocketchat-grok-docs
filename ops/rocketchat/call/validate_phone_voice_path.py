#!/usr/bin/env python3
"""
Fail-closed validator for the *phone* Rocket.Chat Call media path.

Why this exists
---------------
Earlier "Call fixed" claims only checked the Mac bot path:
  - RC join succeeds
  - Chromium on 127.0.0.1 gets a secure context
  - Bot greets / lock / no-peer timeout

That path can be green while the iPhone WebView still dies with:
  TypeError: undefined is not an object (evaluating 'navigator.mediaDevices.getUserMedia')

Root cause: http://<LAN-IP>:8090 is NOT a browser secure context on iOS.
mediaDevices is missing; getUserMedia never runs.

This script refuses exit 0 unless the phone path is media-safe.
Bot-only success must never green this gate.

Checks (all required unless --skip-safari)
-----------------------------------------
1. Pure URL rules (rc_call_media.assess_phone_join_url)
2. Live RC Jitsi settings (domain + jitsi_ssl) via ensure_jitsi_lan helpers
3. Voice room health reachable at the phone-facing origin
4. Safari JS probe on the phone-facing URL:
     window.isSecureContext && navigator.mediaDevices

Usage
-----
  python3 validate_phone_voice_path.py
  python3 validate_phone_voice_path.py --json
  python3 validate_phone_voice_path.py --skip-safari   # pure + RC only

Exit codes
----------
  0  PHONE_VOICE_PATH: PASS  (safe to claim phone media can work)
  1  PHONE_VOICE_PATH: FAIL  (do NOT claim Call fixed)
  2  validator infrastructure error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CALL_DIR = Path(__file__).resolve().parent
if str(CALL_DIR) not in sys.path:
    sys.path.insert(0, str(CALL_DIR))

from ensure_jitsi_lan import (  # noqa: E402
    DEFAULT_BASE,
    desired_jitsi_target,
    login_admin,
    read_jitsi_domain,
)
from rc_call_media import (  # noqa: E402
    assess_jitsi_phone_settings,
    assess_phone_join_url,
    phone_facing_join_url,
    resolve_primary_lan_ipv4,
    voice_room_port,
)


def _http_json(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_pure_phone_url(lan_ip: str, port: int) -> dict[str, Any]:
    """
    Desired phone join URL from ensure_jitsi target — must be media-safe.

    Prefer public HTTPS sample (default). Fall back to LAN helper URL only when
    RC_VOICE_JITSI_MODE=lan (expected to fail the media gate).
    """
    want = desired_jitsi_target(lan_ip=lan_ip, port=port)
    url = str(want.get("sample_join") or "") or phone_facing_join_url(
        "PhonePathValidate", lan_ip=lan_ip, port=port
    )
    assessment = assess_phone_join_url(
        url, lan_ip=lan_ip if want.get("mode") == "lan" else None
    )
    assessment["desired_mode"] = want.get("mode")
    assessment["desired"] = {
        "domain": want.get("domain"),
        "ssl": want.get("ssl"),
        "reason": want.get("reason"),
    }
    return {
        "name": "pure_phone_join_url",
        "ok": bool(assessment.get("ok")),
        "detail": assessment,
    }


def check_live_jitsi(lan_ip: str, port: int, base: str) -> dict[str, Any]:
    """Read live RC Jitsi domain/ssl and assess phone media safety."""
    try:
        uid, tok = login_admin(base=base)
        domain, ssl_val = read_jitsi_domain(base=base, user_id=uid, auth_token=tok)
    except Exception as ex:
        return {
            "name": "live_jitsi_settings",
            "ok": False,
            "detail": {
                "error": f"{type(ex).__name__}:{ex}",
                "issues": ["rc_admin_read_failed"],
            },
        }
    # Only require LAN IP match when the live domain is itself a LAN host.
    # Public HTTPS domains must not be forced to equal the Mac LAN IP.
    domain_host = (domain or "").split(":")[0].strip()
    require_lan = bool(domain_host and domain_host == (lan_ip or "").strip())
    assessed = assess_jitsi_phone_settings(
        domain,
        ssl_val,
        lan_ip=lan_ip if require_lan else None,
        port=port,
    )
    return {
        "name": "live_jitsi_settings",
        "ok": bool(assessed.get("ok")),
        "detail": assessed,
    }


def check_voice_room_health(origin: str) -> dict[str, Any]:
    """
    Health at the origin phones would use.

    Public branded host serves RC on /health; voice room is exposed as
    /voice-health via public_proxy. Direct LAN/loopback still uses /health.
    """
    host = (urlparse(origin).hostname or "").lower()
    if host in ("127.0.0.1", "localhost") or host.replace(".", "").isdigit():
        candidates = [origin.rstrip("/") + "/health"]
    else:
        candidates = [
            origin.rstrip("/") + "/voice-health",
            origin.rstrip("/") + "/health",
        ]
    last_err = ""
    for health_url in candidates:
        try:
            body = _http_json(health_url, timeout=8.0)
            ok = bool(body.get("ok")) and body.get("service") == "rc-voice-room"
            if ok:
                return {
                    "name": "voice_room_health",
                    "ok": True,
                    "detail": {"url": health_url, "body": body},
                }
            last_err = f"unexpected_body:{body}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as ex:
            last_err = f"{type(ex).__name__}:{ex}"
    return {
        "name": "voice_room_health",
        "ok": False,
        "detail": {
            "candidates": candidates,
            "error": last_err,
            "issues": ["voice_room_unreachable_at_phone_origin"],
        },
    }


def safari_secure_context_probe(url: str, *, wait_s: float = 2.5) -> dict[str, Any]:
    """
    Open the phone-facing URL in Safari and read isSecureContext + mediaDevices.

    This is the Mac-side stand-in for the iPhone WebView rule. Safari on a
    non-loopback http origin reports isSecureContext=false and mediaDevices
    missing — the same class of failure as the phone mic TypeError.
    """
    js = (
        "JSON.stringify({"
        "href: location.href,"
        "secure: window.isSecureContext,"
        "hasMediaDevices: !!(navigator.mediaDevices),"
        "hasGetUserMedia: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)"
        "})"
    )
    # Escape for AppleScript string
    js_esc = js.replace("\\", "\\\\").replace('"', '\\"')
    url_esc = url.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "Safari"
  activate
  if (count of windows) is 0 then
    make new document with properties {{URL:"{url_esc}"}}
  else
    tell front window to set URL of current tab to "{url_esc}"
  end if
end tell
delay {wait_s}
tell application "Safari"
  set r to do JavaScript "{js_esc}" in current tab of front window
  return r
end tell
'''
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as ex:
        return {
            "name": "safari_secure_context",
            "ok": False,
            "detail": {
                "url": url,
                "error": f"{type(ex).__name__}:{ex}",
                "issues": ["safari_probe_failed"],
            },
        }
    raw = (proc.stdout or "").strip()
    if proc.returncode != 0 or not raw:
        return {
            "name": "safari_secure_context",
            "ok": False,
            "detail": {
                "url": url,
                "returncode": proc.returncode,
                "stdout": raw,
                "stderr": (proc.stderr or "").strip(),
                "issues": ["safari_js_empty_or_failed_enable_AllowJavaScriptFromAppleEvents"],
            },
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "name": "safari_secure_context",
            "ok": False,
            "detail": {
                "url": url,
                "raw": raw,
                "issues": ["safari_js_not_json"],
            },
        }
    secure = bool(data.get("secure"))
    has_md = bool(data.get("hasMediaDevices"))
    has_gum = bool(data.get("hasGetUserMedia"))
    ok = secure and has_md and has_gum
    issues: list[str] = []
    if not secure:
        issues.append("safari_isSecureContext_false")
    if not has_md:
        issues.append("safari_mediaDevices_missing")
    if not has_gum:
        issues.append("safari_getUserMedia_missing")
    return {
        "name": "safari_secure_context",
        "ok": ok,
        "detail": {"url": url, "probe": data, "issues": issues},
    }


def check_bot_loopback_still_secure(port: int) -> dict[str, Any]:
    """
    Informational: bot path on 127.0.0.1 should remain secure-context-OK.

    This check never alone greens the phone gate; it documents the split.
    """
    bot_url = f"http://127.0.0.1:{port}/AgencyBotLoopbackProbe"
    a = assess_phone_join_url(bot_url)
    # Bot URL is intentionally NOT phone-safe (loopback); secure_context should be True
    secure_ok = bool(a.get("secure_context"))
    phone_ok = bool(a.get("phone_media_safe"))
    return {
        "name": "bot_loopback_context_info",
        "ok": secure_ok and not phone_ok,
        "required_for_phone_pass": False,
        "detail": {
            "url": bot_url,
            "secure_context": secure_ok,
            "phone_media_safe": phone_ok,
            "note": (
                "Bot may use loopback HTTP; phones cannot. "
                "Phone gate must stay red until HTTPS non-loopback works."
            ),
            "assessment": a,
        },
    }


def run_all(*, skip_safari: bool = False, base: str = DEFAULT_BASE) -> dict[str, Any]:
    lan_ip = resolve_primary_lan_ipv4()
    port = voice_room_port()
    checks: list[dict[str, Any]] = []

    if not lan_ip:
        summary = {
            "verdict": "FAIL",
            "label": "PHONE_VOICE_PATH",
            "ok": False,
            "reason": "no_lan_ip",
            "checks": [],
            "claim_call_fixed": False,
        }
        return summary

    checks.append(check_pure_phone_url(lan_ip, port))
    checks.append(check_live_jitsi(lan_ip, port, base))

    # Origin from live jitsi if available, else pure helper URL
    jitsi = next((c for c in checks if c["name"] == "live_jitsi_settings"), None)
    inferred = None
    if jitsi and isinstance(jitsi.get("detail"), dict):
        inferred = jitsi["detail"].get("inferred_join_url")
    if not inferred:
        inferred = phone_facing_join_url("PhonePathValidate", lan_ip=lan_ip, port=port)
    parsed = urlparse(inferred)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    checks.append(check_voice_room_health(origin))
    checks.append(check_bot_loopback_still_secure(port))

    if not skip_safari:
        room_url = f"{origin}/AgencyPhoneSafariProbe"
        checks.append(safari_secure_context_probe(room_url))

    # Phone pass = every check that is required
    required = [
        c
        for c in checks
        if c.get("required_for_phone_pass", True) is not False
    ]
    all_ok = all(bool(c.get("ok")) for c in required)
    issues: list[str] = []
    for c in required:
        if not c.get("ok"):
            detail = c.get("detail") or {}
            if isinstance(detail, dict):
                for i in detail.get("issues") or []:
                    issues.append(f"{c['name']}:{i}")
                if detail.get("error"):
                    issues.append(f"{c['name']}:{detail['error']}")
            if not any(x.startswith(c["name"] + ":") for x in issues):
                issues.append(f"{c['name']}:failed")

    return {
        "verdict": "PASS" if all_ok else "FAIL",
        "label": "PHONE_VOICE_PATH",
        "ok": all_ok,
        "claim_call_fixed": all_ok,
        "lan_ip": lan_ip,
        "port": port,
        "phone_origin": origin,
        "inferred_join_url": inferred,
        "issues": issues,
        "checks": checks,
        "policy": (
            "Do NOT claim Call/voice fixed unless verdict=PASS. "
            "Bot-only greets and dual-peer preflight on loopback are insufficient."
        ),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true", help="Print full JSON report")
    ap.add_argument(
        "--skip-safari",
        action="store_true",
        help="Skip Safari isSecureContext probe (still runs pure+RC gates)",
    )
    ap.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"Rocket.Chat base URL (default {DEFAULT_BASE})",
    )
    args = ap.parse_args()

    try:
        report = run_all(skip_safari=args.skip_safari, base=args.base)
    except Exception as ex:
        err = {"verdict": "ERROR", "ok": False, "error": f"{type(ex).__name__}:{ex}"}
        print(json.dumps(err, indent=2) if args.json else f"PHONE_VOICE_PATH: ERROR {err['error']}")
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['label']}: {report['verdict']}")
        print(f"  claim_call_fixed={report['claim_call_fixed']}")
        print(f"  phone_origin={report.get('phone_origin')}")
        print(f"  join={report.get('inferred_join_url')}")
        for c in report.get("checks") or []:
            flag = "PASS" if c.get("ok") else "FAIL"
            req = "" if c.get("required_for_phone_pass", True) else " (info)"
            print(f"  [{flag}] {c['name']}{req}")
        if report.get("issues"):
            print("  issues:")
            for i in report["issues"]:
                print(f"    - {i}")
        print(f"  policy: {report.get('policy')}")

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
