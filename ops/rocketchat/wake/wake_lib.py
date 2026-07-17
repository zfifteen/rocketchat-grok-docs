#!/usr/bin/env python3
"""
Shared pure / injectable helpers for Rocket.Chat ↔ Grok wake path.

Production modules (rc_dm_poll, rc_operator_agent) import from here so tests
exercise the real shipped logic without re-implementing it.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping

OPERATOR = "grok"
PRINCIPAL = "principal"

DEFAULT_AGENCY = Path.home() / ".grok" / "agency"
DEFAULT_IDEA_PROJECTS = Path.home() / "IdeaProjects"
DEFAULT_WAKE_DIR = DEFAULT_AGENCY / "ops" / "rocketchat" / "wake"
DEFAULT_LOG_DIR = Path.home() / "logs" / "rocketchat-dm-wake"
DEFAULT_LOCK_DIR = DEFAULT_LOG_DIR / "wake.lock.d"
DEFAULT_STATE_PATH = DEFAULT_WAKE_DIR / "state.json"
DEFAULT_CHANNEL_MAP = DEFAULT_WAKE_DIR / "channel_projects.json"
DEFAULT_GROK_BIN = os.environ.get("GROK_BIN", str(Path.home() / ".local" / "bin" / "grok"))
DEFAULT_HERMES_BIN = os.environ.get(
    "HERMES_BIN", str(Path.home() / ".local" / "bin" / "hermes")
)
DEFAULT_HERMES_PROFILE = os.environ.get("RC_HERMES_PROFILE", "idea")
# IMP-09: single default; env may override. Must match wake_grok / launchd.
DEFAULT_WAKE_MAX_TURNS = "100"
DEFAULT_MAX_TURNS = os.environ.get("RC_WAKE_MAX_TURNS", DEFAULT_WAKE_MAX_TURNS)

# IMP-02: wake subprocess timeout vs lock stale reclaim (stale must exceed timeout).
DEFAULT_WAKE_TIMEOUT_S = int(os.environ.get("RC_WAKE_TIMEOUT_S", "600"))
DEFAULT_WAKE_LOCK_STALE_S = int(
    os.environ.get("RC_WAKE_LOCK_STALE_S", str(DEFAULT_WAKE_TIMEOUT_S + 300))
)

# Wake tool-approval profiles (IMP-01). Default is restricted: no --always-approve.
APPROVAL_RESTRICTED = "restricted"
APPROVAL_ADMIN = "admin"
# Env: RC_WAKE_APPROVAL_MODE=restricted|admin
# Env: RC_WAKE_ADMIN_DMS_ONLY=1 (default) → admin applies only to DMs; channels stay restricted.
DEFAULT_APPROVAL_MODE = APPROVAL_RESTRICTED

# Auto-create IdeaProjects/<slug> for new channels (default ON).
# Kill switch only: RC_AUTO_CREATE_PROJECTS=0|false|no|off.
def auto_create_projects_from_env(env: dict[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    raw = (source.get("RC_AUTO_CREATE_PROJECTS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")

# Legacy placeholder text still stripped from finals if the model echoes it.
THINKING_PLACEHOLDER = "Thinking..."

# Initial agent-bubble text before the first streaming-json thought chunk.
# Same msgId is chat.update'd with thoughts, then with the final answer only.
ACTIVITY_PLACEHOLDER = "…"

# Only DMs use the agency spine. All channels/groups map under ~/IdeaProjects.
# (dm: labels are handled via room_type / name prefix, not this set.)
NON_PROJECT_ROOM_NAMES = frozenset()


def load_env(path: Path) -> dict[str, str]:
    """Parse KEY=value secrets file. Raises FileNotFoundError if missing."""
    env: dict[str, str] = {}
    if not path.is_file():
        raise FileNotFoundError(f"missing secrets: {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def load_state(state_path: Path) -> dict:
    """Load state.json; migrate to v2 schema (IMP-14)."""
    if not state_path.is_file():
        return migrate_state_to_v2({})
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return migrate_state_to_v2({})
    if not isinstance(raw, dict):
        return migrate_state_to_v2({})
    return migrate_state_to_v2(raw)


def save_state(state: dict, state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = migrate_state_to_v2(state if isinstance(state, dict) else {})
    import threading
    tmp = state_path.with_name(f"{state_path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(state_path)


def new_principal_messages(
    messages: list[dict],
    last_id: str | None,
    *,
    principal: str = PRINCIPAL,
) -> list[dict]:
    """
    Return principal messages strictly after last_id.

    messages: chronological (oldest first).
    last_id None or empty → no wake candidates (seed path uses empty list).
    """
    if not messages:
        return []
    if last_id is None:
        return []
    out: list[dict] = []
    seen_last = False
    for m in messages:
        mid = m.get("_id")
        if not seen_last:
            if mid == last_id:
                seen_last = True
            continue
        user = (m.get("u") or {}).get("username")
        if user == principal and message_has_handleable_content(m):
            out.append(m)
    if not seen_last and last_id:
        last_ts = None
        for m in messages:
            if m.get("_id") == last_id:
                last_ts = m.get("ts")
        if last_ts:
            for m in messages:
                if m.get("ts", "") <= last_ts:
                    continue
                user = (m.get("u") or {}).get("username")
                if user == principal and message_has_handleable_content(m):
                    out.append(m)
        else:
            for m in messages[-5:]:
                user = (m.get("u") or {}).get("username")
                if user == principal and message_has_handleable_content(m):
                    out.append(m)
    return out


def seed_state_from_messages(
    messages: list[dict],
    room_id: str,
    *,
    newest_first: bool = False,
) -> dict | None:
    """
    Build seed state for first run: remember newest message, no wake.

    messages: chronological (oldest first) unless newest_first=True (API im.history order).
    Returns None if messages empty.
    """
    if not messages:
        return None
    newest = messages[0] if newest_first else messages[-1]
    from datetime import datetime, timezone

    return {
        "last_seen_id": newest.get("_id"),
        "last_seen_ts": newest.get("ts"),
        "room_id": room_id,
        "seeded_at": datetime.now(timezone.utc).isoformat(),
        "last_wake_at": None,
    }


def _pid_is_alive(pid: int) -> bool:
    """True if pid looks like a live process (POSIX)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but not ours — treat as live so we never steal.
        return True
    except OSError:
        return False


def read_lock_holder_pid(lock_dir: Path) -> int | None:
    """Parse holder.pid inside a lock dir; None if missing/invalid."""
    path = lock_dir / "holder.pid"
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        return int(raw.split()[0])
    except (OSError, ValueError):
        return None


def lock_holder_is_alive(lock_dir: Path) -> bool:
    """True when holder.pid exists and the process is still running."""
    pid = read_lock_holder_pid(lock_dir)
    if pid is None:
        return False
    return _pid_is_alive(pid)


def heartbeat_wake_lock(lock_dir: Path) -> None:
    """
    Refresh lock mtime / pid stamp so long wakes are not reclaimed as stale.

    Call periodically while a wake is in progress (IMP-02).
    """
    try:
        if not lock_dir.is_dir():
            return
        pid_path = lock_dir / "holder.pid"
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
        # Touch directory mtime for age-based fallback.
        now = time.time()
        os.utime(lock_dir, (now, now))
    except OSError:
        pass


def _clear_lock_dir_contents(lock_dir: Path) -> bool:
    """Remove lock dir and children. True if gone or never present."""
    try:
        if not lock_dir.exists():
            return True
        if lock_dir.is_dir():
            for child in lock_dir.iterdir():
                try:
                    child.unlink()
                except OSError:
                    pass
            lock_dir.rmdir()
        return not lock_dir.exists()
    except OSError:
        return not lock_dir.exists()


def acquire_wake_lock(
    lock_dir: Path,
    *,
    stale_after_s: float | None = None,
) -> bool:
    """
    mkdir-based single-flight lock. True if acquired.

    IMP-02 rules:
    - Default stale_after_s is DEFAULT_WAKE_LOCK_STALE_S (timeout + margin),
      never shorter than DEFAULT_WAKE_TIMEOUT_S when using defaults.
    - If holder.pid is alive, never steal regardless of age.
    - If holder is dead (or pid missing), reclaim immediately — a dead process
      must not block a room until the stale timer (cross-room parallelism).
    - If holder is unknown/unreadable and age > stale_after_s, reclaim.
    """
    if stale_after_s is None:
        stale_after_s = float(DEFAULT_WAKE_LOCK_STALE_S)
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_dir.mkdir()
        try:
            (lock_dir / "holder.pid").write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass
        return True
    except FileExistsError:
        try:
            # Live holder: never steal (even if mtime is old — e.g. clock skew).
            if lock_holder_is_alive(lock_dir):
                return False
            # Dead or missing holder: reclaim. Age gate only when we cannot
            # decide (pid file unreadable) — treat unknown like stale check.
            pid_file = lock_dir / "holder.pid"
            holder_known_dead = False
            if not pid_file.is_file():
                holder_known_dead = True
            else:
                try:
                    raw = pid_file.read_text(encoding="utf-8").strip()
                    int(raw)
                    # Parsed pid but not alive → dead
                    holder_known_dead = True
                except (OSError, ValueError):
                    holder_known_dead = False
            age = time.time() - lock_dir.stat().st_mtime
            if not holder_known_dead and age <= stale_after_s:
                return False
            if not _clear_lock_dir_contents(lock_dir):
                return False
            try:
                lock_dir.mkdir()
                try:
                    (lock_dir / "holder.pid").write_text(
                        str(os.getpid()), encoding="utf-8"
                    )
                except OSError:
                    pass
                return True
            except FileExistsError:
                return False
        except OSError:
            return False


def release_wake_lock(lock_dir: Path) -> None:
    _clear_lock_dir_contents(lock_dir)


def force_clear_wake_lock(lock_dir: Path) -> bool:
    """Unconditionally remove a stuck lock dir. Returns True if cleared/absent."""
    return _clear_lock_dir_contents(lock_dir)


def wake_timeout_and_lock_stale_are_consistent(
    wake_timeout_s: float | None = None,
    stale_after_s: float | None = None,
) -> bool:
    """True when lock stale reclaim waits longer than the wake subprocess timeout."""
    wt = float(DEFAULT_WAKE_TIMEOUT_S if wake_timeout_s is None else wake_timeout_s)
    st = float(DEFAULT_WAKE_LOCK_STALE_S if stale_after_s is None else stale_after_s)
    return st > wt


def room_wake_lock_dir(base_lock_dir: Path, room_id: str) -> Path:
    """
    IMP-10: per-room lock path under base_lock_dir/rooms/<safe_rid>.

    Same room serializes; different rooms run concurrently (subject to
    RC_WAKE_MAX_CONCURRENT).
    """
    import re

    rid = (room_id or "unknown").strip() or "unknown"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", rid)[:80]
    return Path(base_lock_dir) / "rooms" / safe


# Default: many concurrent rooms so a long Agency wake does not block DMs.
# Per-room locks still force same-room serial. Override with RC_WAKE_MAX_CONCURRENT.
DEFAULT_MAX_CONCURRENT_WAKES = 16


def max_concurrent_wakes_from_env(env: dict[str, str] | None = None) -> int:
    """RC_WAKE_MAX_CONCURRENT — default 16 (per-room serial, cross-room parallel)."""
    source = env if env is not None else os.environ
    raw = (source.get("RC_WAKE_MAX_CONCURRENT") or "").strip()
    if not raw:
        return DEFAULT_MAX_CONCURRENT_WAKES
    try:
        n = int(raw)
    except ValueError:
        n = DEFAULT_MAX_CONCURRENT_WAKES
    return max(1, n)


def pick_next_pending_index_for_free_room(
    pending: list,
    *,
    busy_room_ids: set[str] | frozenset[str],
) -> int | None:
    """
    Index of the first pending item whose ``rid`` is not busy.

    Preserves FIFO *within* a room (first free-room hit wins among free rooms;
    earlier busy-room items stay queued). Cross-room work is not blocked by a
    busy head-of-queue room.
    """
    for i, item in enumerate(pending):
        if not isinstance(item, dict):
            continue
        rid = str(item.get("rid") or "").strip()
        if rid not in busy_room_ids:
            return i
    return None


def count_active_room_locks(base_lock_dir: Path) -> int:
    """Count locks with a live holder (per-room under rooms/, else legacy base)."""
    rooms = Path(base_lock_dir) / "rooms"
    n = 0
    if rooms.is_dir():
        for child in rooms.iterdir():
            if child.is_dir() and lock_holder_is_alive(child):
                n += 1
        return n
    # Legacy single lock at base — only count if holder process is alive
    base = Path(base_lock_dir)
    if base.is_dir() and lock_holder_is_alive(base):
        return 1
    return 0


def get_room_session_id(state: dict, room_id: str) -> str | None:
    """Pinned headless Grok session id for a Rocket.Chat room (same chat continuity)."""
    if not room_id:
        return None
    sessions = state.get("grok_sessions") or {}
    if isinstance(sessions, dict):
        sid = sessions.get(room_id)
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    # legacy single-session field (pre per-room)
    legacy = state.get("grok_session_id")
    if isinstance(legacy, str) and legacy.strip() and state.get("room_id") == room_id:
        return legacy.strip()
    return None


def get_room_cwd(state: dict, room_id: str) -> str | None:
    """Pinned project cwd for a room (must match the session's original --cwd)."""
    if not room_id:
        return None
    cwds = state.get("grok_cwds") or {}
    if isinstance(cwds, dict):
        p = cwds.get(room_id)
        if isinstance(p, str) and p.strip():
            return p.strip()
    return None


def set_room_session_id(state: dict, room_id: str, session_id: str | None) -> dict:
    """
    Return state with per-room session id set or cleared.

    On clear: remove grok_sessions[room_id], clear rooms[room_id].session_id if
    present, and drop legacy grok_session_id when it applies to this room so
    get_room_session_id cannot resurrect the pin (NF-SPEC-03 /new).
    """
    sessions = dict(state.get("grok_sessions") or {})
    if session_id:
        sessions[room_id] = session_id
        state["grok_session_id"] = session_id  # last used (debug / legacy)
        state["room_id"] = room_id
    else:
        sessions.pop(room_id, None)
        # Legacy single-session field is only meaningful for state["room_id"].
        # After a normal wake, room_id is set; leaving grok_session_id made /new
        # a no-op for the next --resume (get_room_session_id legacy fallback).
        if state.get("room_id") == room_id:
            state.pop("grok_session_id", None)
        rooms = state.get("rooms")
        if isinstance(rooms, dict) and room_id in rooms:
            entry = dict(rooms.get(room_id) or {})
            entry.pop("session_id", None)
            rooms = dict(rooms)
            rooms[room_id] = entry
            state["rooms"] = rooms
    state["grok_sessions"] = sessions
    return state


def set_room_cwd(state: dict, room_id: str, cwd: str | None) -> dict:
    """Pin the project directory used for this room's Grok sessions."""
    cwds = dict(state.get("grok_cwds") or {})
    if cwd:
        cwds[room_id] = cwd
        state["last_project_cwd"] = cwd
    else:
        cwds.pop(room_id, None)
    state["grok_cwds"] = cwds
    return state


def slugify_channel_name(room_name: str) -> str:
    """
    Map a Rocket.Chat room label to an IdeaProjects directory slug.

    Examples:
      Prime-Gap-Structure → prime-gap-structure
      #Prime Gap Structure → prime-gap-structure
      dm:principal → dm-principal
    """
    import re

    name = (room_name or "").strip()
    if name.startswith("#"):
        name = name[1:]
    if name.lower().startswith("dm:"):
        name = name[3:]
    name = name.strip()
    # Normalize separators
    name = name.replace("_", "-").replace(" ", "-")
    name = re.sub(r"[^A-Za-z0-9.-]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-.")
    return name.lower() or "unnamed-channel"


def load_channel_project_map(map_path: Path | None = None) -> dict[str, str]:
    """
    Optional overrides: channel name (any case) or slug → absolute or relative path.

    File: ops/rocketchat/wake/channel_projects.json
    {
      "Prime-Gap-Structure": "prime-gap-structure",
      "Agency": "/Users/.../.grok/agency"
    }
    """
    path = map_path or DEFAULT_CHANNEL_MAP
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or k.startswith("_"):
            continue
        key = k.strip()
        if not key:
            continue
        # Legacy: string cwd. NF-SPEC-04: object profile with "cwd" (+ mode=agy-collab).
        if isinstance(v, str):
            val = v.strip()
            if val:
                out[key] = val
            continue
        if isinstance(v, dict):
            cwd = v.get("cwd")
            if isinstance(cwd, str) and cwd.strip():
                out[key] = cwd.strip()
    return out


def _resolve_existing_project_dir(slug: str, idea_projects: Path) -> Path | None:
    """Find an existing IdeaProjects child matching slug (case-insensitive)."""
    if not idea_projects.is_dir():
        return None
    exact = idea_projects / slug
    if exact.is_dir():
        return exact.resolve()
    # case-insensitive / hyphen-vs-underscore soft match
    target_keys = {
        slug.lower(),
        slug.lower().replace("-", ""),
        slug.lower().replace("-", "_"),
    }
    try:
        children = list(idea_projects.iterdir())
    except OSError:
        return None
    for child in children:
        if not child.is_dir() or child.name.startswith("."):
            continue
        keys = {
            child.name.lower(),
            child.name.lower().replace("-", ""),
            child.name.lower().replace("_", ""),
            child.name.lower().replace("_", "-"),
        }
        if keys & target_keys:
            return child.resolve()
    return None


def ensure_project_dir(path: Path, *, room_name: str, created_note: bool = True) -> Path:
    """Create project directory (+ minimal README) if missing. Returns resolved path."""
    path = path.expanduser()
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.md"
    if created_note and not readme.is_file():
        readme.write_text(
            f"# {path.name}\n\n"
            f"Auto-created for Rocket.Chat channel **{room_name}** "
            f"({datetime_utc_now()}).\n\n"
            f"Grok operator wakes in this directory for that channel.\n",
            encoding="utf-8",
        )
    return path.resolve()


def datetime_utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_project_cwd(
    room_name: str,
    *,
    room_type: str | None = None,
    idea_projects: Path | str | None = None,
    agency: Path | str | None = None,
    channel_map: dict[str, str] | None = None,
    create_if_missing: bool | None = None,
) -> tuple[Path, str]:
    """
    Map a Rocket.Chat room to a filesystem project directory.

    Returns (cwd_path, reason) where reason is one of:
      dm | special | map | existing | created | no_create | agency_fallback

    Rules:
    - DM rooms only → agency spine (~/.grok/agency)
    - All channels/groups → ~/IdeaProjects (map / existing / optional create)
    - Optional channel_projects.json overrides (paths under IdeaProjects or absolute)
    - create_if_missing defaults from RC_AUTO_CREATE_PROJECTS (default true / always-on)
    """
    if create_if_missing is None:
        create_if_missing = auto_create_projects_from_env()

    agency_path = Path(agency or DEFAULT_AGENCY).expanduser()
    ideas = Path(idea_projects or DEFAULT_IDEA_PROJECTS).expanduser()
    name = (room_name or "").strip() or "unnamed"
    rtype = (room_type or "").strip().lower()

    # Direct messages only — not channels named "agency" / "general" / etc.
    if rtype == "d" or name.lower().startswith("dm:") or name.lower() == "dm":
        return agency_path.resolve(), "dm"

    slug = slugify_channel_name(name)

    # Manual overrides (by original name, stripped #, or slug)
    cmap = channel_map if channel_map is not None else load_channel_project_map()
    for key in (name, name.lstrip("#"), slug, name.lower(), slugify_channel_name(name)):
        if key in cmap:
            raw = cmap[key]
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = ideas / raw
            if create_if_missing:
                p = ensure_project_dir(p, room_name=name, created_note=not p.exists())
            else:
                p = p.resolve() if p.exists() else p
            return p, "map"

    existing = _resolve_existing_project_dir(slug, ideas)
    if existing is not None:
        return existing, "existing"

    target = ideas / slug
    if create_if_missing:
        return ensure_project_dir(target, room_name=name), "created"

    # IMP-19: do not create; still return intended path for logging/cwd attempt
    return target, "no_create"


def compose_unified_reply(
    final_body: str,
    *,
    thinking: str = THINKING_PLACEHOLDER,
) -> str:
    """
    Clean final-answer text (no intermediate placeholder prefix).

    Strips a leading Thinking... or activity placeholder line if the model
    echoed one. Empty body falls back to ACTIVITY_PLACEHOLDER (callers usually
    pass FINAL_ERR text instead).
    """
    body = (final_body or "").strip()
    prefixes = []
    for p in (thinking, THINKING_PLACEHOLDER, ACTIVITY_PLACEHOLDER):
        p = (p or "").strip()
        if p and p not in prefixes:
            prefixes.append(p)
    if not body:
        return ACTIVITY_PLACEHOLDER
    bl = body.lower()
    for prefix in prefixes:
        pl = prefix.lower()
        if bl == pl:
            return ACTIVITY_PLACEHOLDER
        # Only strip when prefix is its own first line (not "Thinking... about X")
        if bl.startswith(pl + "\n"):
            rest = body[len(prefix) :].lstrip()
            return rest if rest else ACTIVITY_PLACEHOLDER
    return body


# RC message markdown is a limited subset (@rocket.chat/message-parser / product docs):
# bold *x*, italic _x_, strike ~x~, quotes, lists, # headings, code — not full GFM.
# Horizontal rules (--- / *** / ___) are NOT rendered as <hr> (forum + live RC 8.6).
# Prefer bold labels over ## (too large on mobile). Use a plain unicode rule line.
THOUGHTS_SECTION_LABEL = "*Thoughts*"
THOUGHTS_SECTION_RULE = "────────────────"


def compose_final_with_thoughts(
    final_body: str,
    thought_text: str = "",
    *,
    thinking: str = THINKING_PLACEHOLDER,
) -> str:
    """
    Published agent-bubble body: keep thoughts, then final answer.

    When thought_text is non-empty after strip (RC-safe markup):

        *Thoughts*

        <thought stream>

        ────────────────

        <final answer>

    Uses bold (not ##) for a smaller label. Uses a unicode line instead of
    markdown --- (RC does not render markdown horizontal rules).

    When there is no thought stream, returns compose_unified_reply(final) only.
    """
    answer = compose_unified_reply(final_body, thinking=thinking)
    thoughts = (thought_text or "").strip()
    if not thoughts:
        return answer
    # Avoid stacking if the answer already embeds a Thoughts section (retries).
    head = answer.lstrip()
    if head.startswith("## Thoughts") or head.startswith(THOUGHTS_SECTION_LABEL):
        return answer
    return (
        f"{THOUGHTS_SECTION_LABEL}\n\n"
        f"{thoughts}\n\n"
        f"{THOUGHTS_SECTION_RULE}\n\n"
        f"{answer}"
    )


def extract_session_id_from_output(text: str) -> str | None:
    """Parse sessionId from headless --output-format json (or mixed log)."""
    import re

    if not text:
        return None
    # Prefer last complete JSON object line
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ("sessionId", "session_id"):
            sid = obj.get(key)
            if isinstance(sid, str) and sid.strip():
                return sid.strip()
    m = re.search(r'"sessionId"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1).strip()
    m = re.search(r'"session_id"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1).strip()
    return None


def normalize_approval_mode(raw: str | None) -> str:
    """
    Map a config string to APPROVAL_RESTRICTED or APPROVAL_ADMIN.

    Accepts common aliases (full, unrestricted → admin). Empty/unknown → restricted.
    """
    value = (raw or "").strip().lower()
    if value in ("admin", "unrestricted", "full", "always-approve", "always_approve"):
        return APPROVAL_ADMIN
    if value in ("restricted", "safe", "default", "acceptedits", "accept_edits", ""):
        return APPROVAL_RESTRICTED
    # Unknown values fail closed (safer for phone-driven wakes).
    return APPROVAL_RESTRICTED


def configured_approval_mode_from_env(env: dict[str, str] | None = None) -> str:
    """
    Read RC_WAKE_APPROVAL_MODE from env (or os.environ). Default: restricted.
    """
    source = env if env is not None else os.environ
    return normalize_approval_mode(source.get("RC_WAKE_APPROVAL_MODE"))


def admin_dms_only_from_env(env: dict[str, str] | None = None) -> bool:
    """
    When True (default), configured admin mode applies only to direct messages.

    Channels/groups stay restricted even if RC_WAKE_APPROVAL_MODE=admin.
    Set RC_WAKE_ADMIN_DMS_ONLY=0 to allow admin on all rooms.
    """
    source = env if env is not None else os.environ
    raw = (source.get("RC_WAKE_ADMIN_DMS_ONLY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def is_dm_room(room_type: str | None = None, room_name: str = "") -> bool:
    """True for Rocket.Chat DMs (type d or dm: name prefix)."""
    rtype = (room_type or "").strip().lower()
    name = (room_name or "").strip().lower()
    return rtype == "d" or name.startswith("dm:") or name == "dm"


def resolve_approval_mode(
    *,
    room_type: str | None = None,
    room_name: str = "",
    configured: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """
    Effective approval mode for one wake.

    1) Start from configured mode (arg or RC_WAKE_APPROVAL_MODE; default restricted).
    2) If admin and admin_dms_only, non-DM rooms force restricted.
    """
    mode = normalize_approval_mode(
        configured if configured is not None else configured_approval_mode_from_env(env)
    )
    if mode == APPROVAL_ADMIN and admin_dms_only_from_env(env):
        if not is_dm_room(room_type, room_name):
            return APPROVAL_RESTRICTED
    return mode


def approval_mode_cli_flags(approval_mode: str) -> list[str]:
    """
    Grok CLI flags for the given approval profile.

    admin      → --always-approve (historical full power)
    restricted → --permission-mode auto (headless-safe; not --always-approve)

    Important (2026-07-10 incident): --permission-mode acceptEdits is **not** safe
    for Rocket.Chat headless wakes. With no TTY to approve tools, Grok returns
    stopReason=Cancelled, leaves the reply file empty, and the operator posts
    "(No reply file content from the wake...)". Reproduced for in-cwd Write.
    `auto` completes EndTurn and writes the reply file without --always-approve.
    """
    mode = normalize_approval_mode(approval_mode)
    if mode == APPROVAL_ADMIN:
        return ["--always-approve"]
    # Restricted: no --always-approve. Use `auto` (not acceptEdits) so headless
    # tool use can finish and write the operator reply file.
    return ["--permission-mode", "auto"]


# --- NF-SPEC-06: message reactions as wake ack (zero extra bubbles) ---
# Env: RC_WAKE_REACT=1 (default on); RC_WAKE_REACT_START/OK/ERR = RC shortnames.

DEFAULT_REACT_START = "eyes"
DEFAULT_REACT_OK = "white_check_mark"
DEFAULT_REACT_ERR = "warning"


def _env_flag_enabled(raw: str | None, *, default: bool = True) -> bool:
    """Parse common truthy/falsey env strings. Empty → default."""
    if raw is None:
        return default
    value = raw.strip().lower()
    if not value:
        return default
    if value in ("0", "false", "no", "off"):
        return False
    if value in ("1", "true", "yes", "on"):
        return True
    return default


def wake_react_enabled(env: dict[str, str] | None = None) -> bool:
    """
    RC_WAKE_REACT master gate (NF-SPEC-06 R1). Default on.
    When off, operator must not call chat.react.
    """
    source = env if env is not None else os.environ
    return _env_flag_enabled(source.get("RC_WAKE_REACT"), default=True)


def wake_react_emoji(
    kind: str, env: dict[str, str] | None = None
) -> str:
    """
    RC shortname for start / ok / err reactions (N3).

    kind: "start" | "ok" | "err"
    """
    source = env if env is not None else os.environ
    kind_norm = (kind or "").strip().lower()
    if kind_norm == "start":
        raw = (source.get("RC_WAKE_REACT_START") or DEFAULT_REACT_START).strip()
        return raw or DEFAULT_REACT_START
    if kind_norm in ("ok", "success", "final_ok"):
        raw = (source.get("RC_WAKE_REACT_OK") or DEFAULT_REACT_OK).strip()
        return raw or DEFAULT_REACT_OK
    if kind_norm in ("err", "error", "fail", "final_err"):
        raw = (source.get("RC_WAKE_REACT_ERR") or DEFAULT_REACT_ERR).strip()
        return raw or DEFAULT_REACT_ERR
    return DEFAULT_REACT_START


def build_wake_argv(
    prompt_path: Path | str,
    *,
    grok_bin: str | None = None,
    agency: Path | str | None = None,
    cwd: Path | str | None = None,
    max_turns: str | int | None = None,
    resume_session_id: str | None = None,
    output_format: str | None = "json",
    approval_mode: str | None = None,
    model: str | None = None,
    effort: str | None = None,
) -> list[str]:
    """
    Production argv for headless Grok wake.

    cwd: project directory for this channel (defaults to agency for DMs).
    When resume_session_id is set, uses --resume so multi-message chats keep
    the same Grok session. output_format=json captures sessionId for pinning.

    approval_mode: restricted (default) or admin. None → resolve from env
    without room context (see resolve_approval_mode for DM-only admin).

    model: optional room pin → ``--model <id>`` (NF-SPEC-03 /model).
    effort: optional room pin → ``--reasoning-effort <level>`` (NF-SPEC-03 /effort).

    Must never include --disallowed-tools Agent (breaks session build).
    """
    bin_path = grok_bin or DEFAULT_GROK_BIN
    # Prefer explicit project cwd; `agency` kept as backward-compatible alias.
    workdir = str(cwd or agency or DEFAULT_AGENCY)
    turns = str(max_turns if max_turns is not None else DEFAULT_MAX_TURNS)
    mode = (
        normalize_approval_mode(approval_mode)
        if approval_mode is not None
        else resolve_approval_mode()
    )
    argv = [
        bin_path,
        "--cwd",
        workdir,
        *approval_mode_cli_flags(mode),
        "--max-turns",
        turns,
        "--prompt-file",
        str(prompt_path),
    ]
    model_id = (model or "").strip()
    if model_id:
        argv.extend(["--model", model_id])
    effort_level = (effort or "").strip().lower()
    if effort_level:
        if effort_level == "max":
            effort_level = "xhigh"
        argv.extend(["--reasoning-effort", effort_level])
    if output_format:
        argv.extend(["--output-format", output_format])
    if resume_session_id:
        argv.extend(["--resume", resume_session_id])
    return argv

def build_agy_wake_argv(
    prompt_path: Path | str,
    *,
    max_turns: str | int | None = None,
    resume_session_id: str | None = None,
    approval_mode: str | None = None,
    model: str | None = None,
) -> list[str]:
    """Production argv for headless Antigravity (agy) RC wake.

    Important (2026-07-16): `--mode accept-edits` is **not** safe headless. Jetski
    auto-denies `write_file` with no TTY, exits with empty reply, FINAL_ERR spam.
    Agy has no Grok-style `--permission-mode auto`. RC wakes must write the reply
    file, so we use `--dangerously-skip-permissions` for both admin and restricted
    (policy still lives in the inject: prefer project cwd, no secrets dumps).
    Override with RC_AGY_FORCE_ACCEPT_EDITS=1 only for interactive debugging.
    """
    mode = (
        normalize_approval_mode(approval_mode)
        if approval_mode is not None
        else resolve_approval_mode()
    )
    argv: list[str] = ["agy", "--prompt", Path(prompt_path).read_text(encoding="utf-8")]
    if resume_session_id:
        argv.extend(["--conversation", str(resume_session_id)])
    force_accept = (os.environ.get("RC_AGY_FORCE_ACCEPT_EDITS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if force_accept and mode != APPROVAL_ADMIN:
        argv.extend(["--mode", "accept-edits"])
    else:
        # Headless-safe for admin and restricted (see docstring).
        argv.append("--dangerously-skip-permissions")
    model_id = (model or "").strip()
    if model_id:
        argv.extend(["--model", model_id])
    return argv


def wake_backend_from_env(env: dict[str, str] | None = None) -> str:
    """RC_WAKE_BACKEND=grok|hermes|agy (default grok)."""
    source = env if env is not None else os.environ
    raw = (source.get("RC_WAKE_BACKEND") or "grok").strip().lower()
    if raw in ("hermes", "nous", "hermes-agent"):
        return "hermes"
    if raw in ("agy", "antigravity"):
        return "agy"
    return "grok"

def hermes_approval_cli_flags(approval_mode: str | None = None) -> list[str]:
    """
    Hermes headless approval flags.

    restricted → no --yolo (manual/smart prompts may block tools; prefer answer + reply file)
    admin → --yolo
    """
    mode = normalize_approval_mode(approval_mode)
    if mode == APPROVAL_ADMIN:
        return ["--yolo"]
    return []


def build_hermes_wake_argv(
    prompt_path: Path | str,
    *,
    hermes_bin: str | None = None,
    profile: str | None = None,
    max_turns: str | int | None = None,
    resume_session_id: str | None = None,
    approval_mode: str | None = None,
    model: str | None = None,
    query_text: str | None = None,
) -> list[str]:
    """
    Production argv for headless Hermes RC wake.

    Hermes has no --prompt-file; the full prompt is passed as ``chat -q``.
    Working directory is set by the operator via subprocess cwd (not a CLI flag).
    Session resume uses ``hermes --resume <id>`` before the chat subcommand.
    Quiet mode (-Q) keeps stdout mostly the final answer; session_id lands on stderr.
    """
    bin_path = hermes_bin or DEFAULT_HERMES_BIN
    prof = (profile or DEFAULT_HERMES_PROFILE).strip() or DEFAULT_HERMES_PROFILE
    turns = str(max_turns if max_turns is not None else DEFAULT_MAX_TURNS)
    mode = (
        normalize_approval_mode(approval_mode)
        if approval_mode is not None
        else resolve_approval_mode()
    )
    if query_text is not None:
        query = query_text
    else:
        query = Path(prompt_path).read_text(encoding="utf-8")
    argv: list[str] = [bin_path, "-p", prof]
    if resume_session_id:
        argv.extend(["--resume", str(resume_session_id)])
    argv.extend(
        [
            "chat",
            "-q",
            query,
            "-Q",
            "--max-turns",
            turns,
            "--no-restore-cwd",
            "--accept-hooks",
            *hermes_approval_cli_flags(mode),
        ]
    )
    model_id = (model or "").strip()
    if model_id:
        argv.extend(["-m", model_id])
    return argv


def parse_hermes_session_id(text: str) -> str | None:
    """Extract Hermes session id from combined stdout/stderr log text."""
    import re

    if not text:
        return None
    # Quiet mode: "session_id: 20260713_215537_f5698c"
    m = re.search(r"(?im)^\s*session_id:\s*([0-9a-zA-Z_\-]+)\s*$", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?i)session[_\s-]?id[:\s]+([0-9]{8}_[0-9]{6}_[0-9a-f]+)", text)
    if m:
        return m.group(1).strip()
    return None


def extract_hermes_reply_from_output(text: str) -> str:
    """
    Best-effort final answer from Hermes -Q combined log when reply file is empty.

    Strips known noise lines (toolset warnings, session_id footer).
    """
    if not text:
        return ""
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        low = s.lower()
        if low.startswith("session_id:"):
            continue
        if low.startswith("warning: unknown toolsets"):
            continue
        if s.startswith("cmd:"):
            continue
        if low.startswith("title ") and "workspace" in low:
            continue
        lines.append(line.rstrip())
    # Drop leading empty lines and trailing empties
    body = "\n".join(lines).strip()
    return body


def wake_argv_is_safe(argv: list[str]) -> bool:
    """Regression: broken Agent disallow flag must not appear."""
    joined = " ".join(argv)
    if "--disallowed-tools" in argv:
        # any disallowed-tools Agent is unsafe for this install
        for i, part in enumerate(argv):
            if part == "--disallowed-tools" and i + 1 < len(argv):
                if "Agent" in argv[i + 1]:
                    return False
            if part.startswith("--disallowed-tools=") and "Agent" in part:
                return False
    if "disallowed-tools" in joined and "Agent" in joined:
        return False
    return True


# Rocket.Chat voice notes / uploads we will attempt to STT.
AUDIO_EXTENSIONS = frozenset(
    {
        ".m4a",
        ".mp3",
        ".wav",
        ".ogg",
        ".oga",
        ".webm",
        ".aac",
        ".mp4",
        ".caf",
        ".opus",
        ".flac",
        ".amr",
        ".3gp",
    }
)
AUDIO_MIME_PREFIXES = ("audio/", "video/webm", "video/mp4")

# Image uploads for multimodal wake (download → local path → Grok read_file).
IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".heic",
        ".heif",
        ".bmp",
        ".tif",
        ".tiff",
    }
)
IMAGE_MIME_PREFIXES = ("image/",)

# Non-image documents for wake path inject (NF-SPEC-05 FR-D1).
DOCUMENT_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".json",
        ".py",
        ".rs",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".html",
        ".css",
        ".yaml",
        ".yml",
        ".toml",
        ".log",
        ".pdf",
        ".xml",
        ".sh",
        ".c",
        ".h",
        ".cpp",
        ".go",
        ".java",
        ".rb",
        ".php",
        ".sql",
        ".ini",
        ".cfg",
        ".conf",
        ".env.example",
    }
)
DOCUMENT_MIME_PREFIXES = (
    "text/",
    "application/pdf",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
    "application/toml",
    "application/x-sh",
    "application/x-python",
)
# Default denylist for binary/executable/archive (FR-D4).
BINARY_SKIP_EXTENSIONS = frozenset(
    {
        ".exe",
        ".dmg",
        ".pkg",
        ".app",
        ".msi",
        ".dll",
        ".so",
        ".dylib",
        ".zip",
        ".rar",
        ".7z",
        ".tar",
        ".gz",
        ".tgz",
        ".bz2",
        ".xz",
        ".iso",
        ".bat",
        ".cmd",
        ".ps1",
        ".bin",
    }
)


def _basename_from_name_or_link(name: str | None, link: str | None = None) -> str:
    """Best-effort basename from a file name or /file-upload/… URL."""
    for raw in (name, link):
        if not raw:
            continue
        s = str(raw).strip().split("?", 1)[0]
        if "/file-upload/" in s:
            s = s.split("/file-upload/", 1)[-1]
            # id/filename → filename
            parts = [p for p in s.split("/") if p]
            if len(parts) >= 2:
                s = parts[-1]
            elif parts:
                s = parts[0]
        base = Path(s.replace("\\", "/")).name
        if base:
            return base
    return ""


def _is_thumb_candidate(
    name: str | None,
    link: str | None = None,
    type_group: str | None = None,
) -> bool:
    """
    True for Rocket.Chat-generated thumbnail siblings of a full upload.

    Live RC 8.6 payloads include files[] entries with typeGroup=thumb and
    names like thumb-IMG_1651.jpg; attachments.image_url often points at the
    thumb id while title_link points at the full file.
    """
    tg = (type_group or "").strip().lower()
    if tg in ("thumb", "thumbnail"):
        return True
    base = _basename_from_name_or_link(name, link).lower()
    if base.startswith("thumb-") or base.startswith("thumb_"):
        return True
    link_l = (link or "").strip().lower()
    if "thumb-" in link_l or "thumb_" in link_l:
        # Avoid matching unrelated substrings in host paths; require path segment-ish
        if "/thumb-" in link_l or "/thumb_" in link_l or "thumb-img" in link_l:
            return True
        if base and ("thumb-" in base or base.startswith("thumb")):
            return True
    return False


def _looks_like_audio(name: str | None, mime: str | None) -> bool:
    """True if filename extension or MIME type suggests audio (or mobile voice note)."""
    mime_l = (mime or "").strip().lower()
    if mime_l:
        for prefix in AUDIO_MIME_PREFIXES:
            if mime_l.startswith(prefix):
                return True
        if mime_l in ("application/ogg",):
            return True
    name_l = (name or "").strip().lower()
    if not name_l:
        return False
    base = name_l.split("?", 1)[0]
    for ext in AUDIO_EXTENSIONS:
        if base.endswith(ext):
            return True
    return False


def _looks_like_image(name: str | None, mime: str | None) -> bool:
    """True if filename extension or MIME type suggests a still image."""
    mime_l = (mime or "").strip().lower()
    if mime_l:
        for prefix in IMAGE_MIME_PREFIXES:
            if mime_l.startswith(prefix):
                return True
    name_l = (name or "").strip().lower()
    if not name_l:
        return False
    base = name_l.split("?", 1)[0]
    for ext in IMAGE_EXTENSIONS:
        if base.endswith(ext):
            return True
    return False


def extract_file_candidates(msg: dict) -> list[dict[str, str]]:
    """
    Collect downloadable file refs from a Rocket.Chat message payload.

    Each item: {id, name, type, title_link, type_group} (missing keys as "").
    Sources: msg.file, msg.files[], msg.attachments[].

    For attachments, prefer title_link (full file) over image_url / image_preview
    (often the thumb id on RC 8.6 mobile uploads).
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(
        file_id: str | None,
        name: str | None,
        mime: str | None = None,
        title_link: str | None = None,
        type_group: str | None = None,
    ) -> None:
        fid = (file_id or "").strip()
        fname = (name or "").strip()
        link = (title_link or "").strip()
        if not fid and not link:
            return
        key = fid or link
        if key in seen:
            return
        seen.add(key)
        if not fname and link:
            fname = _basename_from_name_or_link(None, link)
        out.append(
            {
                "id": fid,
                "name": fname or "upload.bin",
                "type": (mime or "").strip(),
                "title_link": link,
                "type_group": (type_group or "").strip(),
            }
        )

    single = msg.get("file")
    if isinstance(single, dict):
        add(
            single.get("_id"),
            single.get("name"),
            single.get("type"),
            type_group=single.get("typeGroup") or single.get("type_group"),
        )

    files = msg.get("files")
    if isinstance(files, list):
        for f in files:
            if isinstance(f, dict):
                add(
                    f.get("_id"),
                    f.get("name"),
                    f.get("type"),
                    type_group=f.get("typeGroup") or f.get("type_group"),
                )

    attachments = msg.get("attachments")
    if isinstance(attachments, list):
        for att in attachments:
            if not isinstance(att, dict):
                continue
            # Prefer full-file title_link; image_url is frequently the thumb.
            title_link = att.get("title_link")
            if not title_link:
                title_link = (
                    att.get("audio_url")
                    or att.get("video_url")
                    or att.get("image_url")
                    or att.get("image_preview")
                )
            title = att.get("title") or att.get("name")
            mime = (
                att.get("image_type")
                or att.get("audio_type")
                or att.get("video_type")
                or att.get("type")
            )
            nested = att.get("file") if isinstance(att.get("file"), dict) else {}
            fid = nested.get("_id") if nested else att.get("_id")
            tg = None
            if nested:
                tg = nested.get("typeGroup") or nested.get("type_group")
            if not fid and isinstance(title_link, str) and "/file-upload/" in title_link:
                parts = title_link.split("/file-upload/", 1)[-1].split("/")
                if parts:
                    fid = parts[0]
                    if len(parts) > 1 and not title:
                        title = parts[-1].split("?")[0]
            add(
                fid if isinstance(fid, str) else None,
                title
                if isinstance(title, str)
                else (nested.get("name") if nested else None),
                mime
                if isinstance(mime, str)
                else (nested.get("type") if nested else None),
                title_link if isinstance(title_link, str) else None,
                type_group=tg if isinstance(tg, str) else None,
            )

    return out


def extract_audio_file_candidates(msg: dict) -> list[dict[str, str]]:
    """Subset of extract_file_candidates that look like audio / voice notes."""
    return [
        f
        for f in extract_file_candidates(msg)
        if not _is_thumb_candidate(
            f.get("name"), f.get("title_link"), f.get("type_group")
        )
        and (
            _looks_like_audio(f.get("name"), f.get("type"))
            or _looks_like_audio(f.get("title_link"), f.get("type"))
        )
    ]


def extract_image_file_candidates(msg: dict) -> list[dict[str, str]]:
    """
    Subset of extract_file_candidates that look like still images.

    Skips RC-generated thumbs (name thumb-*, typeGroup=thumb, thumb URLs)
    so the wake gets the full image only (NF-SPEC-05 FR-A4).
    """
    out: list[dict[str, str]] = []
    for f in extract_file_candidates(msg):
        if _is_thumb_candidate(
            f.get("name"), f.get("title_link"), f.get("type_group")
        ):
            continue
        if _looks_like_image(f.get("name"), f.get("type")) or _looks_like_image(
            f.get("title_link"), f.get("type")
        ):
            out.append(f)
    return out


def _looks_like_document(name: str | None, mime: str | None) -> bool:
    """True if filename or MIME suggests a readable document (not image/audio)."""
    mime_l = (mime or "").strip().lower()
    if mime_l:
        if mime_l.startswith("image/") or mime_l.startswith("audio/"):
            return False
        for prefix in DOCUMENT_MIME_PREFIXES:
            if mime_l == prefix or mime_l.startswith(prefix.rstrip("/") + "/"):
                return True
            if mime_l.startswith(prefix):
                return True
        if mime_l in (
            "application/pdf",
            "application/json",
            "application/xml",
            "text/plain",
            "text/markdown",
            "text/csv",
        ):
            return True
    base = _basename_from_name_or_link(name).lower()
    if not base:
        return False
    for ext in DOCUMENT_EXTENSIONS:
        if base.endswith(ext):
            return True
    return False


def _looks_like_binary_skip(name: str | None, mime: str | None = None) -> bool:
    """True for executables/archives we refuse to download by default."""
    base = _basename_from_name_or_link(name).lower()
    for ext in BINARY_SKIP_EXTENSIONS:
        if base.endswith(ext):
            return True
    mime_l = (mime or "").strip().lower()
    if mime_l in (
        "application/x-msdownload",
        "application/x-executable",
        "application/x-dosexec",
        "application/zip",
        "application/x-tar",
        "application/gzip",
        "application/x-7z-compressed",
    ):
        return True
    return False


def extract_document_file_candidates(msg: dict) -> list[dict[str, str]]:
    """
    Non-image, non-audio documents for path inject (NF-SPEC-05 FR-A7 / FR-D1).

    Excludes thumbs, images, audio, and denylisted binaries.
    """
    out: list[dict[str, str]] = []
    for f in extract_file_candidates(msg):
        if _is_thumb_candidate(
            f.get("name"), f.get("title_link"), f.get("type_group")
        ):
            continue
        if _looks_like_image(f.get("name"), f.get("type")) or _looks_like_image(
            f.get("title_link"), f.get("type")
        ):
            continue
        if _looks_like_audio(f.get("name"), f.get("type")) or _looks_like_audio(
            f.get("title_link"), f.get("type")
        ):
            continue
        if _looks_like_binary_skip(f.get("name"), f.get("type")):
            continue
        if _looks_like_document(f.get("name"), f.get("type")) or _looks_like_document(
            f.get("title_link"), f.get("type")
        ):
            out.append(f)
    return out


# Call start + hangup/end system message types (NF-SPEC-01 FR-V6)
_VIDEOCONF_START_TYPES = frozenset({"videoconf", "video_conf"})
_VIDEOCONF_END_TYPES = frozenset(
    {
        "videoconf-end",
        "videoconf_end",
        "call-ended",
        "call_ended",
        "video_conf_end",
        "videoconf-ended",
    }
)
_VIDEOCONF_BLOCK_TYPES = frozenset(
    {
        "video_conf",
        "videoconf",
        "video_conf_end",
        "videoconf_end",
        "videoconf-end",
    }
)


def is_videoconf_end_message(msg: dict) -> bool:
    """
    True for call hangup / ended system messages (FR-V6).

    Recognized by is_videoconf_message so intake routes to handle_videoconf_call
    rather than dropping the message or starting a text wake.
    """
    if not isinstance(msg, dict):
        return False
    t = (msg.get("t") or "").strip().lower()
    if t in _VIDEOCONF_END_TYPES:
        return True
    blocks = msg.get("blocks")
    if isinstance(blocks, list):
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bt = (b.get("type") or "").strip().lower()
            if bt in _VIDEOCONF_END_TYPES or ("end" in bt and "conf" in bt):
                return True
    return False


def is_videoconf_message(msg: dict) -> bool:
    """
    True for Rocket.Chat conference-call system messages (Call start **or** end).

    Start: t='videoconf' and/or a video_conf block.
    End: t='videoconf-end' / call-ended / end blocks (NF-SPEC-01 hangup path).
    Hangup must return True so handle_principal_message → handle_videoconf_call.
    """
    if not isinstance(msg, dict):
        return False
    t = (msg.get("t") or "").strip().lower()
    if t in _VIDEOCONF_START_TYPES or t in _VIDEOCONF_END_TYPES:
        return True
    if is_videoconf_end_message(msg):
        return True
    blocks = msg.get("blocks")
    if isinstance(blocks, list):
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bt = (b.get("type") or "").strip().lower()
            if bt in _VIDEOCONF_BLOCK_TYPES:
                return True
    return False


def videoconf_call_id(msg: dict) -> str | None:
    """Extract callId from a videoconf message, if present."""
    blocks = msg.get("blocks")
    if isinstance(blocks, list):
        for b in blocks:
            if not isinstance(b, dict):
                continue
            cid = b.get("callId") or b.get("blockId")
            if isinstance(cid, str) and cid.strip():
                return cid.strip()
    return None


def message_has_handleable_content(msg: dict) -> bool:
    """
    True if the message has text and/or any downloadable file attachment.

    Voice notes often arrive with empty msg text and only a file payload.
    Conference-call system messages are handled separately (not a text wake).
    """
    if is_videoconf_message(msg):
        return False
    if (msg.get("msg") or "").strip():
        return True
    return bool(extract_file_candidates(msg))


def compose_wake_user_text(
    caption: str,
    *,
    transcripts: list[str] | None = None,
    stt_errors: list[str] | None = None,
    image_paths: list[str] | None = None,
    image_errors: list[str] | None = None,
    file_entries: list[dict[str, str]] | None = None,
    file_errors: list[str] | None = None,
) -> str:
    """
    Build the single user-facing string fed into the Grok wake prompt.

    caption: original RC msg text (may be empty for pure voice notes).
    transcripts: successful STT strings (one per audio file, chronological).
    stt_errors: human-readable failures (still wake so the operator can reply).
    image_paths: local paths of downloaded image attachments (read with read_file).
    image_errors: download failures for image attachments.
    file_entries: document downloads — dicts with path, name, mime, bytes keys.
    file_errors: typed failures for non-image attachments.
    """
    parts: list[str] = []
    cap = (caption or "").strip()
    if cap:
        parts.append(cap)
    tx_list = list(transcripts or [])
    for i, t in enumerate(tx_list):
        body = (t or "").strip()
        if not body:
            continue
        label = (
            "Voice note transcript"
            if len(tx_list) == 1
            else f"Voice note transcript ({i + 1})"
        )
        parts.append(f"[{label}]\n{body}")
    for err in stt_errors or []:
        e = (err or "").strip()
        if e:
            parts.append(f"[Voice note — could not transcribe: {e}]")
    img_list = [p for p in (image_paths or []) if (p or "").strip()]
    if img_list:
        lines = [
            "[Image attachment(s) — open each path with the read_file tool to view the pixels]"
        ]
        for p in img_list:
            lines.append(f"- {p.strip()}")
        parts.append("\n".join(lines))
    for err in image_errors or []:
        e = (err or "").strip()
        if e:
            parts.append(f"[Image attachment — could not download: {e}]")
    doc_lines: list[str] = []
    for ent in file_entries or []:
        if not isinstance(ent, dict):
            continue
        path = (ent.get("path") or "").strip()
        if not path:
            continue
        name = (ent.get("name") or Path(path).name).strip()
        mime = (ent.get("mime") or "").strip() or "application/octet-stream"
        nbytes = (ent.get("bytes") or "").strip()
        if nbytes:
            doc_lines.append(
                f"- name={name} mime={mime} bytes={nbytes} path={path}"
            )
        else:
            doc_lines.append(f"- name={name} mime={mime} path={path}")
    if doc_lines:
        parts.append(
            "[File attachment(s) — open each path with read_file (or the appropriate tool); "
            "do not claim you cannot view attachments if paths are listed]\n"
            + "\n".join(doc_lines)
        )
    for err in file_errors or []:
        e = (err or "").strip()
        if e:
            parts.append(f"[Attachment error — {e}]")
    return "\n\n".join(parts).strip()


def empty_attachment_wake_stub() -> str:
    """
    User-facing text when a pure attachment wake produced no caption, no STT,
    no image paths, and no document paths (NF-SPEC-05 FR-A10).
    """
    return (
        "(Received a message with an attachment but could not obtain usable content: "
        "no caption, no voice transcript, no image/document path. "
        "Re-send the file, add a caption, or use a voice note.)"
    )


def should_handle_dm_message(
    msg: dict,
    *,
    principal: str = PRINCIPAL,
    last_seen_id: str | None = None,
    processed_ids: list[str] | None = None,
) -> bool:
    """
    Legacy principal-only content filter (FR-A0 base).

    Handleable = non-empty text OR any file attachment (including voice notes
    with empty msg text). Does not enforce @mention tag-to-talk — see
    require_mention_* helpers and should_enqueue_llm_wake.

    Prefer should_enqueue_llm_wake for full wake decisions (includes peer tags).
    """
    mid = msg.get("_id")
    user = (msg.get("u") or {}).get("username")
    if user != principal or not mid:
        return False
    if not message_has_handleable_content(msg):
        return False
    if last_seen_id == mid:
        return False
    if processed_ids and mid in processed_ids:
        return False
    return True


# --- Tag-to-talk (multi-operator: grok + peers) --------------------------------

# Word-boundary @username (same physics as rc_collab.resolve_mention_targets).
_OPERATOR_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9._-]+)\b")

# Bot operator identities (B3/B10 intentional-mention path).
# Keep in sync with rc_multi_round_collab.ALL_OPERATORS (nie/feynman added 2026-07-16).
_ALL_OPERATORS = frozenset({"grok", "hermes", "feynman", "nie", "agy"})

# Activity / intermediate stream chrome (B3).
_ACTIVITY_SHELLS = frozenset({"…", "Thinking...", "...", "Thinking…", "thinking..."})
_STREAM_SHELL_RES = (
    re.compile(r"^\s*\*Thoughts?\*\s*", re.I),
    re.compile(r"^\s*Thinking\b", re.I),
    re.compile(r"^\s*Recovery wake\b", re.I),
    re.compile(r"^\s*PHASE\s*[:=]", re.I),
)
# Final bubble often keeps *Thoughts* above the answer (compose_final_with_thoughts).
_FINAL_COMPOSE_MARKERS = (
    re.compile(r"─{3,}"),  # unicode rule between thoughts and answer
    re.compile(r"(?m)^\s*#{1,3}\s+Shared goal\b", re.I),
    re.compile(r"(?m)^\s*\*\*Shared goal\*\*", re.I),
)
# Optional markdown wrappers around @name: **@nie**, *@nie*, `@nie`, @nie**
_MD_WRAP = r"[\*_`]*"
_ASSIGN_VERB_RE = re.compile(
    rf"@{_MD_WRAP}([A-Za-z0-9._-]+){_MD_WRAP}\s+"
    r"(?:please\s+)?"
    r"(?:dig|own|fix|trace|run|do|check|write|propose|add|test|handle|"
    r"implement|review|pressure-test|pressure_test|take|cover|look|"
    r"investigate|deliver|spec|patch|report|verify|re-?verify|refresh|"
    r"tag|assign|open|close|draft|update|merge)\b",
    re.I,
)
# Numbered task assign: @nie (1) … / **@nie** (1–2) …
_NUMBERED_TASK_RE = re.compile(
    rf"@{_MD_WRAP}([A-Za-z0-9._-]+){_MD_WRAP}\s*\(\s*\d",
    re.I,
)
_COLLAB_RETURN_TEMPLATE_RE = re.compile(
    r"(?<!\w)@([A-Za-z0-9._-]+)\s+collab-return\s+from\s+`?([A-Za-z0-9._-]+)`?",
    re.I,
)


def _env_truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def is_activity_or_stream_shell(text: str | None) -> bool:
    """True for empty / pure activity placeholders (B3)."""
    raw = (text or "").strip()
    return (not raw) or raw in _ACTIVITY_SHELLS


def looks_like_final_composed_reply(text: str | None) -> bool:
    """True when body looks like a finalized activity bubble, not pure stream chrome."""
    raw = text or ""
    return any(cre.search(raw) for cre in _FINAL_COMPOSE_MARKERS)


def looks_like_nonfinal_stream(text: str | None) -> bool:
    """True for intermediate thought-stream chrome, not a final assign (B3).

    Final chat.update bodies often still start with ``*Thoughts*`` above the
    answer (compose_final_with_thoughts). Those must **not** block bot→peer
    wakes when the body also contains an intentional ``@peer`` assign.
    """
    raw = (text or "").strip()
    if not raw or is_activity_or_stream_shell(raw):
        return True
    # Final-shaped body: thoughts + rule + answer, or explicit shared-goal lead.
    if looks_like_final_composed_reply(raw):
        return False
    # Any intentional @op assign means this is (or became) a handoff body.
    if intentional_operator_mentions(raw):
        return False
    head = raw[:240]
    for cre in _STREAM_SHELL_RES:
        if cre.search(head):
            return True
    return False


def intentional_line_start_mentions(text: str | None) -> set[str]:
    """@op at line start, allowing light markdown wrappers (``**@nie**``)."""
    if not text:
        return set()
    found: set[str] = set()
    for line in str(text).splitlines():
        m = re.match(
            rf"^\s*(?:\*{{1,2}}|_{{1,2}}|`)*@([A-Za-z0-9._-]+)\b",
            line,
        )
        if m:
            found.add(m.group(1).lower())
    return found


def intentional_assign_verb_mentions(text: str | None) -> set[str]:
    if not text:
        return set()
    return {m.group(1).lower() for m in _ASSIGN_VERB_RE.finditer(text)}


def intentional_numbered_task_mentions(text: str | None) -> set[str]:
    """@op (1) / **@op** (1–2) multi-peer task blocks (common lead assign shape)."""
    if not text:
        return set()
    return {m.group(1).lower() for m in _NUMBERED_TASK_RE.finditer(text)}


def collab_return_mention_targets(text: str | None) -> set[str]:
    if not text:
        return set()
    return {m.group(1).lower() for m in _COLLAB_RETURN_TEMPLATE_RE.finditer(text)}


def intentional_for_footer_mentions(text: str | None) -> set[str]:
    """Playbook soft footer ``FOR: @op`` — wake-capable handoff to lead/peer."""
    if not text:
        return set()
    found: set[str] = set()
    for line in str(text).splitlines():
        m = re.match(r"^\s*FOR:\s*@([A-Za-z0-9._-]+)\b", line, re.I)
        if m:
            found.add(m.group(1).lower())
    return found


def intentional_operator_mentions(text: str | None) -> set[str]:
    """Mentions that may wake when author is a bot (B10)."""
    return (
        intentional_line_start_mentions(text)
        | intentional_assign_verb_mentions(text)
        | intentional_numbered_task_mentions(text)
        | collab_return_mention_targets(text)
        | intentional_for_footer_mentions(text)
    )


def peer_tag_wake_enabled(env: Mapping[str, str] | None = None) -> bool:
    """
    RC_PEER_TAG_WAKE — when on (default), any author who @mentions this operator
    can enqueue an LLM wake (not principal-only).

    Explicit 0/false/off disables (legacy principal-only content path).
    Explicit 1/true/on enables. Unset → ON (multi-agent collab default).
    Self-posts are always ignored by should_enqueue_llm_wake regardless of this flag.
    """
    e = env if env is not None else os.environ
    if "RC_PEER_TAG_WAKE" in e:
        return _env_truthy(str(e.get("RC_PEER_TAG_WAKE", "")))
    return True


def require_mention_enabled(env: Mapping[str, str] | None = None) -> bool:
    """
    RC_REQUIRE_MENTION — when on, shared-room LLM wakes need @operator.

    Explicit 0/false/off disables. Explicit 1/true/on enables.
    If unset: Hermes backend defaults ON (dual-operator safe); Grok defaults OFF
    for pure-legacy single-bot installs (launchd dual-operator still sets 1).
    """
    e = env if env is not None else os.environ
    if "RC_REQUIRE_MENTION" in e:
        return _env_truthy(str(e.get("RC_REQUIRE_MENTION", "")))
    # Hermes parallel operator: fail closed to tag-to-talk in shared rooms.
    if wake_backend_from_env(e) == "hermes":
        return True
    return False


def require_mention_scope(env: Mapping[str, str] | None = None) -> str:
    """
    RC_REQUIRE_MENTION_SCOPE:

    - channels (default when flag on): require @ in channel/group (c/p); DMs free-wake
    - all: require @ in every room type including 1:1 DMs
    """
    e = env if env is not None else os.environ
    raw = str(e.get("RC_REQUIRE_MENTION_SCOPE", "channels")).strip().lower()
    if raw in {"all", "everywhere", "strict"}:
        return "all"
    return "channels"


def room_requires_operator_mention(
    room_type: str | None,
    *,
    require_mention: bool | None = None,
    scope: str | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """
    True when this room type must include @operator for an LLM wake.

    Unknown / missing room_type under scope=channels → free-wake (legacy-safe).
    """
    on = require_mention_enabled(env) if require_mention is None else bool(require_mention)
    if not on:
        return False
    sc = (scope or require_mention_scope(env)).strip().lower()
    if sc == "all":
        return True
    t = (room_type or "").strip().lower()
    return t in {"c", "p"}


def message_mentions_operator_literal(
    msg: Mapping[str, Any] | None,
    operator: str,
    *,
    text: str | None = None,
) -> bool:
    """
    True if structured mentions[] or @username text targets this operator.

    Case-insensitive; operator username is the RC bot identity (grok, hermes, …).
    Literal path: any mid-sentence @op counts (principal / human tag-to-talk).
    """
    op = (operator or "").strip().lower()
    if not op:
        return False
    payload = msg or {}
    mentions = payload.get("mentions")
    if isinstance(mentions, list):
        for m in mentions:
            if not isinstance(m, dict):
                continue
            uname = (m.get("username") or m.get("name") or "").strip().lower()
            if uname == op:
                return True
    body = text if text is not None else (payload.get("msg") or "")
    if isinstance(body, str) and body:
        for m in _OPERATOR_MENTION_RE.finditer(body):
            if m.group(1).lower() == op:
                return True
    return False


def message_mentions_operator(
    msg: Mapping[str, Any] | None,
    operator: str,
    *,
    text: str | None = None,
    author: str | None = None,
    principal: str | None = None,
) -> bool:
    """
    True if this operator is intentionally targeted for a wake.

    B10: bot authors only wake peers on intentional shapes (line-start @op,
    @op + assign verb, or collab-return template). Principal / other humans
    keep literal any-@op. B3 pure shells are rejected in should_enqueue_llm_wake.
    """
    op = (operator or "").strip().lower()
    if not op:
        return False
    payload = msg or {}
    body = text if text is not None else (payload.get("msg") or "")
    body_s = body if isinstance(body, str) else ""
    author_u = (author or "").strip().lower()
    if not author_u:
        author_u = ((payload.get("u") or {}).get("username") or "").strip().lower()

    if author_u not in _ALL_OPERATORS:
        return message_mentions_operator_literal(msg, op, text=body_s)

    # Bot-authored: intentional text shapes only (structured alone is not enough).
    return op in intentional_operator_mentions(body_s)


def should_enqueue_llm_wake(
    msg: dict,
    *,
    operator: str,
    principal: str = PRINCIPAL,
    last_seen_id: str | None = None,
    processed_ids: list[str] | None = None,
    room_type: str | None = None,
    require_mention: bool | None = None,
    scope: str | None = None,
    env: Mapping[str, str] | None = None,
    text: str | None = None,
) -> bool:
    """
    Full non-collab LLM enqueue predicate.

    - Never wakes on the operator's own posts (loop prevention).
    - Principal: handleable content; DMs free-wake unless scope=all; channels need
      @operator when RC_REQUIRE_MENTION applies. Call *after* control-plane
      short-circuit so !status etc. stay mention-exempt.
    - Anyone else (peer bots, other humans): only when RC_PEER_TAG_WAKE is on
      (default) *and* the message explicitly @mentions this operator.
    - B3: pure activity/thinking shells and bot intermediate stream chrome skip.
    - B10: bot authors require intentional @op (not prose mid-sentence).
    """
    mid = msg.get("_id")
    if not mid:
        return False
    user = ((msg.get("u") or {}).get("username") or "").strip()
    op = (operator or "").strip()
    if not user or not op:
        return False
    if user.lower() == op.lower():
        return False
    if not message_has_handleable_content(msg):
        return False
    if last_seen_id == mid:
        return False
    if processed_ids and mid in processed_ids:
        return False

    body = text if text is not None else (msg.get("msg") or "")
    body_s = (body if isinstance(body, str) else "").strip()
    has_files = bool(msg.get("file") or msg.get("files") or msg.get("attachments"))

    # B3: pure activity / Thinking… placeholders never enqueue.
    if body_s and is_activity_or_stream_shell(body_s) and not has_files:
        return False

    is_principal = user == principal

    if is_principal:
        mentions = message_mentions_operator_literal(msg, operator, text=text)
        if not room_requires_operator_mention(
            room_type,
            require_mention=require_mention,
            scope=scope,
            env=env,
        ):
            return True
        return mentions

    # Peer / any non-principal author
    if not peer_tag_wake_enabled(env):
        return False

    # B3: bot intermediate thought stream must not re-wake peers on chat.update.
    if user.lower() in _ALL_OPERATORS and looks_like_nonfinal_stream(body_s):
        return False

    return message_mentions_operator(
        msg, operator, text=text, author=user, principal=principal
    )


# --- IMP-08 log retention ---

LEDGER_BASENAME = "media-post-ledger.json"


def prune_log_artifacts(
    log_dir: Path | str,
    *,
    now: float | None = None,
    max_age_s: float = 7 * 24 * 3600,
    patterns: tuple[str, ...] = (
        "wake-prompt-*.txt",
        "wake-run-*.log",
        "wake-reply-*.txt",
        "call-prompt-*.txt",
        "call-wake-*.log",
        "call-reply-*.txt",
    ),
    dry_run: bool = False,
    protect_names: frozenset[str] | None = None,
) -> list[Path]:
    """
    Delete aged wake/call artifacts under log_dir. Never deletes ledger by default.

    Returns list of paths that were (or would be) removed.
    """
    root = Path(log_dir)
    protect = protect_names or frozenset({LEDGER_BASENAME, "health.json", "operator-agent.log"})
    ts = time.time() if now is None else now
    removed: list[Path] = []
    if not root.is_dir():
        return removed
    for pat in patterns:
        for path in root.glob(pat):
            if path.name in protect:
                continue
            try:
                age = ts - path.stat().st_mtime
            except OSError:
                continue
            if age < max_age_s:
                continue
            removed.append(path)
            if not dry_run:
                try:
                    path.unlink()
                except OSError:
                    pass
    return removed


# --- IMP-14 per-room state schema ---

STATE_VERSION = 2


def migrate_state_to_v2(state: dict) -> dict:
    """
    Ensure state has version=2 and rooms[rid] entries from legacy flat fields.

    Idempotent. Preserves processed_ids, pending_wakes, grok_sessions, grok_cwds.
    """
    if not isinstance(state, dict):
        return {"version": STATE_VERSION, "rooms": {}, "processed_ids": [], "pending_wakes": []}
    out = dict(state)
    out["version"] = STATE_VERSION
    rooms = dict(out.get("rooms") or {}) if isinstance(out.get("rooms"), dict) else {}
    sessions = out.get("grok_sessions") if isinstance(out.get("grok_sessions"), dict) else {}
    cwds = out.get("grok_cwds") if isinstance(out.get("grok_cwds"), dict) else {}
    all_rids = set(sessions) | set(cwds) | set(rooms)
    legacy_rid = out.get("room_id")
    if isinstance(legacy_rid, str) and legacy_rid.strip():
        all_rids.add(legacy_rid.strip())
    for rid in all_rids:
        if not rid:
            continue
        entry = dict(rooms.get(rid) or {})
        if sessions.get(rid) and not entry.get("session_id"):
            entry["session_id"] = sessions[rid]
        if cwds.get(rid) and not entry.get("cwd"):
            entry["cwd"] = cwds[rid]
        if legacy_rid == rid and out.get("last_seen_id") and not entry.get("last_seen_id"):
            entry["last_seen_id"] = out.get("last_seen_id")
            entry["last_seen_ts"] = out.get("last_seen_ts")
        rooms[rid] = entry
    out["rooms"] = rooms
    if not isinstance(out.get("processed_ids"), list):
        out["processed_ids"] = []
    if not isinstance(out.get("pending_wakes"), list):
        out["pending_wakes"] = []
    return out
