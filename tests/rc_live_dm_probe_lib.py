#!/usr/bin/env python3
"""
Principal → grok Rocket.Chat DM live probe helpers.

Posts as principal via REST (not Safari), polls im.history for a final grok
reply, and classifies FINAL_ERR cancel shells using the shipped wake_telemetry
formatter so assertions stay aligned with the operator's real error text.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:3000"
DEFAULT_SECRETS = Path.home() / ".grok" / "agency" / "secrets" / "rocketchat.env"
OPS_WAKE = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"


def load_env(path: Path) -> dict[str, str]:
    """Parse KEY=value secrets file (same shape as wake_lib.load_env)."""
    out: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _import_wake_telemetry():
    """Load shipped wake_telemetry from the live operator tree."""
    import importlib.util
    import sys

    path = OPS_WAKE / "wake_telemetry.py"
    if not path.is_file():
        raise FileNotFoundError(f"missing shipped wake_telemetry: {path}")
    name = "rc_wake_telemetry_shipped"
    if name in sys.modules:
        return sys.modules[name]
    # Must be on sys.path so sibling ops imports resolve if any appear later.
    wake_dir = str(OPS_WAKE)
    if wake_dir not in sys.path:
        sys.path.insert(0, wake_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses can resolve forward annotations.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def final_err_template_text() -> str:
    """Exact FINAL_ERR shell produced by the shipped operator for Cancelled."""
    tel = _import_wake_telemetry()
    return tel.format_final_err(
        rc=0,
        stop_reason="Cancelled",
        approval_mode="restricted",
        log_basename="wake-run-example.log",
    )


def is_final_err_body(body: str) -> bool:
    """
    True if body matches the operator's cancel / empty-reply FINAL_ERR pattern.

    Uses substrings that the shipped format_final_err always emits for Cancelled.
    """
    text = body or ""
    # Fast path: fixed phrases from wake_telemetry.format_final_err (Cancelled).
    if "stopReason: Cancelled" in text:
        return True
    if "Wake ended without a reply file" in text:
        return True
    if "Wake did not produce a reply file" in text:
        return True
    return False


def is_streaming_meta_body(body: str) -> bool:
    """True for Thinking… / Working… NF-02 intermediate bubbles (not final)."""
    b = (body or "").strip()
    if not b:
        return True
    low = b.lower()
    if low.startswith("thinking"):
        return True
    if b.startswith("Working"):
        return True
    if "• phase:" in b or "• elapsed:" in b:
        return True
    if "RUNNING_META" in b:
        return True
    return False


def api(
    method: str,
    path: str,
    *,
    base: str = DEFAULT_BASE,
    token: str | None = None,
    uid: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token and uid:
        headers["X-Auth-Token"] = token
        headers["X-User-Id"] = uid
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def login(
    username: str,
    password: str,
    *,
    base: str = DEFAULT_BASE,
) -> tuple[str, str]:
    d = api("POST", "/api/v1/login", base=base, body={"user": username, "password": password})
    if d.get("status") != "success":
        raise RuntimeError(f"login failed for {username!r}: status={d.get('status')}")
    data = d.get("data") or {}
    return str(data["authToken"]), str(data["userId"])


def find_or_create_principal_grok_dm(
    token: str,
    uid: str,
    *,
    base: str = DEFAULT_BASE,
    principal: str = "principal",
    operator: str = "grok",
) -> str:
    d = api("GET", "/api/v1/im.list", base=base, token=token, uid=uid)
    if not d.get("success"):
        raise RuntimeError(f"im.list failed: {d}")
    for im in d.get("ims") or []:
        names = set(im.get("usernames") or [])
        if principal in names and operator in names:
            return str(im["_id"])
        users = im.get("users") or []
        unames = {u.get("username") for u in users if isinstance(u, dict)}
        if principal in unames and operator in unames:
            return str(im["_id"])
    created = api(
        "POST",
        "/api/v1/im.create",
        base=base,
        token=token,
        uid=uid,
        body={"username": operator},
    )
    if not created.get("success"):
        raise RuntimeError(f"im.create failed: {created}")
    room = created.get("room") or {}
    rid = room.get("_id")
    if not rid:
        raise RuntimeError(f"im.create missing room id: {created}")
    return str(rid)


def post_principal_probe(
    *,
    marker: str | None = None,
    base: str = DEFAULT_BASE,
    secrets_path: Path = DEFAULT_SECRETS,
) -> dict[str, Any]:
    """
    Authenticate as principal and post a unique DM probe to grok.

    Returns a redacted record (no passwords/tokens).
    """
    secrets = load_env(secrets_path)
    p_user = secrets["ROCKETCHAT_ADMIN_USERNAME"]
    p_pass = secrets["ROCKETCHAT_ADMIN_PASSWORD"]
    mark = marker or f"RC_PROBE_{int(time.time())}"
    probe_text = (
        f"{mark}\n"
        "Reply with exactly one line: PROBE_OK (nothing else). "
        "Write that to the reply file only."
    )
    p_tok, p_uid = login(p_user, p_pass, base=base)
    room_id = find_or_create_principal_grok_dm(p_tok, p_uid, base=base)
    post = api(
        "POST",
        "/api/v1/chat.postMessage",
        base=base,
        token=p_tok,
        uid=p_uid,
        body={"roomId": room_id, "text": probe_text},
    )
    if not post.get("success"):
        raise RuntimeError(f"chat.postMessage failed: {post}")
    msg = post.get("message") or {}
    return {
        "marker": mark,
        "probe_text_prefix": probe_text.split("\n", 1)[0],
        "room_id": room_id,
        "principal_message_id": msg.get("_id"),
        "principal_username": p_user,
        "ts": time.time(),
        "success": True,
        "_auth": (p_tok, p_uid),  # caller-internal; strip before writing artifacts
    }


def poll_final_grok_reply(
    *,
    room_id: str,
    principal_message_id: str,
    token: str,
    uid: str,
    base: str = DEFAULT_BASE,
    timeout_s: float = 300,
    interval_s: float = 3,
) -> dict[str, Any]:
    """
    Poll DM history until grok posts a non-streaming final body after the probe.

    Returns dict with final_body, final_mid, ok, is_final_err, timed_out.
    """
    deadline = time.time() + timeout_s
    final_body: str | None = None
    final_mid: str | None = None
    while time.time() < deadline:
        hist = api(
            "GET",
            f"/api/v1/im.history?roomId={room_id}&count=30",
            base=base,
            token=token,
            uid=uid,
        )
        messages = hist.get("messages") or []
        p_idx = next(
            (i for i, m in enumerate(messages) if m.get("_id") == principal_message_id),
            None,
        )
        if p_idx is None:
            time.sleep(interval_s)
            continue
        for m in messages[:p_idx]:
            if (m.get("u") or {}).get("username") != "grok":
                continue
            body = (m.get("msg") or "").strip()
            if is_streaming_meta_body(body):
                continue
            final_body = body
            final_mid = m.get("_id")
            break
        if final_body is not None:
            break
        time.sleep(interval_s)

    err = is_final_err_body(final_body or "")
    ok = bool(final_body) and not err
    return {
        "final_body": final_body,
        "final_grok_message_id": final_mid,
        "is_final_err": err,
        "ok": ok,
        "timed_out": final_body is None,
    }


def run_live_dm_probe(
    *,
    base: str | None = None,
    secrets_path: Path | None = None,
    timeout_s: float = 300,
    marker: str | None = None,
) -> dict[str, Any]:
    """
    End-to-end principal→grok DM probe against a live Rocket.Chat.

    Requires RC up + operator healthy enough to wake. Does not print secrets.
    """
    base_url = (base or os.environ.get("RC_BASE") or DEFAULT_BASE).rstrip("/")
    secrets = secrets_path or Path(
        os.environ.get("RC_SECRETS_PATH") or str(DEFAULT_SECRETS)
    )
    send = post_principal_probe(marker=marker, base=base_url, secrets_path=secrets)
    token, uid = send.pop("_auth")
    poll = poll_final_grok_reply(
        room_id=send["room_id"],
        principal_message_id=send["principal_message_id"],
        token=token,
        uid=uid,
        base=base_url,
        timeout_s=timeout_s,
    )
    return {"send": send, "reply": poll}


def rc_reachable(base: str = DEFAULT_BASE, timeout: float = 5) -> bool:
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/api/info", timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return bool(d.get("success") or d.get("version"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False
