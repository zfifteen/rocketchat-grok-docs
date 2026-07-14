#!/usr/bin/env python3
"""
Live four-agent multi-round collab smoke (issue #2 Phase 4).

Gated: requires RC_LIVE_COLLAB_SMOKE=1. Uses principal RC secrets; never commits them.

Clean-path contract (principal @grok only):
  1. Seed posts only @grok (no peer @ in seed text).
  2. First bot substantive activity is grok (among operators).
  3. Grok reply eventually tags ≥1 peer (hermes/agy/claude).
  4. ≥1 collab-return appears before/around synthesis window.
  5. Lead plain-language DONE language appears (or timeout soft-fail with transcript).

Usage:
  RC_LIVE_COLLAB_SMOKE=1 \\
    RC_SMOKE_ROOM=general \\
    python3 ~/.grok/agency/ops/rocketchat/tests/live_four_agent_collab_smoke.py

Env:
  RC_LIVE_COLLAB_SMOKE   must be 1/true to run
  RC_SMOKE_ROOM          channel name (default: general)
  RC_SMOKE_TIMEOUT_S     wall clock (default: 600)
  RC_SMOKE_LOG           transcript path (default: under /tmp or RC_TEST_SCRATCH)
  RC_URL / secrets       from agency rocketchat.env (principal)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OPS = Path.home() / ".grok" / "agency" / "ops" / "rocketchat"
WAKE = OPS / "wake"
SECRETS = Path.home() / ".grok" / "agency" / "secrets" / "rocketchat.env"

OPERATORS = ("grok", "hermes", "agy", "claude")
PEERS = ("hermes", "agy", "claude")
COLLAB_RETURN = "collab-return"
_DONE_HINT = re.compile(
    r"(this\s+concludes|collaboration\s+complete|goal\s+met|no\s+further\s+handoffs|"
    r"we(?:'re|\s+are)\s+done)",
    re.I,
)
_MENTION = re.compile(r"(?<!\w)@([A-Za-z0-9._-]+)\b")


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _rc_base() -> str:
    envf = _load_env_file(SECRETS)
    url = (
        os.environ.get("RC_URL")
        or envf.get("RC_URL")
        or envf.get("ROCKETCHAT_URL")
        or "http://127.0.0.1:3000"
    ).rstrip("/")
    return url


def _auth() -> tuple[str, str]:
    envf = _load_env_file(SECRETS)
    user = os.environ.get("RC_USER_ID") or envf.get("RC_USER_ID") or envf.get("RC_PRINCIPAL_USER_ID")
    tok = (
        os.environ.get("RC_AUTH_TOKEN")
        or envf.get("RC_AUTH_TOKEN")
        or envf.get("RC_PRINCIPAL_TOKEN")
        or envf.get("RC_TOKEN")
    )
    if not user or not tok:
        raise SystemExit(
            "missing RC_USER_ID / RC_AUTH_TOKEN (principal) in env or "
            f"{SECRETS}"
        )
    return user, tok


def _api(method: str, path: str, body: dict | None = None) -> dict:
    base = _rc_base()
    uid, tok = _auth()
    url = f"{base}{path}"
    data = None
    headers = {
        "X-User-Id": uid,
        "X-Auth-Token": tok,
        "Content-Type": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {path}: {raw[:400]}") from e


def _resolve_room(name: str) -> tuple[str, str]:
    """Return (room_id, room_type_hint). Prefer channel then group."""
    for path, key in (
        (f"/api/v1/channels.info?roomName={name}", "channel"),
        (f"/api/v1/groups.info?roomName={name}", "group"),
    ):
        try:
            data = _api("GET", path)
        except Exception:
            continue
        if data.get("success") and data.get(key):
            rid = data[key].get("_id")
            if rid:
                return str(rid), "c" if key == "channel" else "p"
    raise SystemExit(f"room not found: {name}")


def _post(rid: str, text: str) -> str:
    data = _api("POST", "/api/v1/chat.postMessage", {"roomId": rid, "text": text})
    if not data.get("success"):
        raise RuntimeError(f"post failed: {data}")
    mid = (data.get("message") or {}).get("_id")
    if not mid:
        raise RuntimeError(f"no mid in post response: {data}")
    return str(mid)


def _history(rid: str, count: int = 50) -> list[dict]:
    # channels.messages works for public; groups.messages for private
    for path in (
        f"/api/v1/channels.messages?roomId={rid}&count={count}",
        f"/api/v1/groups.messages?roomId={rid}&count={count}",
    ):
        try:
            data = _api("GET", path)
        except Exception:
            continue
        if data.get("success") and isinstance(data.get("messages"), list):
            return list(data["messages"])
    return []


def _user(m: dict) -> str:
    return ((m.get("u") or {}).get("username") or "").strip().lower()


def _text(m: dict) -> str:
    return (m.get("msg") or "").strip()


def _mentions(text: str) -> set[str]:
    return {m.group(1).lower() for m in _MENTION.finditer(text or "")}


def main() -> int:
    if not _truthy(os.environ.get("RC_LIVE_COLLAB_SMOKE")):
        print(
            "SKIP: set RC_LIVE_COLLAB_SMOKE=1 to run live four-agent collab smoke"
        )
        return 0

    room_name = (os.environ.get("RC_SMOKE_ROOM") or "general").strip()
    timeout_s = int(os.environ.get("RC_SMOKE_TIMEOUT_S") or "600")
    log_path = Path(
        os.environ.get("RC_SMOKE_LOG")
        or os.environ.get("RC_TEST_SCRATCH")
        or "/tmp"
    )
    if log_path.is_dir():
        log_path = log_path / f"live-four-agent-collab-{int(time.time())}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    def log(msg: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        row = f"[{ts}] {msg}"
        print(row)
        lines.append(row)

    rid, rtype = _resolve_room(room_name)
    log(f"room={room_name} rid={rid} type={rtype}")

    seed = (
        "@grok Clean-path multi-round collab smoke (issue #2). "
        "You are lead. Assign @hermes, @agy, and @claude each one short readiness "
        "check (one sentence each is enough). After returns, synthesize and declare "
        "plain-language DONE with zero peer @tags."
    )
    # Contract: seed must not @peer before lead fans out (text may mention names without @).
    assert not (_mentions(seed) & set(PEERS)), "seed must not @peer operators"
    assert "grok" in _mentions(seed)

    seed_mid = _post(rid, seed)
    log(f"seed_mid={seed_mid}")
    seed_ts = time.time()

    first_bot: str | None = None
    saw_peer_tag_from_grok = False
    collab_returns = 0
    saw_done = False
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        msgs = _history(rid, count=80)
        # chronological
        msgs_sorted = sorted(msgs, key=lambda m: m.get("ts") or "")
        after_seed = False
        for m in msgs_sorted:
            mid = m.get("_id")
            if mid == seed_mid:
                after_seed = True
                continue
            if not after_seed:
                continue
            u = _user(m)
            t = _text(m)
            if not t or t == "…":
                continue
            if u in OPERATORS and first_bot is None:
                first_bot = u
                log(f"first_bot_substantive={u} mid={mid}")
            if u == "grok" and (_mentions(t) & set(PEERS)):
                saw_peer_tag_from_grok = True
                log(f"grok_peer_assign mid={mid} peers={sorted(_mentions(t) & set(PEERS))}")
            if COLLAB_RETURN in t.lower() and u in OPERATORS:
                collab_returns += 1
                log(f"collab_return mid={mid} from={u}")
            if u == "grok" and _DONE_HINT.search(t):
                # Prefer DONE without peer tags
                if not (_mentions(t) & set(PEERS)):
                    saw_done = True
                    log(f"lead_done mid={mid}")
                else:
                    log(f"lead_done_language_with_peer_tags mid={mid} (anti-pattern)")
        if first_bot and saw_peer_tag_from_grok and collab_returns >= 1 and saw_done:
            break
        time.sleep(8)

    elapsed = time.time() - seed_ts
    log(
        f"summary first_bot={first_bot} peer_tag={saw_peer_tag_from_grok} "
        f"collab_returns≈{collab_returns} done={saw_done} elapsed_s={elapsed:.0f}"
    )
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"transcript={log_path}")

    ok = True
    failures: list[str] = []
    if first_bot != "grok":
        ok = False
        failures.append(f"first_bot expected grok got {first_bot!r}")
    if not saw_peer_tag_from_grok:
        ok = False
        failures.append("grok never @-tagged a peer")
    if collab_returns < 1:
        ok = False
        failures.append("no collab-return observed")
    if not saw_done:
        # Soft: long model latency may miss DONE; still fail for contract
        ok = False
        failures.append("no clean lead DONE language without peer @tags")

    if ok:
        print("PASS live_four_agent_collab_smoke")
        return 0
    print("FAIL live_four_agent_collab_smoke: " + "; ".join(failures))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
