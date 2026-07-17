#!/usr/bin/env python3
"""
Always-on Rocket.Chat operator agent for user `grok`.

- Keeps a DDP websocket so presence shows **online**
- Watches principal↔grok DM for new principal messages
- Wakes headless Grok to reply (shared state with poller)

Run via launchd KeepAlive: com.velocityworks.rocketchat-operator
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from wake_lib import (
    load_env as _lib_load_env,
    load_state as _lib_load_state,
    save_state as _lib_save_state,
    acquire_wake_lock as _lib_acquire,
    release_wake_lock as _lib_release,
    force_clear_wake_lock as _lib_force_clear,
    heartbeat_wake_lock,
    room_wake_lock_dir,
    max_concurrent_wakes_from_env,
    count_active_room_locks,
    build_wake_argv,
    build_hermes_wake_argv,
    build_agy_wake_argv,
    wake_backend_from_env,
    parse_hermes_session_id,
    extract_hermes_reply_from_output,
    DEFAULT_HERMES_BIN,
    DEFAULT_HERMES_PROFILE,
    resolve_approval_mode,
    should_handle_dm_message,
    should_enqueue_llm_wake,
    message_has_handleable_content,
    require_mention_enabled,
    require_mention_scope,
    room_requires_operator_mention,
    message_mentions_operator,
    seed_state_from_messages,
    get_room_session_id,
    set_room_session_id,
    get_room_cwd,
    set_room_cwd,
    extract_session_id_from_output,
    resolve_project_cwd,
    compose_unified_reply,
    compose_final_with_thoughts,
    compose_wake_user_text,
    empty_attachment_wake_stub,
    extract_audio_file_candidates,
    extract_document_file_candidates,
    extract_image_file_candidates,
    extract_file_candidates,
    is_videoconf_message,
    is_videoconf_end_message as _wl_is_videoconf_end_message,
    videoconf_call_id,
    ACTIVITY_PLACEHOLDER,
    wake_react_enabled,
    wake_react_emoji,
)
from rc_commands import (
    control_plane_enabled,
    parse_command,
    is_confirm_reply,
    dispatch_command,
    get_pending_confirm,
    clear_expired_pending,
    confirm_yes,
    confirm_no,
    effective_approval_for_room,
    consume_once_elevation,
    get_room_model,
    get_room_effort,
    goal_prompt_block,
    set_last_content,
    set_room_wake_pid,
    admin_ttl_s,
    strip_leading_mentions,
)
from wake_telemetry import (
    wake_meta_enabled,
    wake_stream_enabled,
    stream_max_chars,
    stream_heartbeat_s,
    thought_first_min_chars,
    thought_first_wait_ms,
    thought_flush_ms,
    StreamThrottle,
    ThoughtAccumulator,
    parse_streaming_json_line,
    format_running_meta,
    choose_final_body,
    extract_salvageable_body,
    final_cool_s,
    retry_cooldown_s,
    wake_auto_retry_enabled,
    PHASE_RUNNING_META,
    PHASE_FINAL_OK,
    PHASE_FINAL_ERR,
)
try:
    from wake_ux_imp23 import (  # IMP-23 S1/S2/S7
        RateLimitBackoff,
        should_skip_empty_reply_retry,
        validate_wake_cwd,
        format_missing_cwd_err,
        final_cool_sleep_s,
        cross_process_update_wait,
        cross_process_update_touch,
        default_shared_update_bucket,
    )
except ImportError:  # pragma: no cover
    RateLimitBackoff = None  # type: ignore
    should_skip_empty_reply_retry = None  # type: ignore
    validate_wake_cwd = None  # type: ignore
    format_missing_cwd_err = None  # type: ignore
    final_cool_sleep_s = None  # type: ignore
    cross_process_update_wait = None  # type: ignore
    cross_process_update_touch = None  # type: ignore
    default_shared_update_bucket = None  # type: ignore
try:
    from wake_inflight_ux import (  # IMP-23 S5
        decide_enqueue,
        apply_decision_to_pending,
        should_emit_decision_log,
        normalize_wake_text,
    )
except ImportError:  # pragma: no cover
    decide_enqueue = None  # type: ignore
    apply_decision_to_pending = None  # type: ignore
    should_emit_decision_log = None  # type: ignore
    normalize_wake_text = None  # type: ignore
from rc_collab import (
    collab_master_enabled,
    collab_armed_for_room,
    lookup_room_profile,
    profile_hop_budget,
    resolve_mention_targets,
    classify_collab_message,
    get_collab_room_state,
    set_collab_room_state,
    ensure_collab_budget,
    set_agy_conversation_id,
    get_agy_conversation_id,
    record_collab_hop,
    pause_auto_handoff,
    resume_auto_handoff,
    build_agy_helper_plan,
    agy_cli_lock,
    assert_no_mcp_agy_in_argv,
    build_agy_l3_inject,
    build_grok_collab_inject_block,
    load_grok_inject_template,
    resolve_identity_creds,
    format_agy_cli_error,
    agy_wake_timeout_s,
    GROK_USER as COLLAB_GROK,
    AGY_USER as COLLAB_AGY,
    PRINCIPAL as COLLAB_PRINCIPAL,
)
from rc_multi_round_collab import (
    multi_round_enabled,
    playbook_inject_block,
    resolve_return_notify_target,
    should_emit_return_notify,
    build_return_notify_text,
    reply_declares_lead_done,
    message_is_collab_return,
    room_lead_done,
    mark_lead_done,
    maybe_clear_lead_done_on_new_work,
    should_skip_lead_llm_on_collab_return,
    should_skip_lead_llm_on_peer_closeout_ack,
    principal_multi_mention_lead_only,
    extract_peer_assignees_from_text,
    open_collab_epoch,
    record_assignee_delivered,
    room_epoch,
    summary_from_reply,
    GROK_LEAD as MR_GROK_LEAD,
    COLLAB_RETURN_MARKER,
)

try:
    import websocket  # websocket-client (install via setup-venv.sh / requirements.txt)
except ImportError as e:
    raise SystemExit(
        "missing dependency websocket-client; run "
        "~/.grok/agency/ops/rocketchat/setup-venv.sh and point PYTHON_BIN at the venv"
    ) from e

# Defaults; apply_runtime_config() (IMP-03) rewrites these from load_rc_config.
AGENCY = Path.home() / ".grok" / "agency"
SECRETS = AGENCY / "secrets" / "rocketchat.env"
WAKE_DIR = AGENCY / "ops" / "rocketchat" / "wake"
STATE_PATH = WAKE_DIR / "state.json"
PROMPT_TEMPLATE = WAKE_DIR / "reply_prompt.txt"
LOG_DIR = Path.home() / "logs" / "rocketchat-dm-wake"
LOG_PATH = LOG_DIR / "operator-agent.log"
LOCK_DIR = LOG_DIR / "wake.lock.d"

BASE_HTTP = os.environ.get("RC_BASE", "http://127.0.0.1:3000")
WS_URL = BASE_HTTP.replace("https://", "wss://").replace("http://", "ws://") + "/websocket"
OPERATOR = "grok"
HERMES_BIN = DEFAULT_HERMES_BIN
HERMES_PROFILE = DEFAULT_HERMES_PROFILE
WAKE_BACKEND = "grok"
PRINCIPAL = "principal"
GROK_BIN = os.environ.get("GROK_BIN", str(Path.home() / ".local" / "bin" / "grok"))
# IMP-09: align with wake_lib.DEFAULT_WAKE_MAX_TURNS
MAX_TURNS = os.environ.get("RC_WAKE_MAX_TURNS", "100")
WAKE_TIMEOUT_S = int(os.environ.get("RC_WAKE_TIMEOUT_S", "600"))
PING_EVERY_S = 20
RECONNECT_S = 5
HEALTH_PATH = LOG_DIR / "health.json"
_RC_CONFIG = None  # set by apply_runtime_config
_auth_lock = threading.Lock()
_auth_token: str | None = None
_auth_uid: str | None = None
_auth_login_count = 0
# NF-SPEC-04 dual identity: separate REST cache for RC user `agy`
_agy_auth_token: str | None = None
_agy_auth_uid: str | None = None
_agy_auth_login_count = 0
_last_event_at: str | None = None
# Re-scan joined channels/groups so rooms created after process start are watched.
ROOM_REFRESH_EVERY_S = int(os.environ.get("RC_ROOM_REFRESH_S", "60"))
CATCHUP_HISTORY = int(os.environ.get("RC_ROOM_CATCHUP", "12"))

# Local Whisper CLI for Path A voice notes (async STT → existing text wake).
WHISPER_BIN = os.environ.get("RC_WHISPER_BIN", "whisper")
WHISPER_MODEL = os.environ.get("RC_WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.environ.get("RC_WHISPER_LANGUAGE", "en")
STT_TIMEOUT_S = int(os.environ.get("RC_STT_TIMEOUT_S", "180"))
AUDIO_CACHE_DIR = LOG_DIR / "audio"
ATTACHMENTS_DIR = LOG_DIR / "attachments"

# NF-SPEC-05 inbound attachments (images + documents → local path → Grok read_file).
def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name, "1" if default else "0").strip().lower()
    if raw in ("0", "false", "off", "no", ""):
        return False
    return True


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


RC_ATTACH_ENABLED = _env_flag("RC_ATTACH_ENABLED", True)
RC_ATTACH_IMAGE = _env_flag("RC_ATTACH_IMAGE", True)
RC_ATTACH_DOCS = _env_flag("RC_ATTACH_DOCS", True)
RC_ATTACH_MAX_BYTES = _env_int("RC_ATTACH_MAX_BYTES", 20 * 1024 * 1024)
RC_ATTACH_MAX_FILES = _env_int("RC_ATTACH_MAX_FILES", 5)
RC_ATTACH_DOWNLOAD_TIMEOUT_S = _env_int("RC_ATTACH_DOWNLOAD_TIMEOUT_S", 60)
# Upload race: chat.getMessage may briefly omit files[] right after mobile attach.
RC_ATTACH_REHYDRATE_ATTEMPTS = max(1, _env_int("RC_ATTACH_REHYDRATE_ATTEMPTS", 3))
RC_ATTACH_REHYDRATE_DELAY_S = float(
    os.environ.get("RC_ATTACH_REHYDRATE_DELAY_S", "0.35") or "0.35"
)

# Path C: media bot joins Jitsi as grok and runs speaking-mode loop.
CALL_BOT = AGENCY / "ops" / "rocketchat" / "call" / "rc_call_bot.py"
CALL_BOT_SH = AGENCY / "ops" / "rocketchat" / "call" / "run_call_bot.sh"
VOICE_AGENT = AGENCY / "ops" / "rocketchat" / "call" / "voice_agent_worker.py"
VOICE_AGENT_SH = AGENCY / "ops" / "rocketchat" / "call" / "run_voice_agent.sh"
CALL_LOCK = LOG_DIR / "call-bot.lock"
MAX_CALL_BUSY_S = int(os.environ.get("RC_CALL_BUSY_S", "960"))
# Fallback text if media bot cannot start.
CALL_NO_MEDIA_REPLY = (
    "I see your call but could not start the voice bot on this Mac.\n\n"
    "Fallback: send a **voice note** or type here.\n"
)
# Import call media helpers (NF-SPEC-01); tolerate missing module in ancient checkouts.
try:
    from rc_call_media import (  # type: ignore
        call_media_backend,
        select_spawn_plan,
        acquire_call_lock,
        update_call_lock_pid,
        release_call_lock,
        call_lock_is_busy,
        clear_stale_call_lock,
        format_call_status_message,
        terminate_call_worker,
        read_call_lock,
        should_supersede_lock_for_new_call,
        STATUS_CONNECTING,
        STATUS_FAILED,
        STATUS_ENDED,
        voice_greeting,
        BACKEND_LIVEKIT,
        BACKEND_PLAYWRIGHT,
    )

    _HAS_CALL_MEDIA = True
except ImportError:
    # call/ is not always on sys.path when wake/ is the only entry
    try:
        sys.path.insert(0, str(AGENCY / "ops" / "rocketchat" / "call"))
        from rc_call_media import (  # type: ignore
            call_media_backend,
            select_spawn_plan,
            acquire_call_lock,
            update_call_lock_pid,
            release_call_lock,
            call_lock_is_busy,
            clear_stale_call_lock,
            format_call_status_message,
            terminate_call_worker,
            read_call_lock,
            should_supersede_lock_for_new_call,
            STATUS_CONNECTING,
            STATUS_FAILED,
            STATUS_ENDED,
            voice_greeting,
            BACKEND_LIVEKIT,
            BACKEND_PLAYWRIGHT,
        )

        _HAS_CALL_MEDIA = True
    except ImportError:
        _HAS_CALL_MEDIA = False


def is_videoconf_end_message(msg: dict) -> bool:
    """Prefer wake_lib (intake-aligned); fall back to call media helper if needed."""
    if _wl_is_videoconf_end_message(msg):
        return True
    if _HAS_CALL_MEDIA:
        try:
            from rc_call_media import is_videoconf_end_message as _cm_end  # type: ignore

            return bool(_cm_end(msg))
        except Exception:
            return False
    return False


def resolve_operator_python_bin() -> str:
    """
    Prefer ops rocketchat .venv (has livekit/websockets) over Frameworks python.

    Spawn of voice_agent_worker must import livekit; Frameworks python3 often cannot.
    """
    env_bin = os.environ.get("PYTHON_BIN", "").strip()
    candidates = [
        env_bin,
        str(AGENCY / "ops" / "rocketchat" / ".venv" / "bin" / "python3"),
        str(AGENCY / "ops" / "rocketchat" / ".venv" / "bin" / "python"),
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
        "python3",
    ]
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        # allow bare "python3" from PATH
        if c == "python3" or (not p.is_absolute() and "/" not in c):
            import shutil

            found = shutil.which(c)
            if found:
                return found
    return "python3"


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_env(path: Path) -> dict[str, str]:
    return _lib_load_env(path)


def http_api(method: str, path: str, token: str | None = None, uid: str | None = None, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token and uid:
        headers["X-Auth-Token"] = token
        headers["X-User-Id"] = uid
    req = urllib.request.Request(f"{BASE_HTTP}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def rest_login(username: str, password: str) -> tuple[str, str]:
    d = http_api("POST", "/api/v1/login", body={"user": username, "password": password})
    if d.get("status") != "success":
        raise RuntimeError(f"login failed: {d}")
    return d["data"]["authToken"], d["data"]["userId"]


def find_dm_room(token: str, uid: str) -> str:
    d = http_api("GET", "/api/v1/im.list", token=token, uid=uid)
    for im in d.get("ims") or []:
        users = set(im.get("usernames") or [])
        if PRINCIPAL in users and OPERATOR in users:
            return im["_id"]
    raise RuntimeError("principal↔grok DM not found")


def list_watch_rooms(token: str, uid: str) -> list[dict]:
    """
    Rooms the operator should listen to: principal DM + joined channels + private groups.

    Each item: {_id, name, t} where t is c/p/d.
    """
    rooms: list[dict] = []
    seen: set[str] = set()

    def add(rid: str, name: str, t: str) -> None:
        if not rid or rid in seen:
            return
        seen.add(rid)
        rooms.append({"_id": rid, "name": name or rid, "t": t})

    try:
        add(find_dm_room(token, uid), "dm:principal", "d")
    except RuntimeError as e:
        log(f"list_watch_rooms DM: {e}")

    try:
        ch = http_api("GET", "/api/v1/channels.list.joined", token=token, uid=uid)
        for c in ch.get("channels") or []:
            add(c.get("_id"), c.get("name") or c.get("fname") or "", "c")
    except Exception as e:
        log(f"list_watch_rooms channels: {e}")

    try:
        gr = http_api("GET", "/api/v1/groups.list", token=token, uid=uid)
        for g in gr.get("groups") or []:
            add(g.get("_id"), g.get("name") or g.get("fname") or "", "p")
    except Exception as e:
        log(f"list_watch_rooms groups: {e}")

    return rooms


def load_state() -> dict:
    return _lib_load_state(STATE_PATH)


def save_state(state: dict) -> None:
    _lib_save_state(state, STATE_PATH)


def acquire_wake_lock(room_id: str = "") -> bool:
    """Acquire per-room lock (IMP-10) with global concurrency cap."""
    lock_path = room_wake_lock_dir(LOCK_DIR, room_id) if room_id else LOCK_DIR
    # Drop dead legacy base lock so it cannot block per-room acquires forever.
    if LOCK_DIR.is_dir() and (LOCK_DIR / "holder.pid").is_file():
        from wake_lib import lock_holder_is_alive

        if not lock_holder_is_alive(LOCK_DIR):
            _lib_force_clear(LOCK_DIR)
    max_c = max_concurrent_wakes_from_env()
    active = count_active_room_locks(LOCK_DIR)
    already = lock_path.is_dir() and (lock_path / "holder.pid").is_file()
    if active >= max_c and not already:
        return False
    return _lib_acquire(lock_path)


def release_wake_lock(room_id: str = "") -> None:
    lock_path = room_wake_lock_dir(LOCK_DIR, room_id) if room_id else LOCK_DIR
    _lib_release(lock_path)


def force_clear_wake_lock(room_id: str = "") -> bool:
    lock_path = room_wake_lock_dir(LOCK_DIR, room_id) if room_id else LOCK_DIR
    ok = _lib_force_clear(lock_path)
    # Also clear dead legacy base lock used by older tests / older operators
    if LOCK_DIR.is_dir() and (LOCK_DIR / "holder.pid").is_file():
        from wake_lib import lock_holder_is_alive

        if not lock_holder_is_alive(LOCK_DIR):
            ok = _lib_force_clear(LOCK_DIR) and ok
    return ok


_drain_lock = threading.Lock()


def _nie_ledger_inject_enabled() -> bool:
    """True when this process is the nie operator / Hermes nie profile."""
    profile = (os.environ.get("RC_HERMES_PROFILE") or HERMES_PROFILE or "").strip().lower()
    op = (os.environ.get("RC_OPERATOR_USERNAME") or OPERATOR or "").strip().lower()
    if profile == "nie" or op == "nie":
        return True
    # Reply prompt path is nie-specific in production launchd
    try:
        prompt = str(PROMPT_TEMPLATE)
        if "nie_reply_prompt" in prompt:
            return True
    except Exception:
        pass
    return False


def _nie_ledger_inject_block(project_cwd: str) -> str:
    """Load nie falsifier ledger inject markdown; empty on any failure."""
    script = Path.home() / ".hermes" / "profiles" / "nie" / "scripts" / "nie_ledger.py"
    if not script.is_file():
        return ""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("nie_ledger_wake", script)
        if spec is None or spec.loader is None:
            return ""
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        text = mod.inject_markdown(project_cwd or "")
        if not text or not str(text).strip():
            return ""
        # Cap inject size so a huge ledger cannot blow the wake prompt
        text = str(text).strip()
        if len(text) > 6000:
            text = text[:6000] + "\n\n(truncated)"
        return text
    except Exception as e:
        try:
            log(f"nie ledger inject skipped: {e}")
        except Exception:
            pass
        return ""


def _feynman_ledger_inject_enabled() -> bool:
    """True when this process is the feynman-mechanism operator / Hermes feynman profile."""
    profile = (os.environ.get("RC_HERMES_PROFILE") or HERMES_PROFILE or "").strip().lower()
    op = (os.environ.get("RC_OPERATOR_USERNAME") or OPERATOR or "").strip().lower()
    if profile == "feynman" or op == "feynman":
        return True
    try:
        prompt = str(PROMPT_TEMPLATE)
        if "feynman_reply_prompt" in prompt:
            return True
    except Exception:
        pass
    return False


def _load_feynman_ledger_mod():
    """Import feynman_claim_ledger.py; None if missing."""
    script = (
        Path.home()
        / ".hermes"
        / "profiles"
        / "feynman"
        / "scripts"
        / "feynman_claim_ledger.py"
    )
    if not script.is_file():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("feynman_claim_ledger_wake", script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _feynman_ledger_inject_block(project_cwd: str) -> str:
    """Load feynman open-claim ledger inject markdown; empty on any failure."""
    try:
        mod = _load_feynman_ledger_mod()
        if mod is None:
            return ""
        text = mod.inject_markdown(project_cwd or "")
        if not text or not str(text).strip():
            return ""
        text = str(text).strip()
        if len(text) > 6000:
            text = text[:6000] + "\n\n(truncated)"
        return text
    except Exception as e:
        try:
            log(f"feynman ledger inject skipped: {e}")
        except Exception:
            pass
        return ""


def _feynman_ledger_ingest_reply(
    *,
    reply_body: str,
    project_cwd: str = "",
    room_id: str = "",
    room_name: str = "",
    mid: str | None = None,
    reply_path: str = "",
) -> int:
    """Post-wake: extract TOY/MOVING PART/FAILURE into claim ledger. Returns count."""
    if not _feynman_ledger_inject_enabled():
        return 0
    body = (reply_body or "").strip()
    if len(body) < 40:
        return 0
    try:
        mod = _load_feynman_ledger_mod()
        if mod is None or not hasattr(mod, "ingest_reply_text"):
            return 0
        rows = mod.ingest_reply_text(
            body,
            project_cwd=project_cwd or "",
            room_id=room_id or "",
            room_name=room_name or "",
            source_wake_id=str(mid) if mid else "",
            artifact_path=reply_path or "",
        )
        n = len(rows or [])
        if n:
            log(
                f"feynman claim ledger ingested n={n} room={room_name or room_id} mid={mid}"
            )
        return n
    except Exception as e:
        try:
            log(f"feynman ledger ingest skipped: {e}")
        except Exception:
            pass
        return 0


def build_prompt(
    new_msgs: list[dict],
    room_id: str,
    room_name: str = "",
    *,
    project_cwd: str = "",
    project_reason: str = "",
    thinking_msg_id: str = "",
    reply_file: str = "",
    approval_mode: str = "",
    goal_block: str = "",
) -> str:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    lines = [
        f"Room id: {room_id}",
        f"Room name: {room_name or room_id}",
        f"Project cwd: {project_cwd or '(agency default)'}",
        f"Project resolve: {project_reason or 'n/a'}",
        f"Approval mode: {approval_mode or '(see template)'}",
        f"Activity message id (already posted): {thinking_msg_id or '(none)'}",
        f"Thinking message id (already posted): {thinking_msg_id or '(none)'}",
        f"Reply file (write final user-facing answer here): {reply_file or '(none)'}",
        f"Base URL: {BASE_HTTP}",
        f"Operator user: {OPERATOR}",
        f"Principal user: {PRINCIPAL}",
        "You were started with --cwd set to Project cwd. Prefer that repo for code/tools.",
        "Do NOT chat.postMessage. Write the final user-facing answer ONLY to the reply file.",
        "The operator will chat.update the activity bubble (thought stream), replacing it with your reply.",
        "NO DUPLICATE POSTS: never rooms.mediaConfirm twice; use rc_post_media.py for images (idempotent).",
        # Standing principal voice: every room (DM/channel/group). See reply_prompt Voice.
        "Voice (ALL rooms): chat-message prose for a person — not log lines "
        "or ops-ticket dumps; short paragraphs; lead with the answer; "
        "no dense tables/status grids unless the user asked for a table.",
        f"New message count: {len(new_msgs)}",
        "New messages (chronological):",
    ]
    for m in new_msgs:
        author = (
            (m.get("author") or "")
            or ((m.get("u") or {}).get("username") if isinstance(m.get("u"), dict) else "")
            or "?"
        )
        body = (m.get("msg") or "").replace(chr(10), " ")
        lines.append(f"- [{m.get('ts','')}] {author}: {body}")
    if goal_block:
        lines.append("")
        lines.append(goal_block)
    # Multi-round collab playbook (one protocol for all four operators).
    if multi_round_enabled():
        pb = playbook_inject_block(wake_dir=WAKE_DIR)
        if pb:
            lines.append(pb)
    # nie: Falsifier Ledger pre-wake inject (closed claims + open/due falsifiers).
    if _nie_ledger_inject_enabled():
        ledger_block = _nie_ledger_inject_block(project_cwd or "")
        if ledger_block:
            lines.append("")
            lines.append(ledger_block)
    # feynman: open-claim ledger (TOY / MOVING PART / FAILURE) pre-wake inject.
    if _feynman_ledger_inject_enabled():
        fl_block = _feynman_ledger_inject_block(project_cwd or "")
        if fl_block:
            lines.append("")
            lines.append(fl_block)
    # Hermes: disk-truth preflight pack (path mtimes + prior replies).
    try:
        from hermes_preflight import (
            build_preflight_block,
            hermes_preflight_enabled_for_process,
            write_preflight_audit,
        )

        if hermes_preflight_enabled_for_process(
            operator=str(OPERATOR or ""),
            profile=str(
                globals().get("HERMES_PROFILE")
                or os.environ.get("RC_HERMES_PROFILE")
                or ""
            ),
            prompt_template=str(PROMPT_TEMPLATE),
            wake_backend=str(
                globals().get("WAKE_BACKEND")
                or os.environ.get("RC_WAKE_BACKEND")
                or ""
            ),
        ):
            msg_blob = "\n".join(
                (m.get("msg") or "") for m in new_msgs if isinstance(m, dict)
            )
            pre = build_preflight_block(
                msg_blob,
                project_cwd=project_cwd or "",
                room_id=room_id or "",
                room_name=room_name or "",
            )
            if pre:
                lines.append("")
                lines.append(pre)
                try:
                    write_preflight_audit(
                        pre,
                        wake_id=(thinking_msg_id or room_id or "")[:24],
                    )
                except Exception:
                    pass
    except Exception as e:
        try:
            log(f"hermes preflight inject skipped: {e}")
        except Exception:
            pass
    # Grok lead: orientation preflight (spine / collab epochs / disk delta / seats).
    try:
        from grok_preflight import (
            build_lead_preflight_block,
            grok_preflight_enabled_for_process,
            write_preflight_audit as write_lead_preflight_audit,
        )

        if grok_preflight_enabled_for_process(
            operator=str(OPERATOR or ""),
            wake_backend=str(
                globals().get("WAKE_BACKEND")
                or os.environ.get("RC_WAKE_BACKEND")
                or ""
            ),
            prompt_template=str(PROMPT_TEMPLATE),
        ):
            msg_blob = "\n".join(
                (m.get("msg") or "") for m in new_msgs if isinstance(m, dict)
            )
            lead_pre = build_lead_preflight_block(
                msg_blob,
                project_cwd=project_cwd or "",
                room_id=room_id or "",
                room_name=room_name or "",
            )
            if lead_pre:
                lines.append("")
                lines.append(lead_pre)
                try:
                    write_lead_preflight_audit(
                        lead_pre,
                        wake_id=(thinking_msg_id or room_id or "")[:24],
                    )
                except Exception:
                    pass
    except Exception as e:
        try:
            log(f"grok lead preflight inject skipped: {e}")
        except Exception:
            pass
    return template.replace("{{CONTEXT}}", "\n".join(lines))


def clear_operator_auth_cache() -> None:
    """Drop cached REST token (IMP-05). Also clears agy peer cache."""
    global _auth_token, _auth_uid, _agy_auth_token, _agy_auth_uid
    with _auth_lock:
        _auth_token = None
        _auth_uid = None
        _agy_auth_token = None
        _agy_auth_uid = None


def clear_agy_auth_cache() -> None:
    """Drop cached agy REST token only."""
    global _agy_auth_token, _agy_auth_uid
    with _auth_lock:
        _agy_auth_token = None
        _agy_auth_uid = None


def apply_runtime_config(*, check_rc: bool = True) -> object:
    """
    IMP-03: load shared rc_config and apply paths/flags to this module.

    Fail-fast if secrets missing or (when check_rc) Rocket.Chat unreachable.
    """
    global AGENCY, SECRETS, LOG_DIR, LOG_PATH, LOCK_DIR, BASE_HTTP, WS_URL
    global GROK_BIN, MAX_TURNS, WAKE_TIMEOUT_S, HEALTH_PATH, AUDIO_CACHE_DIR
    global CALL_BOT, CALL_BOT_SH, VOICE_AGENT, VOICE_AGENT_SH, CALL_LOCK
    global STATE_PATH, PROMPT_TEMPLATE, WAKE_DIR
    global OPERATOR, HERMES_BIN, HERMES_PROFILE, WAKE_BACKEND
    global _RC_CONFIG

    # Import here so tests can load the module without requiring a live secrets file.
    from rc_config import load_rc_config, validate_config_startup

    cfg = load_rc_config(require_secrets=True)
    problems = validate_config_startup(cfg, check_rc=check_rc)
    if problems:
        for p in problems:
            log(f"config error: {p}")
        raise SystemExit(f"operator config invalid: {'; '.join(problems)}")

    AGENCY = cfg.agency_path
    SECRETS = cfg.secrets_path
    LOG_DIR = cfg.log_dir
    LOG_PATH = LOG_DIR / "operator-agent.log"
    LOCK_DIR = LOG_DIR / "wake.lock.d"
    HEALTH_PATH = LOG_DIR / "health.json"
    AUDIO_CACHE_DIR = LOG_DIR / "audio"
    ATTACHMENTS_DIR = LOG_DIR / "attachments"
    BASE_HTTP = cfg.rc_base.rstrip("/")
    WS_URL = BASE_HTTP.replace("https://", "wss://").replace("http://", "ws://") + "/websocket"
    GROK_BIN = cfg.grok_bin
    HERMES_BIN = os.environ.get("HERMES_BIN", DEFAULT_HERMES_BIN)
    HERMES_PROFILE = os.environ.get("RC_HERMES_PROFILE", DEFAULT_HERMES_PROFILE)
    WAKE_BACKEND = wake_backend_from_env()
    MAX_TURNS = str(cfg.max_turns)
    WAKE_TIMEOUT_S = int(cfg.wake_timeout_s)
    WAKE_DIR = AGENCY / "ops" / "rocketchat" / "wake"
    # Parallel Hermes operator: separate state file (default hermes_state.json when backend=hermes).
    state_override = os.environ.get("RC_STATE_PATH", "").strip()
    if state_override:
        STATE_PATH = Path(state_override).expanduser()
    elif WAKE_BACKEND == "hermes":
        STATE_PATH = WAKE_DIR / "hermes_state.json"
    else:
        STATE_PATH = WAKE_DIR / "state.json"
    prompt_override = os.environ.get("RC_REPLY_PROMPT", "").strip()
    if prompt_override:
        PROMPT_TEMPLATE = Path(prompt_override).expanduser()
    elif WAKE_BACKEND == "hermes":
        PROMPT_TEMPLATE = WAKE_DIR / "hermes_reply_prompt.txt"
    else:
        PROMPT_TEMPLATE = WAKE_DIR / "reply_prompt.txt"
    OPERATOR = (cfg.operator_username or "grok").strip() or "grok"
    CALL_BOT = AGENCY / "ops" / "rocketchat" / "call" / "rc_call_bot.py"
    CALL_BOT_SH = AGENCY / "ops" / "rocketchat" / "call" / "run_call_bot.sh"
    VOICE_AGENT = AGENCY / "ops" / "rocketchat" / "call" / "voice_agent_worker.py"
    VOICE_AGENT_SH = AGENCY / "ops" / "rocketchat" / "call" / "run_voice_agent.sh"
    CALL_LOCK = LOG_DIR / "call-bot.lock"
    _RC_CONFIG = cfg
    log(
        f"config applied agency={AGENCY} secrets={SECRETS} log_dir={LOG_DIR} "
        f"rc_base={BASE_HTTP} approval_mode={cfg.approval_mode} "
        f"wake_timeout_s={WAKE_TIMEOUT_S} backend={WAKE_BACKEND} operator={OPERATOR} "
        f"require_mention={int(require_mention_enabled())} "
        f"require_mention_scope={require_mention_scope()} "
        f"state={STATE_PATH} prompt={PROMPT_TEMPLATE}"
    )
    return cfg


def _operator_auth(*, force_refresh: bool = False) -> tuple[str, str]:
    """
    Return (authToken, userId), caching across REST calls (IMP-05).

    Prefers ROCKETCHAT_OPERATOR_TOKEN + USER_ID when set (IMP-20);
    otherwise password login. Never logs secrets.
    """
    global _auth_token, _auth_uid, _auth_login_count
    with _auth_lock:
        if not force_refresh and _auth_token and _auth_uid:
            return _auth_token, _auth_uid
        secrets = load_env(SECRETS)
        from rc_config import token_pair_from_secrets, password_login_pair

        pair = token_pair_from_secrets(secrets)
        if pair:
            _auth_token, _auth_uid = pair
            return _auth_token, _auth_uid
        user, password = password_login_pair(secrets)
        _auth_token, _auth_uid = rest_login(user, password)
        _auth_login_count += 1
        return _auth_token, _auth_uid


def _agy_auth(*, force_refresh: bool = False) -> tuple[str, str]:
    """
    Return (authToken, userId) for RC peer `agy` (NF-SPEC-04).

    Prefers RC_AGY_TOKEN + RC_AGY_USER_ID (or secrets equivalents); else password
    login. Never logs secrets. Raises if credentials missing.
    """
    global _agy_auth_token, _agy_auth_uid, _agy_auth_login_count
    with _auth_lock:
        if not force_refresh and _agy_auth_token and _agy_auth_uid:
            return _agy_auth_token, _agy_auth_uid
        secrets = load_env(SECRETS)
        # Env overrides for tokens (launchd may inject without rewriting secrets file)
        env_merged = {**secrets, **{k: v for k, v in os.environ.items() if k.startswith("RC_AGY")}}
        creds = resolve_identity_creds("agy", secrets=secrets, env=env_merged)
        if creds.token and creds.user_id:
            _agy_auth_token, _agy_auth_uid = creds.token, creds.user_id
            return _agy_auth_token, _agy_auth_uid
        if creds.password:
            _agy_auth_token, _agy_auth_uid = rest_login(creds.username, creds.password)
            _agy_auth_login_count += 1
            return _agy_auth_token, _agy_auth_uid
        raise RuntimeError(
            "agy RC credentials missing — set RC_AGY_TOKEN+RC_AGY_USER_ID "
            "or ROCKETCHAT_AGY_PASSWORD in secrets"
        )


def auth_for_identity(identity: str, *, force_refresh: bool = False) -> tuple[str, str]:
    """REST auth for target RC identity (`grok` default or `agy`)."""
    ident = (identity or COLLAB_GROK).strip().lower()
    if ident == COLLAB_AGY:
        return _agy_auth(force_refresh=force_refresh)
    return _operator_auth(force_refresh=force_refresh)


def write_health_snapshot(
    *,
    ws_connected: bool,
    rooms_count: int = 0,
    extra: dict | None = None,
) -> None:
    """IMP-12: machine-readable operator health for watchdogs."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ws_connected": bool(ws_connected),
        "rooms_count": int(rooms_count),
        "last_event_at": _last_event_at,
        "last_wake_at": (load_state() or {}).get("last_wake_at"),
        "pid": os.getpid(),
        "auth_login_count": _auth_login_count,
        "approval_mode": os.environ.get("RC_WAKE_APPROVAL_MODE", "restricted"),
    }
    if extra:
        payload.update(extra)
    tmp = HEALTH_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(HEALTH_PATH)
    except OSError as e:
        log(f"health write failed: {e}")


def health_check_ok(*, max_age_s: float = 120.0) -> bool:
    """True if health.json is fresh and claims ws_connected (IMP-12)."""
    try:
        if not HEALTH_PATH.is_file():
            return False
        data = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
        ts = data.get("ts") or ""
        # parse ISO
        from datetime import datetime as _dt

        t = _dt.fromisoformat(ts.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - t).total_seconds()
        if age > max_age_s:
            return False
        return bool(data.get("ws_connected"))
    except Exception:
        return False


def post_as_grok(room_id: str, text: str) -> bool:
    """Post a message as grok. Prefer post_message_get_id when msg id is needed."""
    mid = post_message_get_id(room_id, text)
    return bool(mid)


def _rest_with_auth_retry(
    method: str,
    path: str,
    body: dict | None = None,
    *,
    identity: str = "grok",
) -> dict:
    """REST call using cached auth for identity; one re-login on auth failure."""
    token, uid = auth_for_identity(identity)
    try:
        return http_api(method, path, token, uid, body)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            if (identity or "").lower() == COLLAB_AGY:
                clear_agy_auth_cache()
            else:
                clear_operator_auth_cache()
            token, uid = auth_for_identity(identity, force_refresh=True)
            return http_api(method, path, token, uid, body)
        raise


def post_message_get_id(
    room_id: str, text: str, *, identity: str = "grok"
) -> str | None:
    """
    POST chat.postMessage as the given RC identity. Returns message _id.

    Used for the Thinking... placeholder so we can chat.update the same bubble.
    NF-SPEC-04: pass identity=`agy` for Antigravity peer posts.
    """
    ident = (identity or COLLAB_GROK).strip().lower() or COLLAB_GROK
    try:
        d = _rest_with_auth_retry(
            "POST",
            "/api/v1/chat.postMessage",
            {"roomId": room_id, "text": text},
            identity=ident,
        )
        if not d.get("success"):
            # Some RC auth errors return 200 with success false
            err = str(d.get("error") or d).lower()
            if "not authorized" in err or "unauthorized" in err or "logged in" in err:
                if ident == COLLAB_AGY:
                    clear_agy_auth_cache()
                else:
                    clear_operator_auth_cache()
                d = _rest_with_auth_retry(
                    "POST",
                    "/api/v1/chat.postMessage",
                    {"roomId": room_id, "text": text},
                    identity=ident,
                )
            if not d.get("success"):
                log(f"post_message_get_id identity={ident} failed: {d.get('error') or d}")
                return None
        mid = (d.get("message") or {}).get("_id")
        return str(mid) if mid else None
    except Exception as e:
        log(f"post_message_get_id identity={ident} failed: {e}")
        return None


def update_message(
    room_id: str,
    msg_id: str,
    text: str,
    *,
    identity: str = "grok",
    retries: int = 0,
    retry_base_s: float = 1.5,
) -> bool:
    """
    POST chat.update — edit an existing message in place (same bubble).

    Must use the same identity that posted the message (FR-A6/A7).
    retries: extra attempts on HTTP 429 / transient errors (use for FINAL update).
    """
    ident = (identity or COLLAB_GROK).strip().lower() or COLLAB_GROK
    attempts = max(1, 1 + int(retries))
    last_err: str | None = None
    for attempt in range(attempts):
        try:
            d = _rest_with_auth_retry(
                "POST",
                "/api/v1/chat.update",
                {"roomId": room_id, "msgId": msg_id, "text": text},
                identity=ident,
            )
            ok = bool(d.get("success"))
            if ok:
                return True
            last_err = str(d.get("error") or d)
            log(
                f"update_message identity={ident} failed attempt={attempt + 1}/{attempts}: "
                f"{last_err}"
            )
        except Exception as e:
            last_err = str(e)
            log(
                f"update_message identity={ident} failed attempt={attempt + 1}/{attempts}: {e}"
            )
            err_l = last_err.lower()
            is_rate = "429" in err_l or "too many" in err_l
            is_transient = is_rate or "timeout" in err_l or "temporarily" in err_l
            if attempt + 1 >= attempts or not is_transient:
                if "rc credentials missing" in err_l:
                    raise RuntimeError(last_err)
                return False
            # Exponential backoff; longer on 429 so FINAL is not lost.
            delay = retry_base_s * (2**attempt)
            if is_rate:
                delay = max(delay, 3.0 * (attempt + 1))
            log(f"update_message retrying in {delay:.1f}s after: {last_err}")
            time.sleep(delay)
            continue
        # success:false path — retry only on rate-limit-ish errors
        err_l = (last_err or "").lower()
        if attempt + 1 >= attempts:
            break
        if "429" in err_l or "too many" in err_l or "rate" in err_l:
            delay = max(retry_base_s * (2**attempt), 3.0 * (attempt + 1))
            log(f"update_message retrying in {delay:.1f}s after: {last_err}")
            time.sleep(delay)
            continue
        break
    return False


def react_message(
    msg_id: str,
    emoji: str,
    *,
    should_react: bool = True,
    identity: str = "grok",
) -> bool:
    """
    POST chat.react on an existing message (NF-SPEC-06).

    RC 8.6 body shape (verified against open API): messageId + emoji + optional
    shouldReact. Failures are logged and return False — never raise to caller.
    Grok wake process must not call this; operator owns REST only (R6).
    """
    if not wake_react_enabled():
        return False
    mid = (msg_id or "").strip()
    em = (emoji or "").strip().strip(":")
    if not mid or not em:
        return False
    ident = (identity or COLLAB_GROK).strip().lower() or COLLAB_GROK
    body = {
        "messageId": mid,
        "emoji": em,
        "shouldReact": bool(should_react),
    }
    try:
        d = _rest_with_auth_retry(
            "POST",
            "/api/v1/chat.react",
            body,
            identity=ident,
        )
        ok = bool(d.get("success"))
        if not ok:
            log(
                f"react failed identity={ident} msg={mid} emoji={em} "
                f"shouldReact={should_react}: {d.get('error') or d}"
            )
        return ok
    except Exception as e:
        log(
            f"react failed identity={ident} msg={mid} emoji={em} "
            f"shouldReact={should_react}: {e}"
        )
        return False


def schedule_react(
    msg_id: str,
    emoji: str,
    *,
    should_react: bool = True,
    identity: str = "grok",
) -> None:
    """
    Fire-and-forget react (N1/N2): daemon thread so wake spawn is not delayed.
    No-ops when RC_WAKE_REACT is off or msg_id empty.
    """
    if not wake_react_enabled() or not (msg_id or "").strip():
        return
    mid = msg_id.strip()
    em = (emoji or "").strip()

    def _run() -> None:
        react_message(mid, em, should_react=should_react, identity=identity)

    threading.Thread(
        target=_run, name=f"rc-react-{'on' if should_react else 'off'}-{em[:12]}", daemon=True
    ).start()


def schedule_wake_react_start(msg_id: str, *, identity: str = "grok") -> None:
    """Legacy: react on a message id (default eyes). Prefer schedule_principal_ack."""
    schedule_react(
        msg_id, wake_react_emoji("start"), should_react=True, identity=identity
    )


def schedule_principal_ack(principal_mid: str, *, identity: str = "grok") -> None:
    """
    Ack that the operator received the principal message: 👀 on *their* message.

    Kept after finalize (do not clear). Replaces the old Thinking... text ack.
    """
    schedule_react(
        principal_mid,
        wake_react_emoji("start"),
        should_react=True,
        identity=identity,
    )


def schedule_wake_react_terminal(
    msg_id: str,
    phase: str,
    *,
    identity: str = "grok",
) -> None:
    """
    Optional terminal react (✅ / ⚠️). Not used on principal ack (👀 stays).

    Kept for tests / explicit callers. Meta stream updates must not call this.
    """
    if not wake_react_enabled() or not (msg_id or "").strip():
        return
    start_em = wake_react_emoji("start")
    # FINAL_OK → success; FINAL_ERR or unknown → warning (safe default).
    kind = "ok" if phase == PHASE_FINAL_OK else "err"
    term_em = wake_react_emoji(kind)
    mid = msg_id.strip()
    ident = identity

    def _run() -> None:
        # Best-effort unreact start (degraded mode if remove unsupported — R3/R4).
        react_message(mid, start_em, should_react=False, identity=ident)
        react_message(mid, term_em, should_react=True, identity=ident)

    threading.Thread(
        target=_run, name=f"rc-react-term-{kind}", daemon=True
    ).start()


def post_thinking_placeholder(room_id: str, *, identity: str = "grok") -> str | None:
    """
    One agent bubble reserved for thought stream then final answer.

    Initial text is ACTIVITY_PLACEHOLDER (not Thinking...). Same msgId is updated
    in place for the rest of the wake. Name kept for test/mock compatibility.
    """
    return post_message_get_id(room_id, ACTIVITY_PLACEHOLDER, identity=identity)


def post_activity_placeholder(room_id: str, *, identity: str = "grok") -> str | None:
    """Alias for post_thinking_placeholder (activity bubble)."""
    return post_thinking_placeholder(room_id, identity=identity)


def _safe_filename(name: str) -> str:
    """Keep a usable basename for disk without path traversal."""
    base = Path((name or "upload.bin").replace("\\", "/")).name
    base = re.sub(r"[^\w.\-()+ ]+", "_", base).strip("._") or "upload.bin"
    return base[:180]


def _same_host_as_base(url: str) -> bool:
    """True if url host matches configured BASE_HTTP (SSRF guard FR-A12)."""
    try:
        base = urllib.parse.urlparse(BASE_HTTP)
        target = urllib.parse.urlparse(url)
    except Exception:
        return False
    if target.scheme not in ("http", "https"):
        return False
    base_host = (base.hostname or "").lower()
    target_host = (target.hostname or "").lower()
    if not base_host or not target_host:
        return False
    # localhost / 127.0.0.1 equivalence for local RC
    loopbacks = {"localhost", "127.0.0.1", "::1"}
    if base_host in loopbacks and target_host in loopbacks:
        return True
    return base_host == target_host


def download_rc_file(
    token: str,
    uid: str,
    *,
    file_id: str = "",
    filename: str = "",
    title_link: str = "",
    dest_dir: Path | None = None,
    max_bytes: int | None = None,
    timeout_s: float | None = None,
) -> Path:
    """
    Download a Rocket.Chat upload using operator auth headers.

    Prefer title_link when present (as RC stores it); else /file-upload/{id}/{name}.
    Enforces same-host as BASE_HTTP and optional max_bytes (NF-SPEC-05).
    """
    dest_dir = dest_dir or AUDIO_CACHE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(filename or "upload.bin")
    stamp = int(time.time() * 1000)
    dest = dest_dir / f"{stamp}-{file_id[:12] if file_id else 'file'}-{safe}"
    limit = RC_ATTACH_MAX_BYTES if max_bytes is None else max_bytes
    timeout = (
        float(RC_ATTACH_DOWNLOAD_TIMEOUT_S) if timeout_s is None else float(timeout_s)
    )

    if title_link:
        if title_link.startswith("http://") or title_link.startswith("https://"):
            url = title_link
        else:
            url = f"{BASE_HTTP.rstrip('/')}{title_link if title_link.startswith('/') else '/' + title_link}"
    elif file_id:
        url = (
            f"{BASE_HTTP.rstrip('/')}/file-upload/"
            f"{urllib.parse.quote(file_id, safe='')}/"
            f"{urllib.parse.quote(safe)}"
        )
    else:
        raise ValueError("download_rc_file needs file_id or title_link")

    if not _same_host_as_base(url):
        raise RuntimeError(
            f"refusing download: host not same as RC_BASE ({BASE_HTTP})"
        )

    headers = {
        "X-Auth-Token": token,
        "X-User-Id": uid,
        # Some RC setups also accept cookie-style; headers are the REST contract.
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # Stream with cap so oversize uploads cannot fill disk (FR-A13).
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if limit > 0 and total > limit:
                raise RuntimeError(
                    f"exceeds RC_ATTACH_MAX_BYTES ({limit} bytes)"
                )
            chunks.append(chunk)
        data = b"".join(chunks)
    if not data:
        raise RuntimeError(f"empty download from {url}")
    dest.write_bytes(data)
    return dest


def transcribe_audio_file(audio_path: Path) -> str:
    """
    Local Whisper STT → plain text transcript.

    Uses the system `whisper` CLI (openai-whisper). Model/language overridable
    via RC_WHISPER_MODEL / RC_WHISPER_LANGUAGE.
    """
    if not audio_path.is_file():
        raise FileNotFoundError(f"audio missing: {audio_path}")
    out_dir = audio_path.parent / f"stt-{audio_path.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        WHISPER_BIN,
        str(audio_path),
        "--model",
        WHISPER_MODEL,
        "--language",
        WHISPER_LANGUAGE,
        "--task",
        "transcribe",
        "--output_format",
        "txt",
        "--output_dir",
        str(out_dir),
        "--verbose",
        "False",
        "--fp16",
        "False",
    ]
    log(f"stt start model={WHISPER_MODEL} file={audio_path.name}")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=STT_TIMEOUT_S,
        env={
            **os.environ,
            "PATH": (
                f"{Path.home() / '.local' / 'bin'}:"
                f"/Library/Frameworks/Python.framework/Versions/3.13/bin:"
                f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:"
                f"{os.environ.get('PATH', '')}"
            ),
        },
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise RuntimeError(f"whisper rc={proc.returncode}: {err}")

    # Whisper names output from the audio stem
    candidates = list(out_dir.glob("*.txt"))
    # Prefer exact stem match
    preferred = out_dir / f"{audio_path.stem}.txt"
    if preferred.is_file():
        text = preferred.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return text
    for c in candidates:
        text = c.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return text
    raise RuntimeError(f"whisper produced no transcript text under {out_dir}")


def fetch_message_by_id(msg_id: str) -> dict | None:
    """
    REST chat.getMessage — full payload when the websocket stream omits files.

    Returns the message dict or None on failure.
    """
    if not msg_id:
        return None
    try:
        token, uid = _operator_auth()
        d = http_api(
            "GET",
            f"/api/v1/chat.getMessage?msgId={urllib.parse.quote(msg_id)}",
            token,
            uid,
        )
        if not d.get("success"):
            return None
        m = d.get("message")
        return m if isinstance(m, dict) else None
    except Exception as e:
        log(f"chat.getMessage failed id={msg_id}: {e}")
        return None


def _rehydrate_message_with_files(msg: dict) -> dict:
    """
    chat.getMessage until file candidates appear or attempts are exhausted.

    Mobile uploads often emit a text/caption event before files[] is linked.
    Sparse DDP payloads also omit file/attachments when text is present.
    Always re-fetch by mid; retry briefly when still empty (NF-SPEC-05 FR-A1).

    Pure text (successful getMessage, no files, no stream file hints): at most
    one delayed re-check so normal chat stays snappy; attach-like traffic keeps
    the full retry budget.
    """
    mid = msg.get("_id")
    if not mid:
        return msg
    best = msg
    stream_files = extract_file_candidates(msg)
    stream_hint = bool(
        msg.get("file") or msg.get("files") or msg.get("attachments") or stream_files
    )
    caption_empty = not (msg.get("msg") or "").strip()
    attempts = max(1, int(RC_ATTACH_REHYDRATE_ATTEMPTS))
    delay = max(0.0, float(RC_ATTACH_REHYDRATE_DELAY_S))
    for i in range(attempts):
        full = fetch_message_by_id(str(mid))
        if full:
            best = full
            n = len(extract_file_candidates(full))
            if n:
                if i > 0:
                    log(
                        f"rehydrate files ready attempt={i + 1}/{attempts} "
                        f"mid={mid} n_files={n}"
                    )
                return full
            # No files yet. Cap retries for ordinary text; keep full budget when
            # stream hinted files, caption-empty upload, or getMessage failed earlier.
            pure_text = (
                not stream_hint
                and not caption_empty
                and bool((full.get("msg") or "").strip())
            )
            if pure_text and i >= 1:
                return full
        if i + 1 < attempts and delay > 0:
            time.sleep(delay)
    if attempts > 1:
        log(
            f"rehydrate done mid={mid} attempts={attempts} "
            f"n_files={len(extract_file_candidates(best))}"
        )
    return best


def resolve_message_text_for_wake(msg: dict) -> str:
    """
    Caption + optional local STT (audio) + local image/document paths.

    DDP stream events often omit `file`/`attachments` when text is present.
    Always re-fetch by message id (with short retries) so uploads are not dropped.

    Pure text messages pass through unchanged. Audio → Whisper transcript.
    Images/docs → downloaded under attachments/ and listed for Grok `read_file`.
    """
    caption = (msg.get("msg") or "").strip()
    mid = msg.get("_id")
    # Merge any queue-side file meta with rehydrated payload.
    queued_files = {
        "file": msg.get("file"),
        "files": msg.get("files"),
        "attachments": msg.get("attachments"),
    }
    if mid:
        full = _rehydrate_message_with_files(msg)
        caption = (full.get("msg") or caption or "").strip()
        msg = full
        # If rehydrate still sparse, keep any file meta that arrived on the WS item.
        if not extract_file_candidates(msg):
            for k, v in queued_files.items():
                if v:
                    msg[k] = v

    audio_files = extract_audio_file_candidates(msg)
    image_files: list[dict[str, str]] = []
    doc_files: list[dict[str, str]] = []
    if RC_ATTACH_ENABLED:
        if RC_ATTACH_IMAGE:
            image_files = extract_image_file_candidates(msg)
        if RC_ATTACH_DOCS:
            doc_files = extract_document_file_candidates(msg)

    # Cap total non-audio downloads per message (FR-A14).
    max_files = max(0, int(RC_ATTACH_MAX_FILES))
    truncated_note = ""
    combined_non_audio = list(image_files) + list(doc_files)
    if max_files and len(combined_non_audio) > max_files:
        keep = combined_non_audio[:max_files]
        truncated_note = (
            f"message has {len(combined_non_audio)} non-audio files; "
            f"processing first {max_files} only (RC_ATTACH_MAX_FILES)"
        )
        image_ids = {f.get("id") or f.get("title_link") for f in image_files}
        image_files = [
            f
            for f in keep
            if (f.get("id") or f.get("title_link")) in image_ids
        ]
        doc_files = [
            f
            for f in keep
            if (f.get("id") or f.get("title_link")) not in image_ids
        ]

    if not audio_files and not image_files and not doc_files:
        return caption

    transcripts: list[str] = []
    stt_errors: list[str] = []
    image_paths: list[str] = []
    image_errors: list[str] = []
    file_entries: list[dict[str, str]] = []
    file_errors: list[str] = []
    if truncated_note:
        file_errors.append(truncated_note)

    try:
        token, uid = _operator_auth()
    except Exception as e:
        return compose_wake_user_text(
            caption,
            stt_errors=[f"auth for download failed: {e}"] if audio_files else None,
            image_errors=[f"auth for download failed: {e}"] if image_files else None,
            file_errors=[f"auth for download failed: {e}"] if doc_files else None,
        )

    for meta in audio_files:
        name = meta.get("name") or "voice"
        try:
            path = download_rc_file(
                token,
                uid,
                file_id=meta.get("id") or "",
                filename=name,
                title_link=meta.get("title_link") or "",
                dest_dir=AUDIO_CACHE_DIR,
            )
            log(f"stt downloaded {path.name} bytes={path.stat().st_size}")
            transcripts.append(transcribe_audio_file(path))
        except Exception as e:
            log(f"stt failed name={name}: {e}")
            stt_errors.append(f"{name}: {e}")

    for meta in image_files:
        name = meta.get("name") or "image.jpg"
        try:
            path = download_rc_file(
                token,
                uid,
                file_id=meta.get("id") or "",
                filename=name,
                title_link=meta.get("title_link") or "",
                dest_dir=ATTACHMENTS_DIR,
            )
            log(f"image downloaded {path.name} bytes={path.stat().st_size}")
            image_paths.append(str(path))
        except Exception as e:
            log(f"image download failed name={name}: {e}")
            image_errors.append(f"{name}: {e}")

    for meta in doc_files:
        name = meta.get("name") or "file.bin"
        try:
            path = download_rc_file(
                token,
                uid,
                file_id=meta.get("id") or "",
                filename=name,
                title_link=meta.get("title_link") or "",
                dest_dir=ATTACHMENTS_DIR,
            )
            nbytes = path.stat().st_size
            log(f"doc downloaded {path.name} bytes={nbytes}")
            file_entries.append(
                {
                    "path": str(path),
                    "name": name,
                    "mime": meta.get("type") or "",
                    "bytes": str(nbytes),
                }
            )
        except Exception as e:
            log(f"doc download failed name={name}: {e}")
            file_errors.append(f"{name}: {e}")

    log(
        f"attach resolve mid={mid or '-'} audio={len(audio_files)} "
        f"image_ok={len(image_paths)} image_err={len(image_errors)} "
        f"docs_ok={len(file_entries)} docs_err={len(file_errors)}"
    )
    return compose_wake_user_text(
        caption,
        transcripts=transcripts,
        stt_errors=stt_errors,
        image_paths=image_paths,
        image_errors=image_errors,
        file_entries=file_entries,
        file_errors=file_errors,
    )


def finalize_thinking_message(
    room_id: str,
    thinking_msg_id: str,
    final_body: str,
    *,
    identity: str = "grok",
    thought_text: str = "",
    stream_throttle: StreamThrottle | None = None,
) -> bool:
    """
    Update the activity bubble in place with Thoughts (if any) + final answer.

    When thought_text is present (RC-safe markup — bold label + unicode rule):

        *Thoughts*
        …
        ────────────────
        <final>

    FINAL_ERR structured chrome is preserved; still prefixed by Thoughts when
    a thought stream was collected. Empty thought_text → answer only.

    Retries chat.update on 429 so a busy thought stream cannot strand the bubble
    without a final answer.

    B4: cool-down is relative to last non-final update (RC_FINAL_COOL_S), not a
    fixed 1s floor alone.
    """
    # FINAL_ERR already includes structured chrome — do not wrap as empty→…
    stripped = final_body.strip()
    if (
        stripped.startswith("(Wake did not produce")
        or stripped.startswith("(Could not complete")
        or stripped.startswith("(agy CLI did not produce")
    ):
        answer = stripped
    else:
        answer = compose_unified_reply(final_body)
    text = compose_final_with_thoughts(answer, thought_text)
    # B4: dynamic cool-down after mid-wake update storm before FINAL (RC 429).
    cool = (
        stream_throttle.final_cool_remaining(final_cool_s())
        if stream_throttle is not None
        else final_cool_s()
    )
    if callable(final_cool_sleep_s):
        cool = final_cool_sleep_s(cool)
    else:
        cool = max(1.0, min(8.0, float(cool)))
    if cool > 0:
        log(f"final cool-down sleep={cool:.2f}s room={room_id}")
        time.sleep(cool)
    # IMP-23 S4-lite: host-wide update gap (same path on every operator).
    if callable(cross_process_update_wait) and callable(cross_process_update_touch):
        if callable(default_shared_update_bucket):
            bucket = default_shared_update_bucket()
        else:
            bucket = Path.home() / "logs" / "rocketchat-shared" / "rc-update.bucket"
        wait_x = cross_process_update_wait(bucket, min_gap_s=0.35)
        if wait_x > 0:
            time.sleep(wait_x)
        cross_process_update_touch(bucket)
    return update_message(
        room_id,
        thinking_msg_id,
        text,
        identity=identity,
        retries=5,
        retry_base_s=2.0,
    )


def update_thinking_meta(
    room_id: str,
    thinking_msg_id: str,
    body: str,
    *,
    identity: str = "grok",
) -> bool:
    """Non-final chat.update on the same bubble (NF-SPEC-02 RUNNING_META)."""
    return update_message(room_id, thinking_msg_id, body, identity=identity)


def _run_wake_once(
    prompt_path: Path,
    log_file: Path,
    *,
    max_turns: str,
    resume_session_id: str | None,
    project_cwd: str,
    approval_mode: str,
    model: str | None = None,
    effort: str | None = None,
    room_id: str | None = None,
    output_format: str | None = "json",
    on_stream_event=None,
) -> tuple[int, str | None, str]:
    """
    Run one headless grok; return (rc, session_id_or_none, log_text).

    When output_format is streaming-json and on_stream_event is set, stdout is
    read line-by-line and each parsed NDJSON object is passed to the callback
    (for live thought bubble updates). Full stdout is still written to log_file.
    """
    cmd = build_wake_argv(
        prompt_path,
        grok_bin=GROK_BIN,
        cwd=project_cwd,
        max_turns=max_turns,
        resume_session_id=resume_session_id,
        output_format=output_format or "json",
        approval_mode=approval_mode,
        model=model,
        effort=effort,
    )
    backend = wake_backend_from_env()
    if backend == "hermes":
        # Hermes has no streaming-json / --prompt-file; -q carries the full prompt.
        cmd = build_hermes_wake_argv(
            prompt_path,
            hermes_bin=HERMES_BIN if "HERMES_BIN" in globals() else DEFAULT_HERMES_BIN,
            profile=HERMES_PROFILE if "HERMES_PROFILE" in globals() else DEFAULT_HERMES_PROFILE,
            max_turns=max_turns,
            resume_session_id=resume_session_id,
            approval_mode=approval_mode,
            model=model,
        )
        output_format = None
        on_stream_event = None
    elif backend == "agy":
        cmd = build_agy_wake_argv(
            prompt_path,
            max_turns=max_turns,
            resume_session_id=resume_session_id,
            approval_mode=approval_mode,
            model=model,
        )
        output_format = None
        on_stream_event = None
    log(
        f"waking {backend} approval_mode={approval_mode} resume={resume_session_id or 'NEW'} "
        f"cwd={project_cwd} model={model or '-'} effort={effort or '-'} "
        f"fmt={output_format or ('hermes-q' if backend == 'hermes' else 'json')} "
        f"cmd={' '.join(cmd[:8])} ..."
    )
    env = os.environ.copy()
    env["PATH"] = (
        f"{Path.home() / '.local' / 'bin'}:{Path.home() / '.grok' / 'bin'}:"
        f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{env.get('PATH', '')}"
    )
    env["HOME"] = str(Path.home())
    stream_live = (output_format or "json") == "streaming-json" and callable(
        on_stream_event
    )

    # IMP-02: heartbeat active room lock(s) while long wakes run
    stop_hb = threading.Event()

    def _hb() -> None:
        while not stop_hb.wait(30.0):
            try:
                rooms = LOCK_DIR / "rooms"
                if rooms.is_dir():
                    for child in rooms.iterdir():
                        if child.is_dir() and (child / "holder.pid").is_file():
                            try:
                                if int((child / "holder.pid").read_text().strip()) == os.getpid():
                                    heartbeat_wake_lock(child)
                            except (OSError, ValueError):
                                pass
                elif LOCK_DIR.is_dir():
                    heartbeat_wake_lock(LOCK_DIR)
            except OSError:
                pass

    hb_thread = threading.Thread(target=_hb, name="rc-wake-lock-hb", daemon=True)
    hb_thread.start()
    rc = 1
    try:
        if stream_live:
            # Prefer a PTY so the child line-buffers NDJSON (plain PIPE often
            # block-buffers → first "The" then a long stall before the rest).
            import pty
            import select

            with log_file.open("w", encoding="utf-8") as out:
                out.write(f"cmd: {cmd}\n\n")
                out.flush()
                master_fd, slave_fd = pty.openpty()
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=slave_fd,
                        stderr=slave_fd,
                        stdin=subprocess.DEVNULL,
                        env=env,
                        cwd=project_cwd,
                        close_fds=True,
                    )
                finally:
                    os.close(slave_fd)
                if room_id and proc.pid:
                    try:
                        st = load_state()
                        set_room_wake_pid(st, room_id, int(proc.pid))
                        save_state(st)
                    except Exception as e:
                        log(f"set_room_wake_pid failed: {e}")

                read_err: list[BaseException] = []
                deadline = time.monotonic() + float(WAKE_TIMEOUT_S)

                def _read_stdout() -> None:
                    buf = ""
                    try:
                        while True:
                            if time.monotonic() > deadline:
                                break
                            r, _, _ = select.select([master_fd], [], [], 0.25)
                            if not r:
                                if proc.poll() is not None:
                                    # Drain any remaining bytes after exit.
                                    while True:
                                        try:
                                            chunk = os.read(master_fd, 4096)
                                        except OSError:
                                            chunk = b""
                                        if not chunk:
                                            break
                                        buf += chunk.decode("utf-8", errors="replace")
                                        while "\n" in buf:
                                            line, buf = buf.split("\n", 1)
                                            line = line + "\n"
                                            out.write(line)
                                            out.flush()
                                            event = parse_streaming_json_line(line)
                                            if event is not None:
                                                try:
                                                    on_stream_event(event)
                                                except Exception as cb_err:
                                                    log(
                                                        f"stream event callback failed: {cb_err}"
                                                    )
                                    break
                                continue
                            try:
                                chunk = os.read(master_fd, 4096)
                            except OSError as e:
                                read_err.append(e)
                                break
                            if not chunk:
                                break
                            buf += chunk.decode("utf-8", errors="replace")
                            while "\n" in buf:
                                line, buf = buf.split("\n", 1)
                                line = line + "\n"
                                out.write(line)
                                out.flush()
                                event = parse_streaming_json_line(line)
                                if event is None:
                                    continue
                                try:
                                    on_stream_event(event)
                                except Exception as cb_err:
                                    log(f"stream event callback failed: {cb_err}")
                    except Exception as e:
                        read_err.append(e)
                    finally:
                        try:
                            os.close(master_fd)
                        except OSError:
                            pass

                reader = threading.Thread(
                    target=_read_stdout, name="rc-wake-stdout", daemon=True
                )
                reader.start()
                reader.join(timeout=float(WAKE_TIMEOUT_S) + 5.0)
                if reader.is_alive():
                    proc.kill()
                    reader.join(timeout=5.0)
                    log(f"wake timeout log={log_file} limit_s={WAKE_TIMEOUT_S}")
                    rc = 124
                else:
                    rc = proc.wait()
                    if time.monotonic() > deadline and rc == 0:
                        # Reader stopped after deadline without kill race
                        pass
                    if read_err:
                        log(f"wake stdout reader error: {read_err[0]}")
        else:
            with log_file.open("w", encoding="utf-8") as out:
                out.write(f"cmd: {cmd}\n\n")
                out.flush()
                proc = subprocess.Popen(
                    cmd, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=project_cwd
                )
                if room_id and proc.pid:
                    try:
                        st = load_state()
                        set_room_wake_pid(st, room_id, int(proc.pid))
                        save_state(st)
                    except Exception as e:
                        log(f"set_room_wake_pid failed: {e}")
                try:
                    rc = proc.wait(timeout=WAKE_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    log(f"wake timeout log={log_file} limit_s={WAKE_TIMEOUT_S}")
                    rc = 124
    finally:
        stop_hb.set()
        if room_id:
            try:
                st = load_state()
                set_room_wake_pid(st, room_id, None)
                save_state(st)
            except Exception:
                pass
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    sid = extract_session_id_from_output(text)
    if not sid:
        sid = parse_hermes_session_id(text)
    return rc, sid, text


def wake_grok(
    prompt: str,
    *,
    max_turns: str | None = None,
    room_id: str | None = None,
    resume_session_id: str | None = None,
    project_cwd: str | None = None,
    approval_mode: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    on_stream_event=None,
) -> tuple[int, str | None, Path | None, str]:
    """
    Headless Grok with per-chat session continuity + project cwd.

    Returns (rc, session_id, log_path, log_text). session_id is the Grok session
    to pin for this Rocket.Chat room so the next message resumes the same conversation.
    log_path/log_text support NF-SPEC-02 FINAL_ERR stopReason parse.

    on_stream_event: optional callable(event: dict) for streaming-json objects
    (thought/text/end). Used to update the intermediate RC bubble with thoughts.

    approval_mode: restricted (default) or admin — see wake_lib.resolve_approval_mode.
    model / effort: optional room pins (NF-SPEC-03) → CLI flags.

    Do NOT pass --disallowed-tools Agent (breaks session build on this install).
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    prompt_path = LOG_DIR / f"wake-prompt-{ts}.txt"
    log_file = LOG_DIR / f"wake-run-{ts}.log"
    prompt_path.write_text(prompt, encoding="utf-8")
    turns = max_turns or MAX_TURNS
    cwd = project_cwd or str(AGENCY)
    mode = approval_mode or resolve_approval_mode()
    if wake_backend_from_env() == "hermes":
        # Hermes has no streaming-json; capture combined log only.
        out_fmt = None
        stream_cb = None
    else:
        out_fmt = "streaming-json" if wake_stream_enabled() else "json"
        stream_cb = on_stream_event if out_fmt == "streaming-json" else None

    rc, sid, text = _run_wake_once(
        prompt_path,
        log_file,
        max_turns=turns,
        resume_session_id=resume_session_id,
        project_cwd=cwd,
        approval_mode=mode,
        model=model,
        effort=effort,
        room_id=room_id,
        output_format=out_fmt,
        on_stream_event=stream_cb,
    )

    # Stale/missing session: drop pin and start a fresh session once.
    resume_failed = resume_session_id and (
        rc != 0
        and (
            "Couldn't start session" in text
            or "session not found" in text.lower()
            or "failed to resume" in text.lower()
            or "unknown session" in text.lower()
        )
    )
    if resume_failed:
        log(f"resume failed for {resume_session_id}; starting new session room={room_id}")
        log_file2 = LOG_DIR / f"wake-run-{ts}-retry.log"
        log_file = log_file2
        rc, sid, text = _run_wake_once(
            prompt_path,
            log_file2,
            max_turns=turns,
            resume_session_id=None,
            project_cwd=cwd,
            approval_mode=mode,
            model=model,
            effort=effort,
            room_id=room_id,
            output_format=out_fmt,
            on_stream_event=stream_cb,
        )

    # If we resumed successfully but JSON omitted sessionId, keep the pin.
    if not sid and resume_session_id and rc == 0:
        sid = resume_session_id

    log(
        f"wake finished rc={rc} approval_mode={mode} session={sid or 'none'} "
        f"cwd={cwd} model={model or '-'} effort={effort or '-'} log={log_file}"
    )
    return rc, sid, log_file, text


def _health_summary_line() -> str:
    """Short operator health for /status and /health (NF-SPEC-03)."""
    try:
        if HEALTH_PATH.is_file():
            age = time.time() - HEALTH_PATH.stat().st_mtime
            raw = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
            ws = raw.get("ws_connected")
            pid = raw.get("pid") or raw.get("operator_pid")
            return (
                f"health.json age={age:.0f}s ws_connected={ws} pid={pid} "
                f"base={BASE_HTTP}"
            )
    except (OSError, json.JSONDecodeError, TypeError) as e:
        return f"health.json unreadable ({e}); base={BASE_HTTP}"
    return f"health.json missing; base={BASE_HTTP} pid={os.getpid()}"


def _try_cancel_wake_pid(pid: int, room_id: str) -> str:
    """SIGTERM owned wake child if still alive; clear state pin."""
    import signal

    try:
        os.kill(pid, 0)
    except OSError:
        st = load_state()
        set_room_wake_pid(st, room_id, None)
        save_state(st)
        return f"PID {pid} is not running (already finished)."
    try:
        os.kill(pid, signal.SIGTERM)
        st = load_state()
        set_room_wake_pid(st, room_id, None)
        save_state(st)
        # Also try force-clear room lock so next wake can proceed
        force_clear_wake_lock(room_id)
        log(f"control-plane cancel SIGTERM pid={pid} room={room_id}")
        return f"Sent SIGTERM to wake pid={pid}."
    except OSError as e:
        return f"Could not signal pid={pid}: {e}"


def _resolve_room_cwd_info(
    rid: str, room_name: str, room_type: str | None, st: dict
) -> tuple[str, str]:
    cwd_pin = get_room_cwd(st, rid)
    if cwd_pin and Path(cwd_pin).is_dir():
        return cwd_pin, "pinned"
    rtype = room_type
    if not rtype and (room_name or "").lower().startswith("dm"):
        rtype = "d"
    path, reason = resolve_project_cwd(room_name or rid, room_type=rtype)
    return str(path), reason


def _mark_processed(
    mid: str,
    rid: str,
    ts: str | None,
    rc: int | None = None,
    *,
    grok_session_id: str | None = None,
    project_cwd: str | None = None,
    clear_session: bool = False,
) -> None:
    state = load_state()
    state["last_seen_id"] = mid
    state["last_seen_ts"] = ts
    state["last_wake_at"] = datetime.now(timezone.utc).isoformat()
    if rc is not None:
        state["last_wake_rc"] = rc
    state["room_id"] = rid
    processed = list(state.get("processed_ids") or [])
    if mid not in processed:
        processed.append(mid)
    state["processed_ids"] = processed[-100:]
    # Clear in-flight so redelivery after success cannot re-wake.
    inflight = [x for x in list(state.get("in_flight_ids") or []) if x != mid]
    state["in_flight_ids"] = inflight[-50:]
    if clear_session:
        set_room_session_id(state, rid, None)
        set_room_cwd(state, rid, None)
    else:
        if grok_session_id:
            set_room_session_id(state, rid, grok_session_id)
        if project_cwd:
            set_room_cwd(state, rid, project_cwd)
    save_state(state)


def _set_in_flight(
    mid: str,
    *,
    active: bool,
    text: str | None = None,
) -> None:
    """Track mids currently running a wake (blocks re-enqueue / double wake)."""
    if not mid:
        return
    state = load_state()
    inflight = list(state.get("in_flight_ids") or [])
    texts = dict(state.get("in_flight_texts") or {})
    if active:
        if mid not in inflight:
            inflight.append(mid)
        if text is not None and callable(normalize_wake_text):
            texts[str(mid)] = normalize_wake_text(text)
        elif text is not None:
            texts[str(mid)] = str(text).strip()
    else:
        inflight = [x for x in inflight if x != mid]
        texts.pop(str(mid), None)
    state["in_flight_ids"] = inflight[-50:]
    state["in_flight_texts"] = texts
    save_state(state)


# Last decide_enqueue kind per mid (best-effort; for caller skip-log honesty).
_LAST_ENQUEUE_KIND: dict[str, str] = {}


def _log_enqueue_skip(mid: str | None, *, context: str = "") -> None:
    """Honest skip log — never claim 'processed' for busy_ack/duplicate."""
    m = str(mid or "")
    kind = _LAST_ENQUEUE_KIND.pop(m, None) if m else None
    ctx = f" {context}" if context else ""
    if kind:
        log(f"enqueue skipped mid={m} kind={kind}{ctx}")
    else:
        log(f"enqueue skipped mid={m} (busy/duplicate/done){ctx}")


def _schedule_busy_react(msg_id: str, *, identity: str = "grok") -> None:
    """Busy react with fallback to eyes if primary shortname fails (S5)."""
    if not wake_react_enabled() or not (msg_id or "").strip():
        return
    mid = msg_id.strip()
    busy_em = (os.environ.get("RC_WAKE_REACT_BUSY") or "repeat").strip() or "repeat"
    ident = identity

    def _run() -> None:
        ok = react_message(mid, busy_em, should_react=True, identity=ident)
        if not ok and busy_em != "eyes":
            react_message(mid, "eyes", should_react=True, identity=ident)

    threading.Thread(target=_run, name=f"rc-react-busy-{busy_em[:12]}", daemon=True).start()


def _enqueue_pending(
    msg: dict,
    rid: str,
    room_name: str,
    room_type: str | None,
    *,
    target: str = "grok",
    collab: bool = False,
    retry_of: str | None = None,
) -> bool:
    """
    Queue a message for wake. Returns True when the pending queue changed.

    IMP-23 S5: uses wake_inflight_ux.decide_enqueue when available — busy ack,
    follow-up on edit-while-in-flight, pending text update, log dedupe, and
    immediate principal 👀 on new enqueue. Falls back to legacy silent-skip
    behavior if the pure module is missing.
    """
    mid = msg.get("_id")
    if not mid:
        return False
    author = ((msg.get("u") or {}).get("username") or PRINCIPAL)
    text = (msg.get("msg") or "").strip()
    msg_subset = {
        "ts": msg.get("ts"),
        "file": msg.get("file"),
        "files": msg.get("files"),
        "attachments": msg.get("attachments"),
        "mentions": msg.get("mentions"),
        "u": msg.get("u") or {"username": PRINCIPAL},
    }
    ident = (OPERATOR or target or COLLAB_GROK).strip().lower() or COLLAB_GROK

    # --- IMP-23 S5 pure policy path ---
    if callable(decide_enqueue) and callable(apply_decision_to_pending):
        state = load_state()
        decision = decide_enqueue(
            mid=str(mid),
            rid=rid,
            room_name=room_name,
            room_type=room_type,
            text=text,
            author=author,
            msg_subset=msg_subset,
            target=target,
            collab=collab,
            retry_of=retry_of,
            processed_ids=list(state.get("processed_ids") or []),
            in_flight_ids=list(state.get("in_flight_ids") or []),
            pending_wakes=list(state.get("pending_wakes") or []),
            in_flight_texts=dict(state.get("in_flight_texts") or {}),
            now_iso=datetime.now(timezone.utc).isoformat(),
        )
        pending = apply_decision_to_pending(
            list(state.get("pending_wakes") or []),
            decision,
            max_pending=30,
        )
        if decision.queue_changed and decision.pending_item is not None:
            # Mark immediate-ack rows so process path does not double 👀.
            if decision.ui_action == "ack_start":
                for p in pending:
                    if (
                        isinstance(p, dict)
                        and str(p.get("mid") or "") == str(decision.pending_item.get("mid"))
                    ):
                        p["acked_on_enqueue"] = True
            state["pending_wakes"] = pending
        # Log dedupe
        if callable(should_emit_decision_log):
            emit, dedupe = should_emit_decision_log(
                last_logged=dict(state.get("enqueue_log_dedupe") or {}),
                mid=str(mid),
                kind=decision.kind,
                now=time.time(),
                ttl_s=float(os.environ.get("RC_INFLIGHT_LOG_TTL_S") or 60),
            )
            state["enqueue_log_dedupe"] = dedupe
            if emit:
                log(decision.log_line)
        else:
            log(decision.log_line)
        save_state(state)
        # UI: reactions only (no chat.update)
        src = decision.source_mid or str(mid)
        if decision.ui_action == "ack_start" and src:
            schedule_principal_ack(src, identity=ident)
        elif decision.ui_action == "busy" and src:
            _schedule_busy_react(src, identity=ident)
        # Expose last decision kind for honest caller skip logs (Task 14).
        _LAST_ENQUEUE_KIND[str(mid)] = decision.kind
        return bool(decision.queue_changed)

    # --- Legacy fallback (pre-S5) ---
    state = load_state()
    processed = list(state.get("processed_ids") or [])
    if mid in processed:
        return False
    inflight = list(state.get("in_flight_ids") or [])
    if mid in inflight:
        log(f"enqueue skip in-flight mid={mid}")
        return False
    pending = list(state.get("pending_wakes") or [])
    if any(isinstance(p, dict) and p.get("mid") == mid for p in pending):
        return False
    pending.append(
        {
            "mid": mid,
            "rid": rid,
            "room_name": room_name,
            "room_type": room_type,
            "ts": msg.get("ts"),
            "text": text,
            "file": msg.get("file"),
            "files": msg.get("files"),
            "attachments": msg.get("attachments"),
            "mentions": msg.get("mentions"),
            "u": msg.get("u") or {"username": PRINCIPAL},
            "author": author,
            "target": (target or "grok").strip().lower(),
            "collab": bool(collab),
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "is_empty_reply_retry": bool(retry_of),
            "retry_of": retry_of,
        }
    )
    state["pending_wakes"] = pending[-30:]
    save_state(state)
    return True


def wake_agy_cli(
    *,
    cwd: str,
    prompt_text: str,
    conversation_id: str | None,
    room_id: str,
    mid: str,
) -> tuple[int, str, str | None, str]:
    """
    Run local agy CLI via skill helper (NF-SPEC-04 FR-A18–A22).

    Returns (rc, stdout_body, new_or_same_conversation_id, log_text).
    Never calls MCP agy_*. Serialized globally via agy_cli_lock.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    short = (mid or "x")[:8]
    prompt_path = LOG_DIR / f"agy-prompt-{stamp}-{short}.md"
    log_path = LOG_DIR / f"agy-run-{stamp}-{short}.log"
    state_path = LOG_DIR / f"agy-conv-{stamp}-{short}.txt"
    reply_capture = LOG_DIR / f"agy-reply-{stamp}-{short}.txt"
    prompt_path.write_text(prompt_text, encoding="utf-8")

    plan = build_agy_helper_plan(
        cwd=cwd,
        prompt_file=str(prompt_path),
        log_file=str(log_path),
        state_file=str(state_path),
        conversation_id=conversation_id,
        env=os.environ,
    )
    assert_no_mcp_agy_in_argv(plan.argv)
    log(
        f"collab wake target=agy mode={plan.mode} uuid={conversation_id or 'none'} "
        f"cwd={cwd} room={room_id}"
    )
    env = os.environ.copy()
    env["PATH"] = (
        f"{Path.home() / '.local' / 'bin'}:{Path.home() / '.grok' / 'bin'}:"
        f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{env.get('PATH', '')}"
    )
    env["HOME"] = str(Path.home())
    timeout_s = agy_wake_timeout_s()
    lock = agy_cli_lock()
    with lock:
        try:
            proc = subprocess.run(
                plan.argv,
                cwd=cwd,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            rc = int(proc.returncode)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
        except subprocess.TimeoutExpired as e:
            rc = 124
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = f"agy wake timeout after {timeout_s}s"
            log(f"collab agy timeout room={room_id} limit_s={timeout_s}")
        except OSError as e:
            rc = 127
            stdout = ""
            stderr = str(e)
            log(f"collab agy spawn failed: {e}")

    combined = stdout
    if stderr and not stdout.strip():
        combined = stderr
    try:
        reply_capture.write_text(stdout if stdout.strip() else "", encoding="utf-8")
    except OSError:
        pass
    log_text = ""
    try:
        if log_path.is_file():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        log_text = stderr or ""
    if not log_text:
        log_text = f"stdout:\n{stdout}\nstderr:\n{stderr}\n"

    new_cid = conversation_id
    try:
        if state_path.is_file():
            pinned = state_path.read_text(encoding="utf-8").strip()
            if pinned:
                new_cid = pinned
    except OSError:
        pass
    if not new_cid and log_text:
        m = re.search(
            r"Created conversation ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12})",
            log_text,
            re.I,
        )
        if m:
            new_cid = m.group(1)

    log(
        f"collab agy rc={rc} uuid_captured={bool(new_cid)} "
        f"stdout_len={len(stdout)} room={room_id}"
    )
    body = stdout.strip()
    if not body and rc != 0:
        body = format_agy_cli_error(rc, stderr_tail=stderr or log_text, log_name=log_path.name)
    elif not body:
        body = format_agy_cli_error(rc or 1, stderr_tail=log_text, log_name=log_path.name)
    return rc, body, new_cid, log_text


def _process_agy_collab_item(item: dict) -> None:
    """
    Agy-target collab turn: 👀 on principal → activity bubble as agy → finalize.
    """
    mid = item.get("mid")
    rid = item.get("rid") or ""
    room_name = item.get("room_name") or rid
    room_type = item.get("room_type")
    caption = (item.get("text") or "").strip()
    ts = item.get("ts")
    author = (item.get("author") or (item.get("u") or {}).get("username") or "?").strip()
    processed = list(load_state().get("processed_ids") or [])
    if mid in processed:
        log(f"skip already-processed mid={mid}")
        return

    # IMP-23 S5: claim in-flight so same mid redelivery busy-acks (agy parity).
    if mid:
        _set_in_flight(str(mid), active=True, text=caption)

    st = load_state()
    project_cwd, reason = _resolve_room_cwd_info(rid, room_name, room_type, st)
    ensure_collab_budget(st, rid)
    collab = get_collab_room_state(st, rid)
    cid = get_agy_conversation_id(st, rid)
    inject = build_agy_l3_inject(
        mention_body=caption,
        room_id=rid,
        room_name=room_name or rid,
        cwd=project_cwd,
        author=author,
        collab=collab,
        write_scope="read-only",
    )
    save_state(st)
    log(
        f"drain collab agy room={room_name} mid={mid} author={author} "
        f"cwd={project_cwd} ({reason}) uuid={cid or 'NEW'}"
    )

    # Ack on principal message (👀 kept after finalize).
    # IMP-23 S5: source_mid for follow-ups; skip if acked on enqueue.
    ack_mid = str(item.get("source_mid") or mid or "")
    if ack_mid and not item.get("acked_on_enqueue"):
        schedule_principal_ack(ack_mid, identity=COLLAB_AGY)

    thinking_msg_id = post_thinking_placeholder(rid, identity=COLLAB_AGY)
    if not thinking_msg_id:
        log(f"failed to post agy activity bubble room={room_name} — continuing anyway")

    # Optional RUNNING_META as agy (reuse F2 formatter shape)
    if thinking_msg_id and wake_meta_enabled():
        try:
            meta = format_running_meta(
                room_name=room_name or rid,
                cwd=project_cwd,
                approval_mode="agy-cli",
                phase="starting",
                elapsed_s=0.0,
                session_short=(cid or "")[:8],
                max_chars=stream_max_chars(),
            )
            update_thinking_meta(rid, thinking_msg_id, meta, identity=COLLAB_AGY)
        except Exception as e:
            log(f"agy meta failed: {e}")

    rc, body, new_cid, _log_text = wake_agy_cli(
        cwd=project_cwd,
        prompt_text=inject,
        conversation_id=cid,
        room_id=rid,
        mid=mid or "x",
    )

    st2 = load_state()
    if new_cid:
        set_agy_conversation_id(st2, rid, new_cid)
    hop = record_collab_hop(
        st2,
        rid,
        author=author,
        target=COLLAB_AGY,
        hop_at=datetime.now(timezone.utc).isoformat(),
    )
    if hop.get("paused_reason") == "budget" and not collab.get("paused_reason"):
        log(
            f"collab pause reason=budget epoch={hop.get('epoch')} "
            f"count={hop.get('hop_count_epoch')}/{hop.get('hop_budget_epoch')}"
        )
    save_state(st2)

    if thinking_msg_id:
        ok = False
        auth_err_msg = ""
        try:
            ok = finalize_thinking_message(rid, thinking_msg_id, body, identity=COLLAB_AGY)
        except RuntimeError as e:
            if "rc credentials missing" in str(e).lower():
                auth_err_msg = str(e)
            else:
                raise
        log(
            f"finalize agy activity msg={thinking_msg_id} ok={ok} "
            f"body_len={len(body)} rc={rc} room={room_name}"
        )
        if auth_err_msg:
            post_as_grok(rid, f"🚨 **Authentication Error**: {auth_err_msg}. Stopping.")
    else:
        post_message_get_id(rid, body, identity=COLLAB_AGY)

    _mark_processed(
        mid,
        rid,
        ts if isinstance(ts, str) else None,
        rc=rc,
        project_cwd=project_cwd,
    )
    if mid:
        _set_in_flight(str(mid), active=False)
    if rc != 0:
        log(f"agy collab wake failed rc={rc} room={room_name} mid={mid}")


def _process_pending_item(item: dict) -> None:
    """
    Run one queued wake: 👀 on principal → activity bubble → finalize.

    1) React 👀 on the principal message (kept after done)
    2) Post one activity bubble (thought stream while wake runs)
    3) Wake Grok; final answer to reply file
    4) chat.update that bubble with the answer only
    """
    target = (item.get("target") or "grok").strip().lower()
    if target == COLLAB_AGY or (item.get("collab") and target == "agy"):
        _process_agy_collab_item(item)
        return

    mid = item.get("mid")
    rid = item.get("rid") or ""
    room_name = item.get("room_name") or rid
    room_type = item.get("room_type")
    caption = item.get("text") or ""
    ts = item.get("ts")
    is_collab = bool(item.get("collab"))
    author = (item.get("author") or (item.get("u") or {}).get("username") or PRINCIPAL)
    processed = list(load_state().get("processed_ids") or [])
    if mid in processed:
        log(f"skip already-processed mid={mid}")
        return
    is_empty_reply_retry = bool(item.get("is_empty_reply_retry"))
    # Claim in-flight before any heavy work so WS redelivery cannot double-wake.
    if mid:
        _set_in_flight(str(mid), active=True, text=caption)

    # Rebuild enough of the RC payload for STT (Path A voice notes).
    raw_for_stt = {
        "_id": mid,
        "rid": rid,
        "msg": caption,
        "ts": ts,
        "file": item.get("file"),
        "files": item.get("files"),
        "attachments": item.get("attachments"),
        "u": item.get("u") or {"username": PRINCIPAL},
    }
    text = resolve_message_text_for_wake(raw_for_stt)
    if not text:
        text = empty_attachment_wake_stub()
    if is_empty_reply_retry:
        text = (
            "[Operator recovery] Your previous attempt ended Cancelled/incomplete "
            "before writing the reply file. Write the complete final answer for the "
            "principal's message to the reply file only. Do not restate this recovery "
            "banner. Original request:\n\n"
            + text
        )

    msg = {
        "_id": mid,
        "rid": rid,
        "msg": text,
        "ts": ts,
        "u": item.get("u") or {"username": PRINCIPAL},
    }
    st = load_state()
    sid_pin = get_room_session_id(st, rid)
    project_cwd, reason = _resolve_room_cwd_info(rid, room_name, room_type, st)
    # IMP-23 S7: missing/invalid cwd → FINAL_ERR, clear bad pin, no spawn.
    if callable(validate_wake_cwd) and callable(format_missing_cwd_err):
        cwd_ok, cwd_why = validate_wake_cwd(project_cwd)
        if not cwd_ok:
            log(f"cwd invalid room={room_name} mid={mid} path={project_cwd} ({cwd_why})")
            pin = get_room_cwd(st, rid)
            if pin and not Path(str(pin)).is_dir():
                set_room_cwd(st, rid, None)
                save_state(st)
            thinking_msg_id = post_thinking_placeholder(rid, identity=OPERATOR or COLLAB_GROK)
            body = format_missing_cwd_err(
                project_cwd, mid_short=(str(mid)[:8] if mid else None)
            )
            if thinking_msg_id:
                finalize_thinking_message(
                    rid, thinking_msg_id, body, identity=OPERATOR or COLLAB_GROK
                )
            if mid:
                _mark_processed(str(mid), rid, ts, rc=1, project_cwd=None)
                _set_in_flight(str(mid), active=False)
            return
    rtype_for_mode = room_type
    if not rtype_for_mode and (room_name or "").lower().startswith("dm"):
        rtype_for_mode = "d"
    base_mode = resolve_approval_mode(
        room_type=rtype_for_mode, room_name=room_name or ""
    )
    approval_mode, consume_once = effective_approval_for_room(
        st, rid, base_mode
    )
    model_pin = get_room_model(st, rid)
    effort_pin = get_room_effort(st, rid)
    gblock = goal_prompt_block(st, rid)
    collab_block = ""
    if is_collab:
        ensure_collab_budget(st, rid)
        collab_state = get_collab_room_state(st, rid)
        collab_block = build_grok_collab_inject_block(
            collab=collab_state,
            inject_template=load_grok_inject_template(),
            author=str(author),
        )
    # Retain last non-command content for /retry
    set_last_content(st, rid, text, mid=mid or "")
    save_state(st)
    op_target = (OPERATOR or COLLAB_GROK).strip().lower() or COLLAB_GROK
    log(
        f"drain wake room={room_name} mid={mid} target={op_target} collab={is_collab} "
        f"retry={is_empty_reply_retry} approval_mode={approval_mode} "
        f"cwd={project_cwd} ({reason}) "
        f"resume={sid_pin or 'NEW'} model={model_pin or '-'} effort={effort_pin or '-'} "
        f"goal={'yes' if gblock else 'no'}"
    )

    # Ack on principal message (👀 kept; not cleared on finalize).
    # IMP-23 S5: use source_mid for follow-ups; skip if already acked on enqueue.
    ack_mid = str(item.get("source_mid") or mid or "")
    if ack_mid and not is_empty_reply_retry and not item.get("acked_on_enqueue"):
        schedule_principal_ack(
            ack_mid, identity=(OPERATOR or COLLAB_GROK).strip().lower() or COLLAB_GROK
        )

    # One agent bubble: reuse on empty-reply recovery; else post new activity bubble.
    thinking_msg_id: str | None = None
    if is_empty_reply_retry and mid:
        st_b = load_state()
        thinking_msg_id = (st_b.get("activity_bubbles") or {}).get(str(mid)) or None
        if thinking_msg_id:
            log(f"reuse activity bubble msg={thinking_msg_id} mid={mid} recovery")
    if not thinking_msg_id:
        thinking_msg_id = post_thinking_placeholder(rid, identity=COLLAB_GROK)
        if not thinking_msg_id:
            log(
                f"failed to post activity bubble room={room_name} — continuing wake anyway"
            )
        elif mid:
            st_b = load_state()
            bubbles = dict(st_b.get("activity_bubbles") or {})
            bubbles[str(mid)] = thinking_msg_id
            # Cap map size
            if len(bubbles) > 40:
                for k in list(bubbles.keys())[: len(bubbles) - 40]:
                    bubbles.pop(k, None)
            st_b["activity_bubbles"] = bubbles
            save_state(st_b)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    reply_path = LOG_DIR / f"wake-reply-{int(time.time())}-{mid[:8] if mid else 'x'}.txt"
    # Ensure empty file exists so the model can open/write it
    try:
        reply_path.write_text("", encoding="utf-8")
    except OSError as e:
        log(f"reply file create failed: {e}")

    # Safety net: missing project dir must finalize the activity bubble, not hang on "…".
    # Auto-create is default ON; this path hits when kill-switched or resolve failed.
    cwd_path = Path(project_cwd) if project_cwd else None
    if cwd_path is None or not cwd_path.is_dir():
        missing = str(project_cwd or "(unset)")
        err_body = (
            f"**Wake failed: project directory missing**\n\n"
            f"`{missing}` does not exist (resolve reason: `{reason}`).\n\n"
            f"Expected auto-create (`RC_AUTO_CREATE_PROJECTS=1`, default on). "
            f"If this keeps happening, check operator env/logs, create the folder, "
            f"or map the channel in `channel_projects.json`.\n"
        )
        log(
            f"cwd missing room={room_name} mid={mid} reason={reason} path={missing} "
            f"— finalizing FINAL_ERR without wake"
        )
        if thinking_msg_id:
            ok = finalize_thinking_message(
                rid,
                thinking_msg_id,
                err_body,
                identity=COLLAB_GROK,
                thought_text="",
            )
            log(
                f"finalize activity msg={thinking_msg_id} phase={PHASE_FINAL_ERR} "
                f"ok={ok} body_len={len(err_body)} room={room_name} missing_cwd=1"
            )
            if not ok:
                post_as_grok(rid, err_body)
        else:
            post_as_grok(rid, err_body)
        if mid:
            try:
                st_c = load_state()
                bubbles = dict(st_c.get("activity_bubbles") or {})
                bubbles.pop(str(mid), None)
                st_c["activity_bubbles"] = bubbles
                save_state(st_c)
            except Exception:
                pass
        _mark_processed(
            mid,
            rid,
            ts if isinstance(ts, str) else None,
            rc=1,
            grok_session_id=sid_pin,
            project_cwd=project_cwd,
        )
        return

    # Non-final bubble updates: thought stream when RC_WAKE_STREAM on; else meta heartbeat.
    # stream_finalized must be set before FINAL_* so late callbacks cannot overwrite final.
    # Separate throttles so starting meta never starves thought updates.
    meta_throttle = StreamThrottle.from_env()
    thought_throttle = StreamThrottle.from_env()
    rate_backoff = RateLimitBackoff.from_env() if RateLimitBackoff is not None else None
    wake_t0 = time.monotonic()
    stop_meta_hb = threading.Event()
    stream_finalized = threading.Event()
    meta_hb_thread: threading.Thread | None = None
    thought_flush_thread: threading.Thread | None = None
    meta_session_short = (sid_pin or "")[:8]
    thoughts = ThoughtAccumulator()
    stream_on = wake_stream_enabled()
    thought_updates = 0
    first_thought_at: float | None = None
    last_pushed_thought_len = 0
    thoughts_dirty = threading.Event()
    first_min_chars = thought_first_min_chars()
    first_wait_s = thought_first_wait_ms() / 1000.0
    flush_s = thought_flush_ms() / 1000.0
    op_identity = (OPERATOR or COLLAB_GROK).strip().lower() or COLLAB_GROK

    def _push_meta(phase: str = "running", force: bool = False) -> None:
        if stream_finalized.is_set() or stop_meta_hb.is_set():
            return
        if not thinking_msg_id or not wake_meta_enabled():
            return
        # Prefer thought stream over meta once we have thought text.
        if stream_on and thoughts.text.strip():
            return
        # IMP-23 S1: yield non-final updates while 429 backoff active.
        if rate_backoff is not None and not rate_backoff.allow_nonfinal():
            return
        if not meta_throttle.allow(force=force):
            return
        if stream_finalized.is_set() or stop_meta_hb.is_set():
            return
        body = format_running_meta(
            room_name=room_name or rid,
            cwd=project_cwd,
            approval_mode=approval_mode,
            phase=phase,
            elapsed_s=time.monotonic() - wake_t0,
            session_short=meta_session_short,
            max_chars=stream_max_chars(),
        )
        if stream_finalized.is_set() or stop_meta_hb.is_set():
            return
        ok_meta = update_thinking_meta(rid, thinking_msg_id, body, identity=op_identity)
        if rate_backoff is not None:
            if ok_meta:
                rate_backoff.note_success()
            else:
                rate_backoff.note_429()
        log(
            f"stream meta phase={PHASE_RUNNING_META}/{phase} msg={thinking_msg_id} "
            f"ok={ok_meta} updates={meta_throttle.updates} room={room_name}"
        )

    def _ready_for_first_thought_paint() -> bool:
        """Avoid painting a lone first token (often 'The') for a long stall."""
        if thought_updates > 0:
            return True
        n = len(thoughts.text)
        if n >= first_min_chars:
            return True
        if first_thought_at is None:
            return False
        return (time.monotonic() - first_thought_at) >= first_wait_s

    def _flush_thoughts(*, force: bool = False) -> None:
        nonlocal thought_updates, last_pushed_thought_len
        if stream_finalized.is_set() or not thinking_msg_id:
            return
        if not thoughts.text.strip():
            return
        if len(thoughts.text) == last_pushed_thought_len and not force:
            return
        if not _ready_for_first_thought_paint():
            return
        # IMP-23 S1: drop intermediate thought paints under 429 backoff.
        if rate_backoff is not None and not rate_backoff.allow_nonfinal():
            return
        if not thought_throttle.allow(force=force or thought_updates == 0):
            return
        if stream_finalized.is_set():
            return
        body = thoughts.format(max_chars=stream_max_chars())
        # IMP-23 S4: use this operator's identity (never hardcode grok for peers).
        ok_thought = update_thinking_meta(
            rid, thinking_msg_id, body, identity=op_identity
        )
        if rate_backoff is not None:
            if ok_thought:
                rate_backoff.note_success()
            else:
                wait_b = rate_backoff.note_429()
                log(f"stream thought 429-backoff wait={wait_b:.1f}s room={room_name}")
        last_pushed_thought_len = len(thoughts.text)
        thought_updates += 1
        log(
            f"stream thought msg={thinking_msg_id} ok={ok_thought} "
            f"n={thought_updates} chars={len(body)} room={room_name}"
        )

    def _on_stream_event(event: dict) -> None:
        nonlocal first_thought_at
        if stream_finalized.is_set() or not thinking_msg_id:
            return
        if not thoughts.consume_event(event):
            return
        if first_thought_at is None:
            first_thought_at = time.monotonic()
        # Only mark dirty — flusher owns chat.update rate (avoid double-fire → 429).
        thoughts_dirty.set()

    # Meta heartbeat only when not streaming thoughts.
    if thinking_msg_id and wake_meta_enabled() and not stream_on:
        _push_meta(phase="starting", force=True)

        def _meta_hb() -> None:
            while not stop_meta_hb.wait(stream_heartbeat_s()):
                if stream_finalized.is_set():
                    return
                _push_meta(phase="running", force=False)

        meta_hb_thread = threading.Thread(
            target=_meta_hb, name="rc-wake-meta-hb", daemon=True
        )
        meta_hb_thread.start()
    elif thinking_msg_id and stream_on:
        # Background flusher: steady bubble updates even if events arrive in bursts.
        def _thought_flusher() -> None:
            while not stop_meta_hb.wait(flush_s):
                if stream_finalized.is_set():
                    return
                if thoughts_dirty.is_set() or (
                    first_thought_at is not None and thought_updates == 0
                ):
                    _flush_thoughts(force=False)
                    if len(thoughts.text) == last_pushed_thought_len:
                        thoughts_dirty.clear()

        thought_flush_thread = threading.Thread(
            target=_thought_flusher, name="rc-wake-thought-flush", daemon=True
        )
        thought_flush_thread.start()

    goal_and_collab = gblock
    if collab_block:
        goal_and_collab = (gblock + "\n\n" if gblock else "") + collab_block
    prompt = build_prompt(
        [msg],
        rid,
        room_name=room_name,
        project_cwd=project_cwd,
        project_reason=reason,
        thinking_msg_id=thinking_msg_id or "",
        reply_file=str(reply_path),
        approval_mode=approval_mode,
        goal_block=goal_and_collab,
    )
    wake_result = wake_grok(
        prompt,
        max_turns=os.environ.get("RC_WAKE_MAX_TURNS", "100"),
        room_id=rid,
        resume_session_id=sid_pin,
        project_cwd=project_cwd,
        approval_mode=approval_mode,
        model=model_pin,
        effort=effort_pin,
        on_stream_event=_on_stream_event if stream_on else None,
    )
    # Compat: tests may still mock wake_grok → (rc, sid)
    log_path: Path | None = None
    log_text = ""
    if isinstance(wake_result, tuple) and len(wake_result) >= 4:
        rc, sid, log_path, log_text = wake_result[0], wake_result[1], wake_result[2], wake_result[3]
    elif isinstance(wake_result, tuple) and len(wake_result) == 2:
        rc, sid = wake_result[0], wake_result[1]
    else:
        rc, sid = 1, None

    # Stop non-final updates before final: flags first so late thoughts cannot win.
    # Do NOT force another thought chat.update here — that races FINAL and causes 429.
    stop_meta_hb.set()
    stream_finalized.set()
    if meta_hb_thread is not None and meta_hb_thread.is_alive():
        meta_hb_thread.join(timeout=2.0)
        if meta_hb_thread.is_alive():
            log(f"meta heartbeat thread did not exit promptly room={room_name}")
    if thought_flush_thread is not None and thought_flush_thread.is_alive():
        thought_flush_thread.join(timeout=2.0)
        if thought_flush_thread.is_alive():
            log(f"thought flusher did not exit promptly room={room_name}")

    if consume_once:
        st2 = load_state()
        consume_once_elevation(st2, rid)
        save_state(st2)
        log(f"elevation once consumed room={room_name}")

    # Reply file can land slightly after process exit; poll briefly.
    reply_body = ""
    for _poll in range(6):
        try:
            if reply_path.is_file():
                reply_body = reply_path.read_text(
                    encoding="utf-8", errors="replace"
                ).strip()
        except OSError as e:
            log(f"reply file read failed: {e}")
            break
        if reply_body:
            break
        time.sleep(0.35)

    if not log_text and log_path and Path(log_path).is_file():
        try:
            log_text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            log_text = ""

    # Hermes quiet mode often writes the answer to stdout only; use as fallback.
    if not reply_body and wake_backend_from_env() == "hermes" and log_text:
        fallback = extract_hermes_reply_from_output(log_text)
        if fallback:
            reply_body = fallback
            log(f"hermes reply fallback from stdout chars={len(reply_body)}")

    log_basename = Path(log_path).name if log_path else ""
    # Disk reply file only — stream salvage is a last resort, not a "done" signal.
    reply_file_empty = not bool((reply_body or "").strip())
    final_body, phase, terminal = choose_final_body(
        reply_file_body=reply_body,
        rc=rc,
        log_text=log_text,
        approval_mode=approval_mode,
        log_basename=log_basename,
        compose_ok=compose_unified_reply,
        mid_short=(str(mid)[:8] if mid else None),
    )

    # One operator-owned recovery: Cancelled/incomplete with empty reply → requeue once.
    # Reuses the same principal mid after releasing in-flight so the bubble can finalize.
    sr_l = (terminal.stop_reason or "").lower()

    # B5 R5-1: salvage substantive thought stream only after a failed recovery
    # attempt (or when auto-retry is off). Salvage must not skip auto-retry —
    # that was posting half-finished stream text with a "Recovered…" footnote
    # (principal 2026-07-16).
    if (
        phase == PHASE_FINAL_ERR
        and reply_file_empty
        and thoughts.text.strip()
        and (
            is_empty_reply_retry
            or not wake_auto_retry_enabled()
            or sr_l not in ("cancelled", "canceled")
            or rc != 0
        )
    ):
        salvaged_from_thoughts = extract_salvageable_body(
            thoughts.text, stop_reason=terminal.stop_reason
        )
        if salvaged_from_thoughts:
            reply_body = salvaged_from_thoughts
            log(
                f"thought-stream salvage chars={len(reply_body)} room={room_name} "
                f"mid={mid}"
            )
            final_body, phase, terminal = choose_final_body(
                reply_file_body=reply_body,
                rc=rc,
                log_text=log_text,
                approval_mode=approval_mode,
                log_basename=log_basename,
                compose_ok=compose_unified_reply,
                mid_short=(str(mid)[:8] if mid else None),
            )

    # Auto-retry clean Cancelled (rc=0) when the **reply file** is empty.
    # IMP-23 S2: skip retry when stream salvage already produced FINAL_OK, or when
    # terminal stream text is strongly salvageable (finalize that instead of re-wake).
    should_retry_empty = (
        wake_auto_retry_enabled()
        and not is_empty_reply_retry
        and reply_file_empty
        and sr_l in ("cancelled", "canceled")
        and rc == 0
        and bool(mid)
        and phase == PHASE_FINAL_ERR
    )
    if should_retry_empty and callable(should_skip_empty_reply_retry):
        if should_skip_empty_reply_retry(
            phase=phase,
            reply_file_empty=reply_file_empty,
            stop_reason=terminal.stop_reason,
            rc=rc,
            already_retry=is_empty_reply_retry,
            auto_retry_enabled=wake_auto_retry_enabled(),
            stream_text=terminal.text,
        ):
            # Prefer salvage over re-wake when stream text is strong.
            salv_stream = extract_salvageable_body(
                terminal.text, stop_reason=terminal.stop_reason
            )
            if salv_stream and phase == PHASE_FINAL_ERR:
                log(
                    f"empty-reply recovery skipped stream-salvage chars={len(salv_stream)} "
                    f"room={room_name} mid={mid}"
                )
                final_body, phase, terminal = choose_final_body(
                    reply_file_body=salv_stream,
                    rc=rc,
                    log_text=log_text,
                    approval_mode=approval_mode,
                    log_basename=log_basename,
                    compose_ok=compose_unified_reply,
                    mid_short=(str(mid)[:8] if mid else None),
                )
            should_retry_empty = False
            if phase == PHASE_FINAL_OK:
                log(
                    f"empty-reply recovery skipped phase=FINAL_OK room={room_name} mid={mid}"
                )
    if should_retry_empty:
        # B5 R5-3: per-room retry cooldown.
        cool_s = retry_cooldown_s()
        st_cd = load_state()
        last_map = dict(st_cd.get("empty_reply_retry_at") or {})
        last_ts = float(last_map.get(str(rid)) or 0.0)
        now_m = time.monotonic()
        # Persist wall time so restarts still cool down roughly.
        last_wall = float(last_map.get(f"{rid}:wall") or 0.0)
        now_wall = time.time()
        if last_wall and (now_wall - last_wall) < cool_s:
            log(
                f"empty-reply recovery blocked cooldown room={room_name} mid={mid} "
                f"cool_s={cool_s} elapsed={now_wall - last_wall:.1f}"
            )
            should_retry_empty = False
        else:
            last_map[str(rid)] = now_m
            last_map[f"{rid}:wall"] = now_wall
            # Cap map size
            if len(last_map) > 80:
                for k in list(last_map.keys())[: len(last_map) - 80]:
                    last_map.pop(k, None)
            st_cd["empty_reply_retry_at"] = last_map
            save_state(st_cd)

    if should_retry_empty:
        # B5 R5-2: retry under completing operator, not hardcoded grok.
        retry_target = (OPERATOR or COLLAB_GROK).strip().lower() or COLLAB_GROK
        log(
            f"empty-reply recovery scheduled mid={mid} stopReason={terminal.stop_reason} "
            f"room={room_name} target={retry_target} is_empty_reply_retry=0"
        )
        _set_in_flight(str(mid), active=False)
        # Do not mark processed yet — requeue a recovery wake.
        retry_msg = {
            "_id": mid,
            "rid": rid,
            "msg": caption,
            "ts": ts,
            "file": item.get("file"),
            "files": item.get("files"),
            "attachments": item.get("attachments"),
            "u": item.get("u") or {"username": PRINCIPAL},
        }
        if _enqueue_pending(
            retry_msg,
            rid,
            room_name,
            room_type,
            target=retry_target,
            collab=is_collab,
            retry_of=str(mid),
        ):
            # Finalize bubble with interim notice so principal sees progress, not silence.
            if thinking_msg_id:
                interim = compose_final_with_thoughts(
                    (
                        "(First attempt ended incomplete — retrying once to write "
                        "the final answer…)"
                    ),
                    thoughts.text,
                )
                update_message(
                    rid,
                    thinking_msg_id,
                    interim,
                    identity=retry_target,
                    retries=3,
                    retry_base_s=1.5,
                )
            # Store bubble id so retry can finalize the same message.
            st_r = load_state()
            bubbles = dict(st_r.get("activity_bubbles") or {})
            bubbles[str(mid)] = thinking_msg_id
            st_r["activity_bubbles"] = bubbles
            save_state(st_r)
            threading.Thread(
                target=_drain_pending_wakes, name="rc-drain-retry", daemon=True
            ).start()
            return

    # Persist telemetry for /status and health (NF-SPEC-02 FR-S13)
    try:
        st3 = load_state()
        st3["last_stop_reason"] = terminal.stop_reason
        st3["last_stream_at"] = datetime.now(timezone.utc).isoformat()
        st3["last_wake_phase"] = phase
        save_state(st3)
        write_health_snapshot(
            ws_connected=True,
            rooms_count=0,
            extra={
                "last_stop_reason": terminal.stop_reason,
                "last_stream_at": st3["last_stream_at"],
                "last_wake_phase": phase,
                "last_wake_rc": rc,
                "last_thought_updates": thought_updates,
            },
        )
    except Exception as e:
        log(f"telemetry persist failed: {e}")

    if thinking_msg_id:
        # Always attempt final update (FR-S7); rate limits do not apply.
        # stream_finalized already set — late thoughts must not overwrite this.
        # Keep full thought stream above the final answer (*Thoughts* / rule / answer).
        # On recovery, merge prior bubble thoughts if this attempt streamed none.
        thought_for_final = thoughts.text
        if is_empty_reply_retry and not thought_for_final.strip():
            try:
                # Best-effort: leave thought_for_final empty; prior interim may have
                # already shown thoughts. Final answer alone still acceptable.
                pass
            except Exception:
                pass
        ok = False
        auth_err_msg = ""
        try:
            ok = finalize_thinking_message(
                rid,
                thinking_msg_id,
                final_body,
                identity=(OPERATOR or COLLAB_GROK),
                thought_text=thought_for_final,
                stream_throttle=thought_throttle,
            )
        except RuntimeError as e:
            if "rc credentials missing" in str(e).lower():
                auth_err_msg = str(e)
            else:
                raise
        # Principal 👀 is intentionally left in place (no terminal react swap).
        log(
            f"finalize activity msg={thinking_msg_id} phase={phase} ok={ok} "
            f"body_len={len(final_body)} thought_chars={len(thought_for_final)} "
            f"stopReason={terminal.stop_reason or '-'} "
            f"thought_updates={thought_updates} room={room_name} "
            f"retry={is_empty_reply_retry}"
        )
        if auth_err_msg:
            post_as_grok(rid, f"🚨 **Authentication Error**: {auth_err_msg}. Stopping.")
            log(f"finalize failed — posted auth error bubble room={room_name}")
        elif not ok:
            # Last resort: new post so the principal is never left with thoughts-only.
            post_as_grok(
                rid,
                compose_final_with_thoughts(final_body, thought_for_final),
            )
            log(f"finalize failed — posted fallback bubble room={room_name}")
    elif reply_body:
        # No placeholder id — last resort new message (should be rare).
        post_as_grok(rid, compose_unified_reply(reply_body))
    elif final_body:
        post_as_grok(rid, final_body)

    # Drop bubble map entry after terminal finalize (success or hard fail).
    if mid:
        try:
            st_c = load_state()
            bubbles = dict(st_c.get("activity_bubbles") or {})
            bubbles.pop(str(mid), None)
            st_c["activity_bubbles"] = bubbles
            save_state(st_c)
        except Exception:
            pass

    if is_collab:
        try:
            st4 = load_state()
            record_collab_hop(
                st4,
                rid,
                author=str(author),
                target=COLLAB_GROK,
                hop_at=datetime.now(timezone.utc).isoformat(),
            )
            save_state(st4)
        except Exception as e:
            log(f"collab hop record failed: {e}")

    # Multi-round collab: lead DONE tracking + peer return-notify (assigner else grok).
    try:
        _maybe_multi_round_after_wake(
            rid=rid,
            room_name=room_name or "",
            room_type=room_type,
            mid=str(mid) if mid else None,
            author=str(author or ""),
            trigger_text=str(caption or ""),
            reply_body=str(reply_body or final_body or ""),
            phase=phase,
            rc=rc,
        )
    except Exception as e:
        log(f"multi-round after-wake failed mid={mid}: {e}")

    # feynman: post-wake claim ledger extract (only on successful final body).
    if phase == PHASE_FINAL_OK:
        try:
            _feynman_ledger_ingest_reply(
                reply_body=str(reply_body or final_body or ""),
                project_cwd=str(project_cwd or ""),
                room_id=str(rid or ""),
                room_name=str(room_name or ""),
                mid=str(mid) if mid else None,
                reply_path=str(reply_path) if reply_path else "",
            )
        except Exception as e:
            log(f"feynman ledger after-wake failed mid={mid}: {e}")

    _mark_processed(
        mid,
        rid,
        ts if isinstance(ts, str) else None,
        rc=rc,
        grok_session_id=sid,
        project_cwd=project_cwd,
    )
    if rc != 0:
        log(f"deep wake failed rc={rc} room={room_name} mid={mid}")


def _maybe_multi_round_after_wake(
    *,
    rid: str,
    room_name: str,
    room_type: str | None,
    mid: str | None,
    author: str,
    trigger_text: str,
    reply_body: str,
    phase: str,
    rc: int,
) -> None:
    """
    After a normal LLM wake finalizes:

    - If this process is lead (grok) and reply declares plain-language DONE → mark room.
    - If this process is a peer and return-notify is allowed → post @assigner|@grok
      so the next hop runs without principal re-tagging (cross-process via tag-to-talk).
    """
    if not multi_round_enabled():
        return
    if not rid:
        return
    op = (OPERATOR or "").strip().lower() or "grok"
    # Lead DONE (plain language) — suppress future automatic return-notify in this room.
    if op == MR_GROK_LEAD and reply_declares_lead_done(reply_body):
        mark_lead_done(
            rid,
            at=datetime.now(timezone.utc).isoformat(),
            mid=mid,
        )
        log(f"multi-round lead DONE marked room={room_name or rid} mid={mid}")
        return

    # Lead kickoff: open a collab epoch when the lead assigns ≥1 peer with @tags.
    if op == MR_GROK_LEAD and not message_is_collab_return(trigger_text):
        peers = extract_peer_assignees_from_text(reply_body)
        if peers:
            try:
                ep = open_collab_epoch(
                    rid,
                    assignees=peers,
                    opened_by=op,
                    mid=mid,
                )
                log(
                    f"multi-round epoch opened epoch={ep} assignees={peers} "
                    f"room={room_name or rid} mid={mid}"
                )
            except Exception as e:
                log(f"multi-round open epoch failed mid={mid}: {e}")

    lead_done = room_lead_done(rid)
    if not should_emit_return_notify(
        operator=op,
        assigner=author,
        room_type=room_type,
        lead_done=lead_done,
        reply_body=reply_body,
        trigger_text=trigger_text,
        phase=phase,
        rc=rc,
        room_id=rid,
    ):
        if lead_done:
            log(
                f"multi-round return-notify suppressed lead_done=1 "
                f"room={room_name or rid} mid={mid} op={op}"
            )
        elif phase == PHASE_FINAL_ERR or (rc is not None and int(rc) != 0):
            log(
                f"multi-round return-notify suppressed quality_gate "
                f"phase={phase} rc={rc} room={room_name or rid} mid={mid} op={op}"
            )
        else:
            # Intentional handoff already in reply, solo principal hop, etc.
            log(
                f"multi-round return-notify suppressed (handoff_already_or_gate) "
                f"room={room_name or rid} mid={mid} op={op} assigner={author} "
                f"phase={phase}"
            )
        return

    # Peer delivery bookkeeping for the active epoch (assignee dedupe / observability).
    try:
        record_assignee_delivered(rid, op, mid=mid)
    except Exception as e:
        log(f"multi-round record delivered failed mid={mid}: {e}")

    target = resolve_return_notify_target(
        author, lead=MR_GROK_LEAD, completing_operator=op
    )
    ep = None
    try:
        ep = room_epoch(rid)
    except Exception:
        ep = None
    text = build_return_notify_text(
        target=target,
        completing_operator=op,
        source_mid=mid,
        room_name=room_name,
        summary=summary_from_reply(reply_body),
        epoch=ep,
    )
    # Post as this process's operator identity (identity="grok" maps to local operator
    # secrets for hermes/agy/claude/grok; "agy" dual-peer path is intentionally avoided).
    posted = post_message_get_id(rid, text, identity=COLLAB_GROK)
    log(
        f"multi-round return-notify target=@{target} from={op} mid={mid} "
        f"room={room_name or rid} posted={bool(posted)} "
        f"marker={COLLAB_RETURN_MARKER} epoch={ep or '-'}"
    )


def _drain_pending_wakes() -> None:
    """
    Drain queued wakes with **per-room serial, cross-room parallel** policy.

    Usability contracts:
    - Never mark processed before a wake attempt (no silent drops).
    - Same room: FIFO — only one wake at a time per rid (per-room lock).
    - Different rooms: process immediately in parallel (up to
      RC_WAKE_MAX_CONCURRENT, default 16) — a long Agency wake must not block DM.
    - Busy head-of-queue room is skipped so later free-room items are not stuck.
    - Workers re-invoke drain on finish so same-room backlog continues.
    - Force-clear only when a chosen room's lock cannot be acquired (stuck);
      not when the room is legitimately busy.
    """
    if not _drain_lock.acquire(blocking=False):
        # Another drain scheduler is active; workers re-check pending on exit.
        return
    started: list[threading.Thread] = []
    try:
        # Fill free room slots; do not block this scheduler on wake runtime.
        for _ in range(64):  # hard cap starts per drain call
            state = load_state()
            pending = list(state.get("pending_wakes") or [])
            if not pending:
                break

            # Prefer try-acquire order: walk pending, first free room wins.
            # Busy rooms fail acquire (live lock or global cap) and are skipped.
            chosen = None
            chosen_i: int | None = None
            chosen_rid = ""
            for i, item in enumerate(pending):
                if not isinstance(item, dict):
                    continue
                rid = str(item.get("rid") or "")
                if acquire_wake_lock(rid):
                    chosen = item
                    chosen_i = i
                    chosen_rid = rid
                    break
            if chosen is None or chosen_i is None:
                # All pending rooms busy or global concurrent cap full.
                break

            pending.pop(chosen_i)
            state["pending_wakes"] = pending
            save_state(state)

            def _work(it: dict = chosen, rid: str = chosen_rid) -> None:
                try:
                    try:
                        _process_pending_item(it)
                    except Exception as e:
                        log(
                            f"process item failed mid={it.get('mid')} "
                            f"room={it.get('room_name')}: {e}"
                        )
                        try:
                            mid_f = str(it.get("mid") or "")
                            rid_f = str(it.get("rid") or "")
                            bubble = None
                            if mid_f:
                                bubble = (load_state().get("activity_bubbles") or {}).get(
                                    mid_f
                                )
                            err_txt = (
                                f"**Wake failed (operator error)**\n\n"
                                f"`{type(e).__name__}: {e}`\n\n"
                                f"Check operator-agent.log under LOG_DIR."
                            )
                            if rid_f and bubble:
                                finalize_thinking_message(
                                    rid_f,
                                    str(bubble),
                                    err_txt,
                                    identity=COLLAB_GROK,
                                    thought_text="",
                                )
                            elif rid_f:
                                post_as_grok(rid_f, err_txt)
                        except Exception as fe:
                            log(f"failed to surface process error to room: {fe}")
                        if it.get("mid"):
                            _set_in_flight(str(it.get("mid")), active=False)
                finally:
                    release_wake_lock(rid)
                    # Continue same-room backlog / other rooms (async path only).
                    # Sync tests join workers then recurse drain themselves.
                    if (os.environ.get("RC_WAKE_DRAIN_SYNC") or "").strip().lower() not in (
                        "1",
                        "true",
                        "yes",
                        "on",
                    ):
                        threading.Thread(
                            target=_drain_pending_wakes,
                            name="rc-drain-wakes",
                            daemon=True,
                        ).start()

            t = threading.Thread(
                target=_work,
                name=f"rc-wake-{(chosen.get('mid') or '')[:10]}",
                daemon=True,
            )
            t.start()
            started.append(t)
            log(
                f"drain started room={chosen.get('room_name') or chosen_rid} "
                f"mid={chosen.get('mid')} concurrent_workers~={len(started)}"
            )
    finally:
        _drain_lock.release()

    # Tests set RC_WAKE_DRAIN_SYNC=1 for deterministic joins.
    sync = (os.environ.get("RC_WAKE_DRAIN_SYNC") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if sync:
        for t in started:
            t.join(timeout=180)
        # Nested drain may have started more workers under sync; one more pass.
        if load_state().get("pending_wakes"):
            # Direct recursive sync drain without holding outer join races.
            _drain_pending_wakes()


def _call_bot_busy() -> bool:
    """
    True if a live call media worker holds the lock.

    Stale locks (dead PID or aged out) are cleared so a hung bot cannot
    permanently block Call. Uses NF-SPEC-01 helpers when available.
    """
    if _HAS_CALL_MEDIA:
        clear_stale_call_lock(CALL_LOCK, busy_s=MAX_CALL_BUSY_S)
        return call_lock_is_busy(CALL_LOCK, busy_s=MAX_CALL_BUSY_S)
    try:
        if not CALL_LOCK.is_file():
            return False
        age = time.time() - CALL_LOCK.stat().st_mtime
        meta: dict = {}
        try:
            meta = json.loads(CALL_LOCK.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        pid = meta.get("pid")
        alive = False
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False
        if alive and age < MAX_CALL_BUSY_S:
            return True
        try:
            CALL_LOCK.unlink(missing_ok=True)
            log(f"cleared stale call-bot lock pid={pid} age={age:.0f}s alive={alive}")
        except OSError:
            pass
        return False
    except OSError:
        return False


def _ensure_jitsi_lan_before_call() -> None:
    """Refresh Jitsi domain to current LAN:8090 so phone join URLs are reachable."""
    try:
        call_dir = str(AGENCY / "ops" / "rocketchat" / "call")
        if call_dir not in sys.path:
            sys.path.insert(0, call_dir)
        from ensure_jitsi_lan import ensure_jitsi_domain_matches_lan  # type: ignore

        r = ensure_jitsi_domain_matches_lan(base=BASE_HTTP, env=os.environ)
        log(
            f"jitsi lan ensure ok={r.get('ok')} domain={r.get('domain')} "
            f"ssl={r.get('ssl')} changed={r.get('changed')} reason={r.get('reason')}"
        )
    except Exception as e:
        log(f"jitsi lan ensure skipped/err: {e}")


def spawn_call_bot(call_id: str, room_id: str, room_name: str = "") -> bool:
    """
    Start call media worker for principal Call (NF-SPEC-01).

    **No-op when call_integration_enabled() is false** (default; voice retired).

    Backend from RC_CALL_MEDIA_BACKEND (only if enabled):
      - livekit → voice_agent_worker.py (Grok Voice Agent / Realtime primary)
      - playwright → rc_call_bot.py (Path C lab only)

    Single-flight lock per concurrent call (FR-V7).
    A *new* callId supersedes any prior lock holder so Call never sticks on
    false busy after a hung previous worker.
    """
    if not call_id:
        return False
    if _HAS_CALL_MEDIA:
        try:
            from rc_call_media import call_integration_enabled as _cie  # type: ignore

            if not _cie():
                log("spawn_call_bot refused — RC_CALL_ENABLED off (voice retired)")
                return False
        except Exception:
            log("spawn_call_bot refused — call_integration_enabled unavailable")
            return False
    # Supersede prior media when principal starts a different Call.
    if _HAS_CALL_MEDIA and _call_bot_busy():
        meta = read_call_lock(CALL_LOCK)
        try:
            supersede = should_supersede_lock_for_new_call(meta, call_id)
        except NameError:
            supersede = bool(meta and getattr(meta, "call_id", None) != call_id)
        if supersede:
            log(
                f"call media supersede prior callId={getattr(meta, 'call_id', None)} "
                f"for new callId={call_id}"
            )
            hangup_call_media(
                call_id=getattr(meta, "call_id", None) or None,
                room_id=room_id,
                post_status=False,
                detail="superseded by new Call",
            )
        elif meta and meta.call_id == call_id:
            log(f"call media busy same callId={call_id} — skip duplicate spawn")
            return False
    if _call_bot_busy():
        log("call media busy — skip second concurrent call")
        return False
    _ensure_jitsi_lan_before_call()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    py = resolve_operator_python_bin()
    backend = "playwright"
    cmd: list[str]
    if _HAS_CALL_MEDIA:
        backend, cmd, _plan = select_spawn_plan(
            call_id=call_id,
            room_id=room_id,
            room_name=room_name or "",
            python_bin=py,
            env=os.environ,
            agency=AGENCY,
        )
    else:
        cmd = [
            py,
            str(CALL_BOT),
            "--call-id",
            call_id,
            "--room-id",
            room_id,
            "--room-name",
            room_name or "",
        ]

    # Worker script must exist for the selected backend
    if backend == "livekit" or (len(cmd) > 1 and "voice_agent" in str(cmd[1])):
        if not VOICE_AGENT.is_file() and not Path(cmd[1]).is_file():
            log(f"voice agent missing: {VOICE_AGENT}")
            return False
    else:
        if not CALL_BOT.is_file() and not Path(cmd[1]).is_file():
            log(f"call bot missing: {CALL_BOT}")
            return False

    started_at = datetime.now(timezone.utc).isoformat()
    if _HAS_CALL_MEDIA:
        ok_lock = acquire_call_lock(
            CALL_LOCK,
            call_id=call_id,
            room_id=room_id,
            backend=backend,
            pid=None,
            started_at=started_at,
            busy_s=MAX_CALL_BUSY_S,
        )
        if not ok_lock:
            log(f"call lock acquire failed callId={call_id} backend={backend}")
            return False
    else:
        try:
            CALL_LOCK.write_text(
                json.dumps(
                    {
                        "call_id": call_id,
                        "room_id": room_id,
                        "backend": backend,
                        "started_at": started_at,
                        "pid": None,
                    }
                ),
                encoding="utf-8",
            )
        except OSError as e:
            log(f"call lock write failed: {e}")

    env = os.environ.copy()
    env["PATH"] = (
        f"/Library/Frameworks/Python.framework/Versions/3.13/bin:"
        f"{Path.home() / '.local' / 'bin'}:/opt/homebrew/bin:/usr/local/bin:"
        f"/usr/bin:/bin:{env.get('PATH', '')}"
    )
    env["RC_BASE"] = BASE_HTTP
    env["RC_CALL_MEDIA_BACKEND"] = backend
    log_path = LOG_DIR / (
        "voice-agent.spawn.log" if backend == "livekit" else "call-bot.spawn.log"
    )
    try:
        with log_path.open("a", encoding="utf-8") as out:
            out.write(
                f"\n--- spawn {datetime.now(timezone.utc).isoformat()} "
                f"backend={backend} {cmd}\n"
            )
            out.flush()
            proc = subprocess.Popen(
                cmd,
                stdout=out,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(AGENCY),
                start_new_session=True,
            )
        if _HAS_CALL_MEDIA:
            update_call_lock_pid(CALL_LOCK, int(proc.pid))
        else:
            try:
                meta = json.loads(CALL_LOCK.read_text(encoding="utf-8"))
                meta["pid"] = proc.pid
                meta["backend"] = backend
                CALL_LOCK.write_text(json.dumps(meta), encoding="utf-8")
            except OSError:
                pass
        log(
            f"call media spawned backend={backend} pid={proc.pid} callId={call_id} "
            f"cmd0={cmd[0]} script={Path(cmd[1]).name if len(cmd) > 1 else '?'}"
        )
        return True
    except Exception as e:
        log(f"call media spawn failed backend={backend}: {e}")
        if _HAS_CALL_MEDIA:
            release_call_lock(CALL_LOCK, call_id=call_id, only_if_call_id=True)
        else:
            try:
                CALL_LOCK.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def hangup_call_media(
    *,
    call_id: str | None = None,
    room_id: str = "",
    post_status: bool = True,
    detail: str = "",
) -> dict:
    """
    FR-V6: terminate media worker (SIGTERM) and release call lock.

    Used on hangup system messages / explicit cleanup. Returns terminate result.
    """
    if not _HAS_CALL_MEDIA:
        try:
            if CALL_LOCK.is_file():
                meta = json.loads(CALL_LOCK.read_text(encoding="utf-8"))
                pid = meta.get("pid")
                if isinstance(pid, int) and pid > 0:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except OSError:
                        pass
                CALL_LOCK.unlink(missing_ok=True)
            return {"ok": True, "lock_released": True, "reason": "legacy"}
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    result = terminate_call_worker(CALL_LOCK, call_id=call_id or None)
    log(
        f"hangup_call_media callId={call_id or result.get('call_id')} "
        f"signalled={result.get('signalled')} released={result.get('lock_released')} "
        f"pid={result.get('pid')}"
    )
    if post_status and room_id:
        post_as_grok(
            room_id,
            format_call_status_message(
                STATUS_ENDED,
                call_id=str(call_id or result.get("call_id") or ""),
                detail=detail or "worker stopped",
            ),
        )
    return result


def handle_videoconf_call(
    msg: dict,
    room_id: str,
    room_name: str = "",
) -> None:
    """
    Principal pressed Call → spawn media worker (LiveKit voice agent or lab Playwright).

    Hangup/end messages → SIGTERM worker + release lock + sparse **ended** status.
    Sparse DM status only (connecting / failed / ended) — no per-turn transcript flood.
    Marks the system message processed so we do not double-spawn.

    **Retired default:** when call integration is off (RC_CALL_ENABLED unset/0),
    mark processed and return — no media spawn (principal roadmap: no voice).
    """
    rid = msg.get("rid") or room_id
    mid = msg.get("_id")
    if not mid:
        return
    state = load_state()
    processed = list(state.get("processed_ids") or [])
    if mid in processed:
        return
    user = (msg.get("u") or {}).get("username")
    if user != PRINCIPAL:
        return

    # Master kill switch — voice/Call integration retired (2026-07-17).
    call_on = False
    if _HAS_CALL_MEDIA:
        try:
            from rc_call_media import call_integration_enabled as _cie  # type: ignore

            call_on = bool(_cie())
        except Exception:
            call_on = False
    if not call_on:
        log(
            f"videoconf ignored room={room_name or rid} mid={mid} — "
            f"Call/voice integration disabled (RC_CALL_ENABLED off / retired)"
        )
        _mark_processed(
            mid,
            rid,
            msg.get("ts") if isinstance(msg.get("ts"), str) else None,
            rc=0,
        )
        return

    # Hangup / call-end path (FR-V6)
    if _HAS_CALL_MEDIA and is_videoconf_end_message(msg):
        cid = videoconf_call_id(msg) or ""
        meta = read_call_lock(CALL_LOCK)
        # Prefer lock's call_id when message lacks one or mismatches (single-flight)
        if meta and (not cid or cid == meta.call_id or not videoconf_call_id(msg)):
            cid = meta.call_id
        elif meta and cid and cid != meta.call_id:
            # Still end the only active call for this operator (one concurrent call)
            cid = meta.call_id
        log(
            f"videoconf end from principal room={room_name or rid} "
            f"mid={mid} callId={cid or 'n/a'} — hangup media"
        )
        hangup_call_media(call_id=cid or None, room_id=rid, post_status=True)
        _mark_processed(
            mid,
            rid,
            msg.get("ts") if isinstance(msg.get("ts"), str) else None,
            rc=0,
        )
        return

    call_id = videoconf_call_id(msg) or ""
    backend = call_media_backend() if _HAS_CALL_MEDIA else "playwright"
    log(
        f"videoconf call from principal room={room_name or rid} "
        f"mid={mid} callId={call_id or 'n/a'} backend={backend} — spawning media"
    )

    started = bool(call_id) and spawn_call_bot(call_id, rid, room_name=room_name)
    if started:
        if _HAS_CALL_MEDIA:
            status = format_call_status_message(
                STATUS_CONNECTING,
                call_id=call_id,
                greeting=voice_greeting(),
            )
        else:
            status = (
                "Answering your call now — you should hear: "
                '"Hello, Grok speaking." Speak after the greeting.'
            )
        post_as_grok(rid, status)
    else:
        if _HAS_CALL_MEDIA:
            post_as_grok(
                rid,
                format_call_status_message(
                    STATUS_FAILED,
                    call_id=call_id,
                    detail="could not start media worker (busy or missing backend)",
                ),
            )
        else:
            post_as_grok(rid, CALL_NO_MEDIA_REPLY)

    _mark_processed(
        mid,
        rid,
        msg.get("ts") if isinstance(msg.get("ts"), str) else None,
        rc=0 if started else 1,
    )


def handle_principal_message(
    msg: dict,
    room_id: str,
    room_name: str = "",
    room_type: str | None = None,
) -> None:
    """
    Room message intake (principal free-wake in DMs; anyone @operator elsewhere).

    Non-collab:
    - Principal: DMs free-wake; with RC_REQUIRE_MENTION=1 (scope channels by default),
      channel/group LLM wakes require @operator. Control-plane !/ commands stay
      mention-exempt for principal only.
    - Anyone else (peer bots, other humans): RC_PEER_TAG_WAKE (default on) +
      explicit @operator. Self-posts never wake (loop prevention).

    Collab rooms (RC_AGY_COLLAB + mode=agy-collab): tag-to-talk for allowlisted
    authors {principal, grok, agy}; routes to Grok CLI or local agy CLI.
    """
    rid = msg.get("rid") or room_id
    state = load_state()
    processed = list(state.get("processed_ids") or [])
    mid = msg.get("_id")
    user = ((msg.get("u") or {}).get("username") or "").strip()
    text = (msg.get("msg") or "").strip()

    # Call button → videoconf system message (empty text; not a normal wake).
    if is_videoconf_message(msg):
        if mid and mid not in processed and user == PRINCIPAL:
            handle_videoconf_call(msg, rid, room_name=room_name)
        return

    armed = collab_armed_for_room(room_name or "", room_type=room_type)
    if not armed:
        # Never process own posts; drop empties / already-handled early.
        if not mid or user.lower() == (OPERATOR or "").strip().lower():
            return
        if mid in processed:
            return
        if not message_has_handleable_content(msg):
            return

        is_principal = user == PRINCIPAL

        # --- NF-SPEC-03 control plane interceptor (before Thinking… enqueue) ---
        # Principal only; mention gate runs after so !status / !cancel stay tag-exempt.
        if is_principal and control_plane_enabled() and mid not in processed:
            handled = _try_control_plane(
                msg, rid, room_name=room_name, room_type=room_type, text=text
            )
            if handled:
                return

        # Full wake gate: principal free-wake rules + peer @operator tags.
        if not should_enqueue_llm_wake(
            msg,
            operator=OPERATOR,
            principal=PRINCIPAL,
            processed_ids=processed,
            room_type=room_type,
            text=text,
        ):
            if is_principal and room_requires_operator_mention(room_type):
                log(
                    f"skip no_operator_mention operator={OPERATOR} "
                    f"room={room_name or rid} mid={mid} room_type={room_type or '?'}"
                )
            return

        # Issue #2 P0: principal multi-@ of lead+peers → only lead enqueues.
        # Peers wait for an explicit lead assign (new mid). Direct principal→@peer
        # (lead not mentioned) still wakes that peer.
        if multi_round_enabled() and mid and principal_multi_mention_lead_only(
            author=user,
            operator=OPERATOR,
            text=text,
            room_type=room_type,
            msg=msg,
        ):
            log(
                f"multi-round skip peer enqueue principal multi-@ lead-only "
                f"op={OPERATOR} room={room_name or rid} mid={mid} author={user}"
            )
            _mark_processed(
                mid,
                rid,
                msg.get("ts") if isinstance(msg.get("ts"), str) else None,
                rc=0,
            )
            return

        # Close-out loop: after lead DONE, collab-return / peer stand-by must not
        # spawn another lead LLM (Prime-Gap-Structure residual-cell thrash).
        if multi_round_enabled() and mid:
            try:
                _ld = room_lead_done(str(rid))
                if should_skip_lead_llm_on_collab_return(
                    operator=OPERATOR,
                    trigger_text=text,
                    lead_done=_ld,
                ) or should_skip_lead_llm_on_peer_closeout_ack(
                    operator=OPERATOR,
                    author=user,
                    trigger_text=text,
                    lead_done=_ld,
                ):
                    log(
                        f"multi-round skip lead wake after DONE "
                        f"room={room_name or rid} mid={mid} op={OPERATOR} "
                        f"author={user} collab_return="
                        f"{message_is_collab_return(text)}"
                    )
                    _mark_processed(
                        mid,
                        rid,
                        msg.get("ts") if isinstance(msg.get("ts"), str) else None,
                        rc=0,
                    )
                    return
            except Exception as e:
                log(f"multi-round lead skip-after-DONE check failed: {e}")

        # Principal opening new work may clear lead DONE (lead incidental @tags never clear).
        if multi_round_enabled() and mid and not message_is_collab_return(text):
            try:
                if maybe_clear_lead_done_on_new_work(
                    room_id=str(rid),
                    author=user,
                    operator=OPERATOR,
                    trigger_text=text,
                ):
                    log(
                        f"multi-round lead_done cleared on new work "
                        f"author={user} room={room_name or rid} mid={mid}"
                    )
            except Exception as e:
                log(f"multi-round clear lead_done failed: {e}")

        n_audio = len(extract_audio_file_candidates(msg))
        n_image = len(extract_image_file_candidates(msg))
        n_docs = len(extract_document_file_candidates(msg))
        n_files = len(extract_file_candidates(msg))
        resume_id = get_room_session_id(state, rid)
        pinned_cwd = get_room_cwd(state, rid)
        if text:
            preview = text[:120]
        elif n_image:
            preview = f"(attachment image={n_image})"
        elif n_docs:
            preview = f"(attachment docs={n_docs})"
        elif n_audio:
            preview = f"(attachment audio={n_audio})"
        elif n_files:
            preview = f"(attachment files={n_files})"
        else:
            preview = "(empty)"
        log(
            f"room msg author={user} in {room_name or rid}: {preview} "
            f"(session={resume_id or 'NEW'} cwd={pinned_cwd or 'resolve'} "
            f"audio={n_audio} image={n_image} docs={n_docs})"
        )

        if not _enqueue_pending(msg, rid, room_name, room_type, target="grok", collab=False):
            _log_enqueue_skip(mid)
            return

        threading.Thread(
            target=_drain_pending_wakes, name="rc-drain-wakes", daemon=True
        ).start()
        log(
            f"wake enqueued author={user} resume={resume_id or 'NEW'} "
            f"room={room_name or rid} mid={mid}"
        )
        return

    # --- NF-SPEC-04 collab-armed room ---
    if mid and mid in processed:
        return
    allow = {COLLAB_PRINCIPAL, COLLAB_GROK, COLLAB_AGY}
    if user.lower() not in allow:
        return

    # Principal slash commands still work in collab rooms.
    if user.lower() == COLLAB_PRINCIPAL and control_plane_enabled() and mid:
        cmd_text = strip_leading_mentions(text)
        if cmd_text.startswith("/") or cmd_text.startswith("!"):
            handled = _try_control_plane(
                msg, rid, room_name=room_name, room_type=room_type, text=text
            )
            if handled:
                return
        # Pending elevation yes/no
        conf = is_confirm_reply(text)
        if conf:
            handled = _try_control_plane(
                msg, rid, room_name=room_name, room_type=room_type, text=text
            )
            if handled:
                return

    targets = resolve_mention_targets(msg, text=text)
    collab = ensure_collab_budget(state, rid)
    # Room profile may override hop budget
    prof = lookup_room_profile(room_name or "")
    if prof:
        collab["hop_budget_epoch"] = profile_hop_budget(prof)
        set_collab_room_state(state, rid, collab)
        save_state(state)
        collab = get_collab_room_state(state, rid)

    decision = classify_collab_message(
        author=user,
        targets=targets,
        collab_armed=True,
        auto_handoff=bool(collab.get("auto_handoff", True)),
        paused_reason=collab.get("paused_reason"),
        hop_count_epoch=int(collab.get("hop_count_epoch") or 0),
        hop_budget_epoch=int(collab.get("hop_budget_epoch") or 100),
    )
    log(
        f"{decision.log_line} room={room_name or rid} mid={mid} "
        f"targets={sorted(targets)}"
    )

    if decision.action == "ignore":
        return

    if decision.action in ("reject", "notify_budget"):
        if decision.action == "notify_budget":
            pause_auto_handoff(state, rid, "budget")
            save_state(state)
        if decision.reply:
            post_as_grok(rid, decision.reply)
        if mid:
            _mark_processed(
                mid,
                rid,
                msg.get("ts") if isinstance(msg.get("ts"), str) else None,
                rc=0,
            )
        return

    # action == wake
    target = decision.target or COLLAB_GROK
    resume_id = get_room_session_id(state, rid)
    if not _enqueue_pending(
        msg, rid, room_name, room_type, target=target, collab=True
    ):
        _log_enqueue_skip(mid, context=f"collab target={target}")
        return
    threading.Thread(
        target=_drain_pending_wakes, name="rc-drain-wakes", daemon=True
    ).start()
    log(
        f"collab wake enqueued target={target} author={user} "
        f"resume={resume_id or 'NEW'} room={room_name or rid} mid={mid}"
    )


def _try_control_plane(
    msg: dict,
    rid: str,
    *,
    room_name: str,
    room_type: str | None,
    text: str,
) -> bool:
    """
    Handle slash commands / elevation confirm. Returns True if message was
    fully handled (no default research wake).
    """
    mid = msg.get("_id")
    state = load_state()
    clear_expired_pending(state, rid)
    save_state(state)
    state = load_state()

    # Pending yes/no (even without slash)
    conf = is_confirm_reply(text)
    if conf and get_pending_confirm(state, rid):
        if conf == "yes":
            state, reply = confirm_yes(state, rid, ttl_s=admin_ttl_s())
        else:
            state, reply = confirm_no(state, rid)
        save_state(state)
        post_as_grok(rid, reply)
        _mark_processed(
            mid,
            rid,
            msg.get("ts") if isinstance(msg.get("ts"), str) else None,
            rc=0,
            clear_session=False,
        )
        log(f"control-plane confirm={conf} room={room_name} mid={mid}")
        return True

    parsed = parse_command(text)
    if not parsed:
        return False

    rtype_for_mode = room_type
    if not rtype_for_mode and (room_name or "").lower().startswith("dm"):
        rtype_for_mode = "d"
    base_mode = resolve_approval_mode(
        room_type=rtype_for_mode, room_name=room_name or ""
    )
    project_cwd, reason = _resolve_room_cwd_info(rid, room_name, room_type, state)
    sid = get_room_session_id(state, rid)

    result = dispatch_command(
        parsed,
        state=state,
        room_id=rid,
        room_name=room_name,
        room_type=room_type,
        health_reader=_health_summary_line,
        base_approval=base_mode,
        session_id=sid,
        cwd=project_cwd,
        cwd_reason=reason,
    )
    save_state(state)
    log(f"control-plane {result.log_line} room={room_name} mid={mid}")

    if result.cancel_pid is not None:
        cancel_msg = _try_cancel_wake_pid(result.cancel_pid, rid)
        post_as_grok(rid, f"{result.reply}\n{cancel_msg}")
        if result.mark_processed:
            _mark_processed(
                mid,
                rid,
                msg.get("ts") if isinstance(msg.get("ts"), str) else None,
                rc=0,
            )
        return True

    if result.wake_text:
        # Explicit wake / retry / ask — enqueue content path with substituted text
        wake_msg = dict(msg)
        wake_msg["msg"] = result.wake_text
        if result.reply:
            post_as_grok(rid, result.reply)
        if result.mark_processed:
            # Mark the command mid processed; new synthetic enqueue needs a new mid
            # so we re-use command mid only for drain of substituted text:
            # replace text on same mid before enqueue.
            pass
        # Enqueue original mid with replaced text (not double-processed yet)
        # Un-mark if we marked — do not mark before drain for wake commands.
        if not _enqueue_pending(wake_msg, rid, room_name, room_type):
            # If already pending, still ok
            _log_enqueue_skip(mid, context="control-plane")
        else:
            threading.Thread(
                target=_drain_pending_wakes, name="rc-drain-wakes", daemon=True
            ).start()
        return True

    # Pure command: reply only, no Grok CLI research wake
    post_as_grok(rid, result.reply)
    if result.mark_processed and mid:
        _mark_processed(
            mid,
            rid,
            msg.get("ts") if isinstance(msg.get("ts"), str) else None,
            rc=0,
        )
    return True


class OperatorAgent:
    def __init__(self) -> None:
        self.ws: websocket.WebSocketApp | None = None
        self.token = ""
        self.uid = ""
        self.room_id = ""  # primary DM room (backward compatible)
        self.watch_rooms: list[dict] = []  # [{_id, name, t}, ...]
        self._room_names: dict[str, str] = {}
        self._room_types: dict[str, str] = {}  # rid → c|p|d
        self._id = 0
        self._stop = False
        self._connected = threading.Event()
        self._last_room_refresh = 0.0
        self._sub_seq = 0

    def next_id(self) -> str:
        self._id += 1
        return str(self._id)

    def send(self, obj: dict) -> None:
        assert self.ws is not None
        self.ws.send(json.dumps(obj))

    def _ddp_subscribe_room(self, room: dict) -> None:
        """Subscribe stream-room-messages for one room (idempotent at RC layer)."""
        rid = room.get("_id") or ""
        if not rid:
            return
        rname = room.get("name") or rid
        self._room_names[rid] = rname
        if room.get("t"):
            self._room_types[rid] = str(room.get("t"))
        self._sub_seq += 1
        self.send(
            {
                "msg": "sub",
                "id": f"sub-room-{self._sub_seq}-{rid[:8]}",
                "name": "stream-room-messages",
                "params": [rid, False],
            }
        )
        log(f"subscribed stream-room-messages room={rname} ({rid})")

    def _history_path(self, room: dict) -> str:
        rid = room.get("_id") or ""
        t = str(room.get("t") or "p")
        n = CATCHUP_HISTORY
        if t == "d":
            return f"/api/v1/im.history?roomId={rid}&count={n}"
        if t == "c":
            return f"/api/v1/channels.history?roomId={rid}&count={n}"
        return f"/api/v1/groups.history?roomId={rid}&count={n}"

    def catch_up_room(self, room: dict) -> int:
        """
        Process recent unhandled principal messages in a room (e.g. created while
        operator was already running). Returns how many messages were enqueued.
        """
        rid = room.get("_id") or ""
        rname = room.get("name") or rid
        rtype = room.get("t")
        if not rid or not self.token:
            return 0
        try:
            hist = http_api("GET", self._history_path(room), self.token, self.uid)
        except Exception as e:
            log(f"catch-up history failed room={rname}: {e}")
            return 0
        # API returns newest first → oldest first for natural order
        msgs = list(reversed(hist.get("messages") or []))
        n = 0
        for m in msgs:
            if not isinstance(m, dict):
                continue
            mid = m.get("_id")
            before = list(load_state().get("processed_ids") or [])
            pending = {
                (p.get("mid") if isinstance(p, dict) else None)
                for p in (load_state().get("pending_wakes") or [])
            }
            if mid and (mid in before or mid in pending):
                continue
            user = ((m.get("u") or {}).get("username") or "").strip()
            # Self-skip; collab-armed keep allowlist; non-collab defer to
            # handle_principal_message (principal free-wake + peer @tags).
            if user.lower() == (OPERATOR or "").strip().lower():
                continue
            if collab_armed_for_room(rname or "", room_type=rtype):
                if user.lower() not in {COLLAB_PRINCIPAL, COLLAB_GROK, COLLAB_AGY}:
                    continue
            handle_principal_message(m, rid, room_name=rname, room_type=rtype)
            n += 1
        if n:
            log(f"catch-up room={rname} enqueued={n}")
        return n

    def refresh_watch_rooms(self, *, catch_up_new: bool = True) -> list[dict]:
        """
        Re-list joined rooms; subscribe any not yet watched.

        Fixes: principal creates a channel and invites grok while operator is up
        — without this, messages in the new room are never seen until restart.
        """
        if not self.token or not self._connected.is_set() or not self.ws:
            return []
        try:
            rooms = list_watch_rooms(self.token, self.uid)
        except Exception as e:
            log(f"refresh_watch_rooms list failed: {e}")
            return []
        known = set(self._room_names)
        added: list[dict] = []
        for room in rooms:
            rid = room.get("_id")
            if not rid or rid in known:
                # Keep name/type fresh
                if rid and rid in self._room_names:
                    self._room_names[rid] = room.get("name") or self._room_names[rid]
                    if room.get("t"):
                        self._room_types[rid] = str(room.get("t"))
                continue
            self.watch_rooms.append(room)
            try:
                self._ddp_subscribe_room(room)
            except Exception as e:
                log(f"subscribe new room failed {room.get('name')}: {e}")
                continue
            added.append(room)
            if catch_up_new:
                try:
                    self.catch_up_room(room)
                except Exception as e:
                    log(f"catch-up after subscribe failed: {e}")
        if added:
            log(
                "watch rooms updated (+"
                + str(len(added))
                + "): "
                + ", ".join(f"{r.get('name')}({r.get('t')})" for r in rooms)
            )
        self._last_room_refresh = time.time()
        return added

    def on_open(self, ws: websocket.WebSocketApp) -> None:
        log("websocket open — connecting DDP")
        self.send({"msg": "connect", "version": "1", "support": ["1"]})

    def on_message(self, ws: websocket.WebSocketApp, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        msg = data.get("msg")
        if msg == "connected":
            log("DDP connected — logging in")
            self.send({"msg": "method", "method": "login", "id": self.next_id(), "params": [{"resume": self.token}]})
            return
        if msg == "ping":
            self.send({"msg": "pong"})
            return
        if msg == "result":
            # after login, set presence + sub
            rid = data.get("id")
            if data.get("error"):
                log(f"method error id={rid}: {data.get('error')}")
                return
            result = data.get("result")
            if isinstance(result, dict) and result.get("id") == self.uid:
                log("login OK — setting online + subscribe")
                self.send(
                    {
                        "msg": "method",
                        "method": "UserPresence:setDefaultStatus",
                        "id": self.next_id(),
                        "params": ["online"],
                    }
                )
                self.send({"msg": "method", "method": "UserPresence:online", "id": self.next_id(), "params": []})
                # Fresh subscribe set for this connection
                self._room_names.clear()
                self._room_types.clear()
                self._sub_seq = 0
                for room in self.watch_rooms or [{"_id": self.room_id, "name": "dm"}]:
                    try:
                        self._ddp_subscribe_room(room)
                    except Exception as e:
                        log(f"subscribe failed: {e}")
                self._connected.set()
                self._last_room_refresh = time.time()
                # Boot drain: pending_wakes survive restarts but nothing else
                # starts a worker until the next enqueue — fix that hole.
                if load_state().get("pending_wakes"):
                    log(
                        f"boot drain pending={len(load_state().get('pending_wakes') or [])}"
                    )
                    threading.Thread(
                        target=_drain_pending_wakes,
                        name="rc-drain-boot",
                        daemon=True,
                    ).start()
            return
        if msg == "changed" and data.get("collection") == "stream-room-messages":
            fields = data.get("fields") or {}
            args = fields.get("args") or []
            if not args:
                return
            payload = args[0]
            if isinstance(payload, dict):
                rid = payload.get("rid") or self.room_id
                rname = self._room_names.get(rid, rid)
                rtype = self._room_types.get(rid)
                handle_principal_message(payload, rid, room_name=rname, room_type=rtype)

    def on_error(self, ws: websocket.WebSocketApp, error: Exception) -> None:
        log(f"websocket error: {error}")

    def on_close(self, ws: websocket.WebSocketApp, status_code: int | None, msg: str | None) -> None:
        log(f"websocket closed code={status_code} msg={msg}")
        self._connected.clear()

    def ping_loop(self) -> None:
        while not self._stop:
            time.sleep(PING_EVERY_S)
            connected = bool(self.ws and self._connected.is_set())
            try:
                write_health_snapshot(
                    ws_connected=connected,
                    rooms_count=len(self.watch_rooms or []),
                )
            except Exception:
                pass
            if connected:
                try:
                    self.send({"msg": "ping"})
                    self.send(
                        {"msg": "method", "method": "UserPresence:online", "id": self.next_id(), "params": []}
                    )
                    if time.time() - self._last_room_refresh >= ROOM_REFRESH_EVERY_S:
                        self.refresh_watch_rooms(catch_up_new=True)
                except Exception as e:
                    log(f"ping failed: {e}")

    def seed_cursor_if_empty(self) -> dict | None:
        """
        First-run seed without waking Grok (history cursor only).

        Called from run_forever after login + room discovery. Returns saved
        seed state, or None if already seeded / no messages.
        """
        st = load_state()
        if st.get("last_seen_id"):
            return None
        hist = http_api(
            "GET",
            f"/api/v1/im.history?roomId={self.room_id}&count=5",
            self.token,
            self.uid,
        )
        msgs = hist.get("messages") or []
        seeded = seed_state_from_messages(msgs, self.room_id, newest_first=True)
        if seeded:
            save_state(seeded)
            log(f"seeded last_seen_id={seeded.get('last_seen_id')}")
            return seeded
        return None

    def bootstrap_session(self, user: str, password: str) -> dict | None:
        """
        Login + discover watch rooms + first-run seed. Same prefix as run_forever.

        Returns seed state if a seed was written, else None.
        Does not start websocket or wake_grok.
        """
        self.token, self.uid = rest_login(user, password)
        self.watch_rooms = list_watch_rooms(self.token, self.uid)
        self._room_names = {r["_id"]: r.get("name") or r["_id"] for r in self.watch_rooms}
        # DM room for seed / backward compat
        self.room_id = next(
            (r["_id"] for r in self.watch_rooms if r.get("t") == "d"),
            (self.watch_rooms[0]["_id"] if self.watch_rooms else ""),
        )
        if not self.room_id:
            self.room_id = find_dm_room(self.token, self.uid)
        log(
            "watch rooms: "
            + ", ".join(f"{r.get('name')}({r.get('t')})" for r in self.watch_rooms)
        )
        return self.seed_cursor_if_empty()

    def run_forever(self) -> None:
        secrets = load_env(SECRETS)
        user = secrets.get("ROCKETCHAT_OPERATOR_USERNAME", OPERATOR)
        password = secrets["ROCKETCHAT_OPERATOR_PASSWORD"]
        while not self._stop:
            try:
                self.bootstrap_session(user, password)

                log(
                    f"starting agent uid={self.uid} rooms={len(self.watch_rooms)} "
                    f"primary={self.room_id}"
                )
                self.ws = websocket.WebSocketApp(
                    WS_URL,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )
                t = threading.Thread(target=self.ping_loop, daemon=True)
                t.start()
                self.ws.run_forever(ping_interval=0)
            except Exception as e:
                log(f"agent loop error: {e}")
            if self._stop:
                break
            log(f"reconnect in {RECONNECT_S}s")
            time.sleep(RECONNECT_S)


def main() -> int:
    log("operator agent starting")
    # IMP-03: shared config + fail-fast (RC reachable, secrets present)
    check_rc = os.environ.get("RC_SKIP_STARTUP_CHECK", "").strip() not in (
        "1",
        "true",
        "yes",
    )
    apply_runtime_config(check_rc=check_rc)
    # IMP-08: optional prune of aged wake artifacts (never ledger)
    try:
        from wake_lib import prune_log_artifacts

        if os.environ.get("RC_PRUNE_ON_START", "1").strip() not in ("0", "false", "no"):
            age = float(os.environ.get("RC_LOG_MAX_AGE_S", str(7 * 24 * 3600)))
            n = prune_log_artifacts(LOG_DIR, max_age_s=age, dry_run=False)
            if n:
                log(f"pruned {len(n)} aged log artifacts")
    except Exception as e:
        log(f"prune on start skipped: {e}")
    write_health_snapshot(ws_connected=False, rooms_count=0)
    OperatorAgent().run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
