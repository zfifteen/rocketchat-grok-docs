#!/usr/bin/env python3
"""
Poll principal → grok Rocket.Chat DMs. On new messages, wake headless Grok to reply.

First successful poll seeds last-seen without waking (avoids replaying history).
Launchd runs this every ~20s. Safe to run manually: python3 rc_dm_poll.py [--once]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import wake_lib
from wake_lib import (
    load_env,
    load_state as _lib_load_state,
    save_state as _lib_save_state,
    new_principal_messages,
    seed_state_from_messages,
    acquire_wake_lock as _lib_acquire,
    release_wake_lock as _lib_release,
    build_wake_argv,
    resolve_approval_mode,
    get_room_session_id,
    set_room_session_id,
    get_room_cwd,
    set_room_cwd,
    extract_session_id_from_output,
    resolve_project_cwd,
)

AGENCY = Path.home() / ".grok" / "agency"
SECRETS = AGENCY / "secrets" / "rocketchat.env"
WAKE_DIR = AGENCY / "ops" / "rocketchat" / "wake"
STATE_PATH = WAKE_DIR / "state.json"
PROMPT_TEMPLATE = WAKE_DIR / "reply_prompt.txt"
LOCK_DIR = Path.home() / "logs" / "rocketchat-dm-wake" / "wake.lock.d"
LOG_DIR = Path.home() / "logs" / "rocketchat-dm-wake"
LOG_PATH = LOG_DIR / "poll.log"

BASE_URL = "http://127.0.0.1:3000"
OPERATOR = "grok"
PRINCIPAL = "principal"
POLL_TIMEOUT_S = 8
GROK_BIN = os.environ.get("GROK_BIN", str(Path.home() / ".local" / "bin" / "grok"))
MAX_TURNS = os.environ.get("RC_WAKE_MAX_TURNS", "100")


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def api(method: str, path: str, token: str | None = None, uid: str | None = None, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token and uid:
        headers["X-Auth-Token"] = token
        headers["X-User-Id"] = uid
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=POLL_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code} {path}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"unreachable Rocket.Chat ({path}): {e}") from e


def login(username: str, password: str) -> tuple[str, str]:
    d = api("POST", "/api/v1/login", body={"user": username, "password": password})
    if d.get("status") != "success":
        raise RuntimeError(f"login failed for {username}: {d}")
    data = d["data"]
    return data["authToken"], data["userId"]


def principal_dm_room(token: str, uid: str) -> str:
    d = api("GET", "/api/v1/im.list", token=token, uid=uid)
    if not d.get("success"):
        raise RuntimeError(f"im.list failed: {d}")
    for im in d.get("ims") or []:
        users = set(im.get("usernames") or [])
        if PRINCIPAL in users and OPERATOR in users:
            return im["_id"]
    raise RuntimeError("no principal↔grok DM room found")


def fetch_history(token: str, uid: str, room_id: str, count: int = 25) -> list[dict]:
    d = api("GET", f"/api/v1/im.history?roomId={room_id}&count={count}", token=token, uid=uid)
    if not d.get("success"):
        raise RuntimeError(f"im.history failed: {d}")
    # API returns newest first; reverse to chronological
    return list(reversed(d.get("messages") or []))


def load_state() -> dict:
    return _lib_load_state(STATE_PATH)


def save_state(state: dict) -> None:
    _lib_save_state(state, STATE_PATH)


def acquire_wake_lock() -> bool:
    ok = _lib_acquire(LOCK_DIR)
    if ok:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    return ok


def release_wake_lock() -> None:
    _lib_release(LOCK_DIR)


def notify_macos(title: str, body: str) -> None:
    # Escape for AppleScript string
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = f'display notification "{esc(body[:180])}" with title "{esc(title)}"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
    except (subprocess.SubprocessError, OSError) as e:
        log(f"notification failed: {e}")


def build_prompt(
    new_msgs: list[dict],
    room_id: str,
    *,
    project_cwd: str = "",
    project_reason: str = "",
) -> str:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    lines = [
        f"Room id: {room_id}",
        f"Room name: dm:principal",
        f"Project cwd: {project_cwd or str(AGENCY)}",
        f"Project resolve: {project_reason or 'dm'}",
        f"Base URL: {BASE_URL}",
        f"Operator user: {OPERATOR}",
        f"Principal user: {PRINCIPAL}",
        "You were started with --cwd set to Project cwd.",
        # Standing principal voice: every room (incl. DM). See reply_prompt Voice.
        "Voice (ALL rooms): chat-message prose for a person — not log lines "
        "or ops-ticket dumps; short paragraphs; lead with the answer; "
        "no dense tables/status grids unless the user asked for a table.",
        f"New principal message count: {len(new_msgs)}",
        "New messages (chronological):",
    ]
    for m in new_msgs:
        ts = m.get("ts", "")
        text = (m.get("msg") or "").replace("\n", " ")
        lines.append(f"- [{ts}] {text}")
    context = "\n".join(lines)
    return template.replace("{{CONTEXT}}", context)


def wake_grok(
    prompt: str,
    *,
    room_id: str | None = None,
    resume_session_id: str | None = None,
    project_cwd: str | None = None,
) -> tuple[int, str | None]:
    """Headless Grok; resume per-room session; cwd is project or agency for DMs."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    prompt_path = LOG_DIR / f"wake-prompt-{ts}.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    log_file = LOG_DIR / f"wake-run-{ts}.log"
    cwd = project_cwd or str(AGENCY)

    def _once(resume: str | None, log_path: Path) -> tuple[int, str | None, str]:
        # Poll path is DM-only; same IMP-01 approval policy as the operator.
        approval_mode = resolve_approval_mode(room_type="d", room_name="dm:principal")
        cmd = build_wake_argv(
            prompt_path,
            grok_bin=GROK_BIN,
            cwd=cwd,
            max_turns=MAX_TURNS,
            resume_session_id=resume,
            output_format="json",
            approval_mode=approval_mode,
        )
        log(
            f"waking grok approval_mode={approval_mode} resume={resume or 'NEW'} "
            f"cwd={cwd}: {' '.join(cmd[:10])} ..."
        )
        env = os.environ.copy()
        env["PATH"] = (
            f"{Path.home() / '.local' / 'bin'}:"
            f"{Path.home() / '.grok' / 'bin'}:"
            f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{env.get('PATH', '')}"
        )
        env["HOME"] = str(Path.home())
        with log_path.open("w", encoding="utf-8") as out:
            out.write(f"cmd: {cmd}\n\n")
            out.flush()
            proc = subprocess.Popen(
                cmd,
                stdout=out,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=cwd,
            )
            try:
                rc = proc.wait(timeout=600)
            except subprocess.TimeoutExpired:
                proc.kill()
                log(f"wake timed out after 600s; log={log_path}")
                try:
                    text = log_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                return 124, None, text
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        sid = extract_session_id_from_output(text)
        return rc, sid, text

    rc, sid, text = _once(resume_session_id, log_file)
    resume_failed = resume_session_id and rc != 0 and (
        "Couldn't start session" in text
        or "session not found" in text.lower()
        or "failed to resume" in text.lower()
        or "unknown session" in text.lower()
    )
    if resume_failed:
        log(f"resume failed for {resume_session_id}; starting new session room={room_id}")
        rc, sid, text = _once(None, LOG_DIR / f"wake-run-{ts}-retry.log")
    if not sid and resume_session_id and rc == 0:
        sid = resume_session_id
    log(f"wake finished rc={rc} session={sid or 'none'} cwd={cwd} log={log_file}")
    return rc, sid


def poll_once() -> int:
    """Return 0 ok, 1 soft skip, 2 hard error."""
    try:
        secrets = load_env(SECRETS)
    except FileNotFoundError as e:
        log(str(e))
        return 2

    password = secrets.get("ROCKETCHAT_OPERATOR_PASSWORD")
    username = secrets.get("ROCKETCHAT_OPERATOR_USERNAME", OPERATOR)
    if not password:
        log("ROCKETCHAT_OPERATOR_PASSWORD missing")
        return 2

    try:
        token, uid = login(username, password)
        room_id = principal_dm_room(token, uid)
        messages = fetch_history(token, uid, room_id)
    except RuntimeError as e:
        log(f"poll error: {e}")
        return 1  # RC down — soft

    if not messages:
        log("no messages in DM yet")
        return 0

    state = load_state()
    last_id = state.get("last_seen_id")
    newest = messages[-1]
    newest_id = newest.get("_id")

    # Seed on first run: remember latest without waking (shared helper)
    if not last_id:
        state = seed_state_from_messages(messages, room_id)
        if state is None:
            log("no messages in DM yet")
            return 0
        save_state(state)
        log(f"seeded last_seen_id={state.get('last_seen_id')} (no wake)")
        return 0

    new_msgs = new_principal_messages(messages, last_id)
    if not new_msgs:
        # Still advance cursor if only grok messages arrived
        if newest_id != last_id:
            state["last_seen_id"] = newest_id
            state["last_seen_ts"] = newest.get("ts")
            save_state(state)
            log(f"advanced cursor to {newest_id} (no principal msg)")
        return 0

    # Advance cursor before wake so retries don't double-fire same set if crash mid-wake
    # Actually: advance after successful wake start is better; if wake fails we may retry.
    # Use mid lock: if wake starts, mark last of new_msgs as seen.
    preview = " | ".join((m.get("msg") or "")[:80] for m in new_msgs)
    log(f"NEW principal DM(s) n={len(new_msgs)}: {preview}")

    if not acquire_wake_lock():
        log("wake already in progress — skip spawn (cursor not advanced)")
        return 0

    try:
        notify_macos("Rocket.Chat → Grok", preview[:120] or "New DM from principal")
        cwd_pin = get_room_cwd(state, room_id)
        if cwd_pin and Path(cwd_pin).is_dir():
            project_cwd, reason = cwd_pin, "pinned"
        else:
            path, reason = resolve_project_cwd("dm:principal", room_type="d")
            project_cwd = str(path)
        prompt = build_prompt(
            new_msgs, room_id, project_cwd=project_cwd, project_reason=reason
        )
        resume_id = get_room_session_id(state, room_id)
        rc, sid = wake_grok(
            prompt,
            room_id=room_id,
            resume_session_id=resume_id,
            project_cwd=project_cwd,
        )
        # Advance past newest message in history (includes our replies later on next poll)
        state = load_state()
        state["last_seen_id"] = newest_id
        state["last_seen_ts"] = newest.get("ts")
        state["last_wake_at"] = datetime.now(timezone.utc).isoformat()
        state["last_wake_rc"] = rc
        state["room_id"] = room_id
        if sid:
            set_room_session_id(state, room_id, sid)
        set_room_cwd(state, room_id, project_cwd)
        save_state(state)
        return 0 if rc == 0 else 1
    finally:
        release_wake_lock()


def main(argv: list[str]) -> int:
    # Always one poll cycle (launchd StartInterval or manual --once).
    _ = argv
    return poll_once()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
