#!/usr/bin/env python3
"""
NF-SPEC-01 — True voice-in-RC Call pure helpers.

Backend selection, callId single-flight lock, timeout/config parse,
LiveKit room/URL/JWT mint shape, voice-agent worker CLI/env contracts,
sparse DM status policy.

No network I/O. Unit-testable without LiveKit, phone, or Playwright.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

# --- Defaults (OD-V5 / NF-IP-01) ----------------------------------------------

DEFAULT_BACKEND = "playwright"  # pre-cutover; livekit after V4
BACKEND_LIVEKIT = "livekit"
BACKEND_PLAYWRIGHT = "playwright"
VALID_BACKENDS = frozenset({BACKEND_LIVEKIT, BACKEND_PLAYWRIGHT})

DEFAULT_VOICE_MAX_DURATION_S = 1800
DEFAULT_VOICE_IDLE_TIMEOUT_S = 120
DEFAULT_CALL_BUSY_S = 960
DEFAULT_TOKEN_TTL_S = 600
DEFAULT_GREETING = "Hello, Grok speaking."
DEFAULT_LIVEKIT_URL = ""
DEFAULT_AGENT_IDENTITY = "grok"

# Worker brain contract: never Whisper+CLI+say as primary (FR-V4)
BRAIN_VOICE_AGENT = "grok_voice_agent_realtime"
BRAIN_FORBIDDEN_PRIMARY = frozenset({"whisper_cli_tts", "playwright_cascade"})


# --- Env / config -------------------------------------------------------------


def _env(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return env if env is not None else os.environ


def _env_flag(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    v = str(raw).strip().lower()
    if not v:
        return default
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return default


def _int_env(key: str, default: int, env: Mapping[str, str] | None = None) -> int:
    raw = str(_env(env).get(key, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def call_integration_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Master switch for RC Call / voice media plane.

    **Default OFF (retired 2026-07-17).** Principal does not want Call/voice as
    an integration feature. Set ``RC_CALL_ENABLED=1`` only for explicit lab work
    (not production roadmap).
    """
    return _env_flag(_env(env).get("RC_CALL_ENABLED"), default=False)


def call_media_backend(env: Mapping[str, str] | None = None) -> str:
    """
    RC_CALL_MEDIA_BACKEND: livekit | playwright.

    Ignored unless call_integration_enabled(). Default playwright for lab only.
    """
    if not call_integration_enabled(env):
        return BACKEND_PLAYWRIGHT
    raw = str(_env(env).get("RC_CALL_MEDIA_BACKEND", DEFAULT_BACKEND) or "").strip().lower()
    if raw in VALID_BACKENDS:
        return raw
    # aliases
    if raw in ("lk", "voice-agent", "voice_agent", "s2s"):
        return BACKEND_LIVEKIT
    if raw in ("pathc", "path-c", "jitsi", "chromium"):
        return BACKEND_PLAYWRIGHT
    return DEFAULT_BACKEND


def is_livekit_backend(env: Mapping[str, str] | None = None) -> bool:
    return call_media_backend(env) == BACKEND_LIVEKIT


def is_playwright_lab_backend(env: Mapping[str, str] | None = None) -> bool:
    return call_media_backend(env) == BACKEND_PLAYWRIGHT


def voice_max_duration_s(env: Mapping[str, str] | None = None) -> int:
    return max(30, _int_env("RC_VOICE_MAX_DURATION_S", DEFAULT_VOICE_MAX_DURATION_S, env))


def voice_idle_timeout_s(env: Mapping[str, str] | None = None) -> int:
    return max(15, _int_env("RC_VOICE_IDLE_TIMEOUT_S", DEFAULT_VOICE_IDLE_TIMEOUT_S, env))


def call_busy_s(env: Mapping[str, str] | None = None) -> int:
    """Max age for an active call lock before treating as stale."""
    return max(60, _int_env("RC_CALL_BUSY_S", DEFAULT_CALL_BUSY_S, env))


DEFAULT_NO_PEER_TIMEOUT_S = 90
DEFAULT_VOICE_ROOM_PORT = 8090


def call_no_peer_timeout_s(env: Mapping[str, str] | None = None) -> int:
    """
    Exit media worker if no remote peer audio after this many seconds.

    Prevents a stuck bot (phone never joins WebView) from holding the lock forever.
    """
    return max(20, _int_env("RC_CALL_NO_PEER_TIMEOUT_S", DEFAULT_NO_PEER_TIMEOUT_S, env))


def voice_room_port(env: Mapping[str, str] | None = None) -> int:
    return max(1, _int_env("RC_VOICE_ROOM_PORT", DEFAULT_VOICE_ROOM_PORT, env))


def is_loopback_host(host: str | None) -> bool:
    h = (host or "").strip().lower()
    return h in ("127.0.0.1", "localhost", "::1", "0.0.0.0")


def resolve_primary_lan_ipv4(
    *,
    candidates: list[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """
    Best-effort primary LAN IPv4 for phone-facing voice-room URLs.

    Prefer RC_VOICE_ROOM_LAN_IP when set; else first non-loopback candidate;
    else UDP route probe (when candidates is None). Never returns loopback.
    """
    forced = str(_env(env).get("RC_VOICE_ROOM_LAN_IP") or "").strip()
    if forced and not is_loopback_host(forced):
        return forced
    if candidates is not None:
        for c in candidates:
            c = (c or "").strip()
            if c and not is_loopback_host(c) and not c.startswith("169.254."):
                return c
        return ""
    # Live probe (still pure-ish; fails closed to "")
    try:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not is_loopback_host(ip):
            return ip
    except OSError:
        pass
    return ""


def phone_facing_voice_room_netloc(
    *,
    lan_ip: str | None = None,
    port: int | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """
    Host:port for RC Jitsi domain / phone join URLs.

    Never uses 127.0.0.1 — phones cannot open the Mac loopback.
    """
    ip = (lan_ip or "").strip() or resolve_primary_lan_ipv4(env=env)
    if not ip or is_loopback_host(ip):
        raise ValueError("no non-loopback LAN IP for phone-facing voice room")
    p = int(port if port is not None else voice_room_port(env))
    return f"{ip}:{p}"


def voice_room_public_scheme(env: Mapping[str, str] | None = None) -> str:
    """
    Scheme for phone-facing voice-room URLs (http|https).

    Default http (legacy). Set RC_VOICE_ROOM_SCHEME=https when TLS is enabled
    on the voice room — required for iOS mediaDevices.
    """
    raw = str(_env(env).get("RC_VOICE_ROOM_SCHEME") or "").strip().lower()
    if raw in ("https", "http"):
        return raw
    # Implicit https when cert paths are configured
    cert = str(_env(env).get("RC_VOICE_ROOM_CERT") or "").strip()
    key = str(_env(env).get("RC_VOICE_ROOM_KEY") or "").strip()
    if cert and key:
        return "https"
    return "http"


def phone_facing_join_url(
    call_id: str,
    *,
    lan_ip: str | None = None,
    port: int | None = None,
    title_prefix: str = "Agency",
    env: Mapping[str, str] | None = None,
) -> str:
    """Canonical phone-facing join URL (scheme from voice_room_public_scheme)."""
    netloc = phone_facing_voice_room_netloc(lan_ip=lan_ip, port=port, env=env)
    prefix = title_prefix or "Agency"
    cid = (call_id or "").strip()
    if cid.startswith(prefix):
        room = cid
    else:
        room = f"{prefix}{cid}"
    scheme = voice_room_public_scheme(env)
    return f"{scheme}://{netloc}/{room}"


def join_url_host_is_phone_safe(url: str, *, lan_ip: str | None = None) -> bool:
    """
    True when URL host is not loopback (and matches lan_ip when provided).

    WARNING: host-reachable is NOT the same as phone media working.
    iOS still needs a browser secure context (HTTPS) for getUserMedia.
    Use url_is_phone_media_safe for the real Call gate.
    """
    if not url or not str(url).startswith("http"):
        return False
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").strip()
    except Exception:
        return False
    if is_loopback_host(host):
        return False
    if lan_ip and host != lan_ip.strip():
        return False
    return True


def url_is_browser_secure_context(url: str) -> bool:
    """
    Whether a browser treats this page origin as a secure context.

    Mirrors the practical Web rule used by Safari/Chrome for mediaDevices:
    - https: → secure
    - http://localhost / 127.0.0.1 / ::1 → secure (desktop bot path)
    - http://LAN-IP or any other host → NOT secure (phone path fails here)

    Pure string rule — no network. Validated live via Safari probe in
    validate_phone_voice_path.py.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url.strip())
    except Exception:
        return False
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").strip().lower()
    if not scheme or not host:
        return False
    if scheme == "https":
        return True
    if scheme == "http" and is_loopback_host(host):
        return True
    return False


def url_is_phone_media_safe(url: str, *, lan_ip: str | None = None) -> bool:
    """
    Fail-closed gate for the *phone* Call media path.

    Requires all of:
    1. Non-loopback host (phone cannot open Mac 127.0.0.1)
    2. Browser secure context (so mediaDevices.getUserMedia exists)
    3. Optional LAN IP match when provided

    Bot Chromium may still use loopback HTTP via prefer_loopback_nav_url;
    that path is intentionally separate and must NOT green this gate.
    """
    if not join_url_host_is_phone_safe(url, lan_ip=lan_ip):
        return False
    return url_is_browser_secure_context(url)


def assess_phone_join_url(url: str, *, lan_ip: str | None = None) -> dict[str, Any]:
    """
    Structured assessment of a VideoConf join URL for phone media.

    Always returns a dict with ok=False unless every phone media rule holds.
    Used by CLI validators so "Call fixed" cannot be claimed from bot-only checks.
    """
    issues: list[str] = []
    scheme = ""
    host = ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse((url or "").strip())
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").strip()
    except Exception:
        issues.append("unparseable_url")
        return {
            "ok": False,
            "url": url,
            "scheme": scheme,
            "host": host,
            "host_reachable_from_phone": False,
            "secure_context": False,
            "phone_media_safe": False,
            "issues": issues,
        }

    if not url or not scheme:
        issues.append("empty_or_missing_scheme")
    host_ok = join_url_host_is_phone_safe(url, lan_ip=lan_ip)
    secure = url_is_browser_secure_context(url)
    if not host_ok:
        if is_loopback_host(host):
            issues.append("loopback_host_unreachable_from_phone")
        elif lan_ip and host and host != lan_ip.strip():
            issues.append(f"host_mismatch_want_{lan_ip.strip()}")
        else:
            issues.append("host_not_phone_reachable")
    if not secure:
        if scheme == "http" and host and not is_loopback_host(host):
            issues.append(
                "http_non_loopback_not_secure_context_"
                "ios_mediaDevices_undefined"
            )
        else:
            issues.append("not_browser_secure_context")
    if scheme not in ("http", "https"):
        issues.append(f"unsupported_scheme_{scheme or 'none'}")

    media_safe = host_ok and secure and scheme in ("http", "https")
    return {
        "ok": media_safe and not issues,
        "url": url,
        "scheme": scheme,
        "host": host,
        "host_reachable_from_phone": host_ok,
        "secure_context": secure,
        "phone_media_safe": media_safe,
        "issues": issues,
    }


def assess_jitsi_phone_settings(
    domain: str | None,
    ssl_enabled: bool | None,
    *,
    lan_ip: str | None = None,
    port: int | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """
    Assess live RC Jitsi app settings for the phone media path.

    Building the canonical join URL from domain + ssl and running
    assess_phone_join_url. jitsi_ssl=false + LAN domain is the known false-green.
    """
    issues: list[str] = []
    d = (domain or "").strip()
    if not d:
        issues.append("jitsi_domain_missing")
        return {
            "ok": False,
            "domain": domain,
            "ssl": ssl_enabled,
            "inferred_join_url": None,
            "join": None,
            "issues": issues,
        }
    # RC stores domain as host[:port]; scheme comes from jitsi_ssl.
    scheme = "https" if ssl_enabled is True else "http"
    sample_url = f"{scheme}://{d}/AgencyPhonePathProbe"
    join = assess_phone_join_url(sample_url, lan_ip=lan_ip)
    if ssl_enabled is not True:
        issues.append("jitsi_ssl_not_true_phone_needs_https")
    for i in list(join.get("issues") or []):
        if i not in issues:
            issues.append(i)
    ok = bool(join.get("phone_media_safe")) and ssl_enabled is True
    return {
        "ok": ok,
        "domain": d,
        "ssl": ssl_enabled,
        "inferred_join_url": sample_url,
        "join": join,
        "issues": [] if ok else issues,
        "want_lan": (
            phone_facing_voice_room_netloc(lan_ip=lan_ip, port=port, env=env)
            if (lan_ip or resolve_primary_lan_ipv4(env=env))
            else None
        ),
    }


def rewrite_loopback_join_url_to_lan(
    url: str,
    *,
    lan_ip: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """
    If RC returned a loopback voice-room URL, rewrite host to current LAN IP.

    Phone clients cannot use 127.0.0.1; bot may still prefer_loopback for nav.
    """
    if not url:
        return url
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not is_loopback_host(host):
            return url
        ip = (lan_ip or "").strip() or resolve_primary_lan_ipv4(env=env)
        if not ip or is_loopback_host(ip):
            return url
        port = parsed.port
        netloc = f"{ip}:{port}" if port else ip
        return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        return url


def voice_greeting(env: Mapping[str, str] | None = None) -> str:
    g = str(_env(env).get("RC_VOICE_GREETING") or _env(env).get("RC_CALL_GREETING") or "").strip()
    return g or DEFAULT_GREETING


def livekit_url(env: Mapping[str, str] | None = None) -> str:
    return str(
        _env(env).get("RC_LIVEKIT_URL")
        or _env(env).get("LIVEKIT_URL")
        or DEFAULT_LIVEKIT_URL
    ).strip()


def livekit_api_key(env: Mapping[str, str] | None = None) -> str:
    return str(
        _env(env).get("RC_LIVEKIT_API_KEY")
        or _env(env).get("LIVEKIT_API_KEY")
        or ""
    ).strip()


def livekit_api_secret(env: Mapping[str, str] | None = None) -> str:
    return str(
        _env(env).get("RC_LIVEKIT_API_SECRET")
        or _env(env).get("LIVEKIT_API_SECRET")
        or ""
    ).strip()


def xai_api_key(env: Mapping[str, str] | None = None) -> str:
    return str(_env(env).get("XAI_API_KEY") or _env(env).get("RC_XAI_API_KEY") or "").strip()


def token_ttl_s(env: Mapping[str, str] | None = None) -> int:
    return max(60, _int_env("RC_LIVEKIT_TOKEN_TTL_S", DEFAULT_TOKEN_TTL_S, env))


def livekit_configured(env: Mapping[str, str] | None = None) -> bool:
    return bool(livekit_url(env) and livekit_api_key(env) and livekit_api_secret(env))


# --- Room identity ------------------------------------------------------------


def room_name_from_call_id(call_id: str, *, prefix: str = "Agency") -> str:
    """
    Derive LiveKit room name from RC VideoConf callId (FR-V2).

    Mirrors historical Jitsi/voice_room path shape: Agency{callId}.
    """
    cid = (call_id or "").strip()
    if not cid:
        raise ValueError("call_id required for room name")
    # strip accidental path / query
    cid = cid.split("/")[-1].split("?")[0]
    if cid.lower().startswith(prefix.lower()):
        return cid
    return f"{prefix}{cid}"


# --- LiveKit JWT (stdlib HS256) -----------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_livekit_access_token(
    *,
    api_key: str,
    api_secret: str,
    identity: str,
    room: str,
    ttl_s: int = DEFAULT_TOKEN_TTL_S,
    now: float | None = None,
    can_publish: bool = True,
    can_subscribe: bool = True,
    name: str | None = None,
) -> str:
    """
    Mint a short-lived LiveKit access JWT (SR-V2).

    Token is HS256 with video grants for a single room. Secrets never go into
    the token payload beyond the signing step (secret is only the HMAC key).
    """
    if not api_key or not api_secret:
        raise ValueError("api_key and api_secret required")
    if not identity or not room:
        raise ValueError("identity and room required")
    t0 = int(now if now is not None else time.time())
    ttl = max(60, int(ttl_s))
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "iss": api_key,
        "sub": identity,
        "nbf": t0 - 10,
        "exp": t0 + ttl,
        "video": {
            "roomJoin": True,
            "room": room,
            "canPublish": bool(can_publish),
            "canSubscribe": bool(can_subscribe),
            "canPublishData": True,
        },
    }
    if name:
        payload["name"] = name
    h = _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{h}.{p}".encode("ascii")
    sig = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


def livekit_join_url(
    ws_url: str,
    token: str,
    *,
    room: str | None = None,
) -> str:
    """
    Build a join material string for clients/workers.

    LiveKit clients take (url, token) separately; this helper never puts the
    API secret in the query string — only the short-lived JWT may appear.
    """
    base = (ws_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("livekit ws_url required")
    if not token:
        raise ValueError("token required")
    # Ensure secret-looking material is not a raw API secret (heuristic)
    if "API" in token and len(token) < 40 and "." not in token:
        raise ValueError("token does not look like a JWT")
    # Return structured form; workers parse via parse_join_material
    mat = {"url": base, "token": token}
    if room:
        mat["room"] = room
    return json.dumps(mat, separators=(",", ":"))


def parse_join_material(material: str) -> dict[str, str]:
    """Parse join material JSON from livekit_join_url."""
    data = json.loads(material)
    if not isinstance(data, dict) or "url" not in data or "token" not in data:
        raise ValueError("invalid join material")
    return {k: str(v) for k, v in data.items()}


def token_contains_raw_secret(token: str, api_secret: str) -> bool:
    """True if the JWT incorrectly embeds the raw API secret (must never)."""
    if not api_secret or not token:
        return False
    return api_secret in token


# --- Call lock (single-flight per callId) -------------------------------------


@dataclass
class CallLockMeta:
    call_id: str
    room_id: str = ""
    backend: str = DEFAULT_BACKEND
    pid: int | None = None
    started_at: str = ""
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "room_id": self.room_id,
            "backend": self.backend,
            "pid": self.pid,
            "started_at": self.started_at,
        }


def default_call_lock_path(log_dir: Path | None = None) -> Path:
    base = log_dir or (Path.home() / "logs" / "rocketchat-dm-wake")
    return Path(base) / "call-bot.lock"


def read_call_lock(lock_path: Path) -> CallLockMeta | None:
    if not lock_path.is_file():
        return None
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    cid = str(raw.get("call_id") or "")
    if not cid:
        return None
    pid = raw.get("pid")
    return CallLockMeta(
        call_id=cid,
        room_id=str(raw.get("room_id") or ""),
        backend=str(raw.get("backend") or DEFAULT_BACKEND),
        pid=int(pid) if isinstance(pid, int) else None,
        started_at=str(raw.get("started_at") or ""),
        path=str(lock_path),
    )


def pid_is_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def should_supersede_lock_for_new_call(
    meta: CallLockMeta | None,
    new_call_id: str,
) -> bool:
    """
    True when a new principal Call should terminate prior media.

    Different call_id while a lock exists → supersede so Call never stuck 'busy'.
    """
    if meta is None or not new_call_id:
        return False
    return meta.call_id != new_call_id


def call_lock_is_busy(
    lock_path: Path,
    *,
    now: float | None = None,
    busy_s: int | None = None,
    env: Mapping[str, str] | None = None,
    kill_check: Any = None,
) -> bool:
    """
    True if a live worker holds the lock (FR-V7).

    Stale locks (dead PID or aged out) are not busy — caller may clear them.
    """
    meta = read_call_lock(lock_path)
    if meta is None:
        return False
    age_limit = busy_s if busy_s is not None else call_busy_s(env)
    try:
        mtime = lock_path.stat().st_mtime
    except OSError:
        return False
    t0 = now if now is not None else time.time()
    age = t0 - mtime
    check = kill_check or pid_is_alive
    # No PID (or non-int) cannot hold a live worker — treat as not busy.
    if meta.pid is None or not isinstance(meta.pid, int) or meta.pid <= 0:
        return False
    alive = bool(check(meta.pid))
    return alive and age < age_limit


def clear_stale_call_lock(
    lock_path: Path,
    *,
    now: float | None = None,
    busy_s: int | None = None,
    env: Mapping[str, str] | None = None,
    kill_check: Any = None,
) -> bool:
    """Clear lock if missing, dead, or aged out. Returns True if cleared/absent."""
    if not lock_path.is_file():
        return True
    if call_lock_is_busy(
        lock_path, now=now, busy_s=busy_s, env=env, kill_check=kill_check
    ):
        return False
    try:
        lock_path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def acquire_call_lock(
    lock_path: Path,
    *,
    call_id: str,
    room_id: str = "",
    backend: str = DEFAULT_BACKEND,
    pid: int | None = None,
    started_at: str = "",
    now: float | None = None,
    busy_s: int | None = None,
    env: Mapping[str, str] | None = None,
    kill_check: Any = None,
) -> bool:
    """
    Acquire single-flight call lock for callId.

    Rejects if another live worker holds any call lock (one concurrent call).
    Also rejects re-acquire of same call_id while busy.
    """
    if not call_id:
        return False
    clear_stale_call_lock(
        lock_path, now=now, busy_s=busy_s, env=env, kill_check=kill_check
    )
    if call_lock_is_busy(
        lock_path, now=now, busy_s=busy_s, env=env, kill_check=kill_check
    ):
        return False
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    meta = CallLockMeta(
        call_id=call_id,
        room_id=room_id,
        backend=backend,
        pid=pid,
        started_at=started_at,
        path=str(lock_path),
    )
    try:
        lock_path.write_text(
            json.dumps(meta.to_dict(), indent=None) + "\n", encoding="utf-8"
        )
        return True
    except OSError:
        return False


def update_call_lock_pid(lock_path: Path, pid: int) -> bool:
    meta = read_call_lock(lock_path)
    if meta is None:
        return False
    meta.pid = int(pid)
    try:
        lock_path.write_text(
            json.dumps(meta.to_dict(), indent=None) + "\n", encoding="utf-8"
        )
        return True
    except OSError:
        return False


def release_call_lock(
    lock_path: Path,
    *,
    call_id: str | None = None,
    only_if_call_id: bool = False,
) -> bool:
    """Release lock. If only_if_call_id, require matching call_id."""
    if not lock_path.is_file():
        return True
    if only_if_call_id and call_id:
        meta = read_call_lock(lock_path)
        if meta and meta.call_id != call_id:
            return False
    try:
        lock_path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


# --- Worker CLI / env contracts -----------------------------------------------


@dataclass
class VoiceWorkerPlan:
    """Planned voice-agent worker invocation (argv + env contract)."""

    argv: list[str] = field(default_factory=list)
    env_keys: list[str] = field(default_factory=list)
    call_id: str = ""
    room_id: str = ""
    room_name: str = ""
    livekit_room: str = ""
    brain: str = BRAIN_VOICE_AGENT
    max_duration_s: int = DEFAULT_VOICE_MAX_DURATION_S
    idle_timeout_s: int = DEFAULT_VOICE_IDLE_TIMEOUT_S
    greeting: str = DEFAULT_GREETING
    uses_playwright: bool = False
    uses_whisper_cli_tts_primary: bool = False


def voice_agent_worker_path(agency: Path | None = None) -> Path:
    root = agency or (Path.home() / ".grok" / "agency")
    return root / "ops" / "rocketchat" / "call" / "voice_agent_worker.py"


def build_voice_worker_argv(
    *,
    call_id: str,
    room_id: str,
    room_name: str = "",
    python_bin: str = "python3",
    worker_path: Path | str | None = None,
    livekit_url_override: str | None = None,
    validate_only: bool = False,
    env: Mapping[str, str] | None = None,
) -> VoiceWorkerPlan:
    """
    Build argv for voice_agent_worker (FR-V4 Realtime path, not Playwright).

    Worker owns media join + cleanup; receives call/room ids.
    """
    if not call_id:
        raise ValueError("call_id required")
    wp = Path(worker_path) if worker_path else voice_agent_worker_path()
    lk_room = room_name_from_call_id(call_id)
    argv = [
        python_bin,
        str(wp),
        "--call-id",
        call_id,
        "--room-id",
        room_id,
        "--room-name",
        room_name or "",
        "--livekit-room",
        lk_room,
        "--max-duration-s",
        str(voice_max_duration_s(env)),
        "--idle-timeout-s",
        str(voice_idle_timeout_s(env)),
        "--greeting",
        voice_greeting(env),
    ]
    url = livekit_url_override if livekit_url_override is not None else livekit_url(env)
    if url:
        argv.extend(["--livekit-url", url])
    if validate_only:
        argv.append("--validate-only")
    return VoiceWorkerPlan(
        argv=argv,
        env_keys=[
            "RC_LIVEKIT_URL",
            "RC_LIVEKIT_API_KEY",
            "RC_LIVEKIT_API_SECRET",
            "XAI_API_KEY",
            "RC_VOICE_MAX_DURATION_S",
            "RC_VOICE_IDLE_TIMEOUT_S",
            "RC_VOICE_GREETING",
        ],
        call_id=call_id,
        room_id=room_id,
        room_name=room_name or "",
        livekit_room=lk_room,
        brain=BRAIN_VOICE_AGENT,
        max_duration_s=voice_max_duration_s(env),
        idle_timeout_s=voice_idle_timeout_s(env),
        greeting=voice_greeting(env),
        uses_playwright=False,
        uses_whisper_cli_tts_primary=False,
    )


def build_playwright_bot_argv(
    *,
    call_id: str,
    room_id: str,
    room_name: str = "",
    python_bin: str = "python3",
    bot_path: Path | str | None = None,
    agency: Path | None = None,
) -> list[str]:
    """Lab Path C argv (explicit playwright backend only)."""
    root = agency or (Path.home() / ".grok" / "agency")
    bp = Path(bot_path) if bot_path else root / "ops" / "rocketchat" / "call" / "rc_call_bot.py"
    return [
        python_bin,
        str(bp),
        "--call-id",
        call_id,
        "--room-id",
        room_id,
        "--room-name",
        room_name or "",
    ]


def select_spawn_plan(
    *,
    call_id: str,
    room_id: str,
    room_name: str = "",
    python_bin: str = "python3",
    env: Mapping[str, str] | None = None,
    agency: Path | None = None,
) -> tuple[str, list[str], VoiceWorkerPlan | None]:
    """
    Choose LiveKit worker vs Playwright bot from RC_CALL_MEDIA_BACKEND.

    Returns (backend, argv, voice_plan_or_none).
    """
    backend = call_media_backend(env)
    if backend == BACKEND_LIVEKIT:
        plan = build_voice_worker_argv(
            call_id=call_id,
            room_id=room_id,
            room_name=room_name,
            python_bin=python_bin,
            worker_path=voice_agent_worker_path(agency),
            env=env,
        )
        return backend, list(plan.argv), plan
    argv = build_playwright_bot_argv(
        call_id=call_id,
        room_id=room_id,
        room_name=room_name,
        python_bin=python_bin,
        agency=agency,
    )
    return backend, argv, None


# --- Sparse status (FR-V8) ----------------------------------------------------

STATUS_CONNECTING = "connecting"
STATUS_FAILED = "failed"
STATUS_ENDED = "ended"
VALID_STATUS = frozenset({STATUS_CONNECTING, STATUS_FAILED, STATUS_ENDED})


def format_call_status_message(
    phase: str,
    *,
    call_id: str = "",
    detail: str = "",
    greeting: str | None = None,
) -> str:
    """
    Sparse DM status only — no per-turn transcript flood (FR-V8).

    Phases: connecting | failed | ended.
    """
    p = (phase or "").strip().lower()
    if p not in VALID_STATUS:
        raise ValueError(f"invalid status phase: {phase!r}")
    cid = (call_id or "").strip()
    tail = f" (`{cid[:12]}…`)" if len(cid) > 12 else (f" (`{cid}`)" if cid else "")
    if p == STATUS_CONNECTING:
        g = greeting if greeting is not None else DEFAULT_GREETING
        return (
            f"**Call** connecting{tail} — you should hear: \"{g}\" "
            "after media connects."
        )
    if p == STATUS_FAILED:
        d = (detail or "media worker failed").strip()[:200]
        return f"**Call** failed{tail}: {d}"
    # ended
    d = (detail or "").strip()[:120]
    if d:
        return f"**Call** ended{tail} — {d}"
    return f"**Call** ended{tail}."


def status_must_not_contain_secrets(text: str, secrets: list[str]) -> bool:
    """Return True if none of the secret strings appear in status text."""
    body = text or ""
    for s in secrets:
        if s and s in body:
            return False
    return True


def worker_brain_is_voice_agent(plan: VoiceWorkerPlan) -> bool:
    return (
        plan.brain == BRAIN_VOICE_AGENT
        and not plan.uses_playwright
        and not plan.uses_whisper_cli_tts_primary
    )


# --- Hangup / terminate (FR-V6 cleanup ≤ 15 s) ---------------------------------


DEFAULT_CLEANUP_WINDOW_S = 15


def terminate_call_worker(
    lock_path: Path,
    *,
    call_id: str | None = None,
    signal_num: int | None = None,
    kill_fn: Any = None,
    wait_s: float = 0.0,
    poll_fn: Any = None,
) -> dict[str, Any]:
    """
    Signal the worker holding the call lock (SIGTERM) and release the lock.

    Returns a result dict for logs/tests:
      {ok, pid, signalled, lock_released, reason}

    Pure enough for contract tests with injectable kill_fn / poll_fn.
    """
    import signal as _signal

    sig = signal_num if signal_num is not None else _signal.SIGTERM
    meta = read_call_lock(lock_path)
    if meta is None:
        return {
            "ok": True,
            "pid": None,
            "signalled": False,
            "lock_released": True,
            "reason": "no_lock",
        }
    if call_id and meta.call_id != call_id:
        return {
            "ok": False,
            "pid": meta.pid,
            "signalled": False,
            "lock_released": False,
            "reason": "call_id_mismatch",
        }
    pid = meta.pid
    signalled = False
    if isinstance(pid, int) and pid > 0:
        try:
            if kill_fn is not None:
                kill_fn(pid, sig)
            else:
                os.kill(pid, sig)
            signalled = True
        except OSError:
            signalled = False
    if wait_s > 0 and poll_fn is not None:
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if not poll_fn(pid):
                break
            time.sleep(0.05)
    released = release_call_lock(
        lock_path, call_id=meta.call_id, only_if_call_id=bool(call_id)
    )
    if not call_id:
        released = release_call_lock(lock_path) or released
    return {
        "ok": True,
        "pid": pid,
        "signalled": signalled,
        "lock_released": bool(released) or not lock_path.is_file(),
        "reason": "hangup",
        "call_id": meta.call_id,
        "backend": meta.backend,
    }


def is_videoconf_end_message(msg: Mapping[str, Any] | None) -> bool:
    """
    Detect hangup / call-ended system messages when RC provides them.

    Heuristic: t=videoconf-end, or msg text contains call ended/hangup, or
    blocks with type video_conf_end. Best-effort; operator also times out locks.
    """
    if not msg:
        return False
    t = str(msg.get("t") or "").strip().lower()
    if t in {"videoconf-end", "videoconf_end", "call-ended", "call_ended"}:
        return True
    text = str(msg.get("msg") or "").strip().lower()
    if any(k in text for k in ("call ended", "hung up", "left the call", "call finished")):
        return True
    blocks = msg.get("blocks")
    if isinstance(blocks, list):
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bt = str(b.get("type") or "").lower()
            if "end" in bt and "conf" in bt:
                return True
    return False
