#!/usr/bin/env python3
"""
Ensure Rocket.Chat Jitsi app domain is phone-media-safe.

Default (production for iOS mic): branded public HTTPS host
  jitsi_domain = velocityworks-rc.ngrok.app  (from PUBLIC_DOMAIN)
  jitsi_ssl    = true

That host is reverse-proxied (public_proxy.py) so /Agency* and /ws hit the
local voice room while the rest of the site stays Rocket.Chat. Safari/iOS then
get a real secure context → mediaDevices.getUserMedia works.

Legacy LAN HTTP (RC_VOICE_JITSI_MODE=lan) still exists for lab-only Mac tests;
it deliberately fails the phone media gate (no secure context on iOS).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from rc_call_media import (
    is_loopback_host,
    phone_facing_voice_room_netloc,
    resolve_primary_lan_ipv4,
    url_is_phone_media_safe,
    voice_room_port,
    voice_room_public_scheme,
)

JITSI_APP_ID = "3b387ba9-f57c-44c6-9810-8c0256abd64c"
DEFAULT_BASE = "http://127.0.0.1:3000"


def _load_secrets(path: Path | None = None) -> dict[str, str]:
    p = path or (Path.home() / ".grok" / "agency" / "secrets" / "rocketchat.env")
    out: dict[str, str] = {}
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    if not raw:
        return {}
    return json.loads(raw)


def login_admin(
    *,
    base: str = DEFAULT_BASE,
    secrets: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    sec = dict(secrets or _load_secrets())
    user = sec.get("ROCKETCHAT_ADMIN_USERNAME") or "principal"
    password = sec.get("ROCKETCHAT_ADMIN_PASSWORD") or ""
    if not password:
        raise RuntimeError("missing ROCKETCHAT_ADMIN_PASSWORD for Jitsi domain ensure")
    d = _http_json(
        "POST",
        f"{base.rstrip('/')}/api/v1/login",
        body={"user": user, "password": password},
    )
    data = d.get("data") or {}
    uid = data.get("userId")
    tok = data.get("authToken")
    if not uid or not tok:
        raise RuntimeError(f"RC admin login failed: {d}")
    return str(uid), str(tok)


def read_jitsi_domain(
    *,
    base: str = DEFAULT_BASE,
    user_id: str,
    auth_token: str,
    app_id: str = JITSI_APP_ID,
) -> tuple[str | None, bool | None]:
    h = {"X-User-Id": user_id, "X-Auth-Token": auth_token}
    d = _http_json("GET", f"{base.rstrip('/')}/api/apps/{app_id}/settings", headers=h)
    settings = d.get("settings") or {}
    domain = None
    ssl_val = None
    if isinstance(settings, dict):
        dom = settings.get("jitsi_domain") or {}
        ssl = settings.get("jitsi_ssl") or {}
        if isinstance(dom, dict):
            domain = dom.get("value")
        if isinstance(ssl, dict):
            ssl_val = ssl.get("value")
    return (
        str(domain) if domain is not None else None,
        bool(ssl_val) if isinstance(ssl_val, bool) else ssl_val,
    )


def set_jitsi_setting(
    setting_id: str,
    value: Any,
    *,
    base: str = DEFAULT_BASE,
    user_id: str,
    auth_token: str,
    app_id: str = JITSI_APP_ID,
) -> bool:
    h = {
        "X-User-Id": user_id,
        "X-Auth-Token": auth_token,
        "Content-Type": "application/json",
    }
    body = {"setting": {"id": setting_id, "value": value}}
    url = f"{base.rstrip('/')}/api/apps/{app_id}/settings/{setting_id}"
    d = _http_json("POST", url, headers=h, body=body)
    return bool(d.get("success"))


def _read_public_domain_file() -> str:
    p = Path(__file__).resolve().parents[1] / "PUBLIC_DOMAIN"
    if not p.is_file():
        return ""
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # first non-comment token is the host
        return s.split()[0].strip()
    return ""


def desired_jitsi_target(
    *,
    env: Mapping[str, str] | None = None,
    lan_ip: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    """
    Decide jitsi_domain + jitsi_ssl for phone-safe Calls.

    Modes (RC_VOICE_JITSI_MODE):
      public (default) — branded HTTPS host via PUBLIC_DOMAIN / env
      lan              — LAN IP:port + ssl false (fails phone media gate)
    """
    e = env if env is not None else os.environ
    mode = str(e.get("RC_VOICE_JITSI_MODE") or "public").strip().lower()
    if mode in ("lan", "local", "http-lan"):
        ip = (lan_ip or "").strip() or resolve_primary_lan_ipv4(env=e)
        if not ip or is_loopback_host(ip):
            return {
                "ok": False,
                "reason": "no_lan_ip",
                "domain": None,
                "ssl": False,
                "mode": "lan",
                "sample_join": None,
            }
        domain = phone_facing_voice_room_netloc(lan_ip=ip, port=port, env=e)
        sample = f"http://{domain}/AgencyPhonePathProbe"
        return {
            "ok": True,
            "reason": "lan_http_lab_only",
            "domain": domain,
            "ssl": False,
            "mode": "lan",
            "sample_join": sample,
            "phone_media_safe": url_is_phone_media_safe(sample, lan_ip=ip),
            "lan_ip": ip,
            "port": port if port is not None else voice_room_port(e),
        }

    # public HTTPS (default)
    host = (
        str(e.get("RC_VOICE_JITSI_DOMAIN") or e.get("RC_PUBLIC_DOMAIN") or "").strip()
        or _read_public_domain_file()
    )
    # strip scheme if someone pasted a URL
    if host.startswith("https://"):
        host = host[len("https://") :]
    if host.startswith("http://"):
        host = host[len("http://") :]
    host = host.split("/")[0].strip()
    if not host or is_loopback_host(host.split(":")[0]):
        return {
            "ok": False,
            "reason": "no_public_domain",
            "domain": None,
            "ssl": True,
            "mode": "public",
            "sample_join": None,
        }
    sample = f"https://{host}/AgencyPhonePathProbe"
    return {
        "ok": True,
        "reason": "public_https",
        "domain": host,
        "ssl": True,
        "mode": "public",
        "sample_join": sample,
        "phone_media_safe": url_is_phone_media_safe(sample),
        "scheme": voice_room_public_scheme({**dict(e), "RC_VOICE_ROOM_SCHEME": "https"}),
    }


def ensure_jitsi_domain_matches_lan(
    *,
    base: str | None = None,
    env: Mapping[str, str] | None = None,
    secrets: Mapping[str, str] | None = None,
    lan_ip: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    """
    Align RC Jitsi settings with the desired phone-facing target.

    Name kept for call-site compatibility; default mode is public HTTPS.
    Returns a result dict for logs/tests (no secrets).
    """
    e = env if env is not None else os.environ
    base_url = (base or e.get("RC_BASE") or DEFAULT_BASE).rstrip("/")
    want = desired_jitsi_target(env=e, lan_ip=lan_ip, port=port)
    if not want.get("ok"):
        return {
            "ok": False,
            "reason": want.get("reason") or "no_target",
            "domain": None,
            "ssl": None,
            "changed": False,
            "mode": want.get("mode"),
        }
    want_domain = str(want["domain"])
    want_ssl = bool(want["ssl"])
    try:
        uid, tok = login_admin(base=base_url, secrets=secrets)
        cur_domain, cur_ssl = read_jitsi_domain(
            base=base_url, user_id=uid, auth_token=tok
        )
        changed = False
        if cur_domain != want_domain:
            if not set_jitsi_setting(
                "jitsi_domain",
                want_domain,
                base=base_url,
                user_id=uid,
                auth_token=tok,
            ):
                return {
                    "ok": False,
                    "reason": "set_domain_failed",
                    "domain": cur_domain,
                    "want": want_domain,
                    "ssl": cur_ssl,
                    "changed": False,
                    "mode": want.get("mode"),
                }
            changed = True
        # Normalize ssl to exact want (True for public, False for lan lab)
        if cur_ssl is not want_ssl:
            if not set_jitsi_setting(
                "jitsi_ssl",
                want_ssl,
                base=base_url,
                user_id=uid,
                auth_token=tok,
            ):
                return {
                    "ok": False,
                    "reason": "set_ssl_failed",
                    "domain": want_domain if changed else cur_domain,
                    "want": want_domain,
                    "ssl": cur_ssl,
                    "want_ssl": want_ssl,
                    "changed": changed,
                    "mode": want.get("mode"),
                }
            changed = True
        final_d, final_s = read_jitsi_domain(
            base=base_url, user_id=uid, auth_token=tok
        )
        sample = str(want.get("sample_join") or "")
        media_ok = url_is_phone_media_safe(sample) if sample else False
        settings_ok = final_d == want_domain and final_s is want_ssl
        # For public mode, require phone-media-safe sample URL.
        # For lan lab mode, settings_ok is enough (explicitly not phone-safe).
        if want.get("mode") == "public":
            ok = settings_ok and media_ok
        else:
            ok = settings_ok
        return {
            "ok": ok,
            "reason": "ok" if ok else "verify_mismatch",
            "domain": final_d,
            "ssl": final_s,
            "want": want_domain,
            "want_ssl": want_ssl,
            "mode": want.get("mode"),
            "sample_join": sample,
            "phone_media_safe": media_ok,
            "changed": changed,
            "lan_ip": want.get("lan_ip"),
            "port": want.get("port") or voice_room_port(e),
        }
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as ex:
        return {
            "ok": False,
            "reason": f"error:{type(ex).__name__}",
            "domain": None,
            "ssl": None,
            "want": want_domain,
            "changed": False,
            "mode": want.get("mode"),
        }


def main() -> int:
    r = ensure_jitsi_domain_matches_lan()
    print(json.dumps(r, indent=2))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
