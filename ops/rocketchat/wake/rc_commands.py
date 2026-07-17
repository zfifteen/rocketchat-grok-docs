#!/usr/bin/env python3
"""
Phone control plane (NF-SPEC-03): pure parse, pins, elevation FSM, dispatch.

No Rocket.Chat network I/O here — operator wires replies and wakes.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Env / flags
# ---------------------------------------------------------------------------

DEFAULT_CMD_PREFIXES = ("/", "!")
EFFORT_LEVELS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
)
# max is alias of xhigh for CLI
EFFORT_NORMALIZE = {"max": "xhigh"}

# Built-in skill bang aliases (also overridable via skill_commands.json).
DEFAULT_SKILL_COMMANDS: dict[str, str] = {
    "novel-insight": "novel-insight-engine",
    "novel_insight": "novel-insight-engine",
    "novelinsight": "novel-insight-engine",
}
DEFAULT_SKILL_COMMANDS_PATH = (
    Path(__file__).resolve().parent / "skill_commands.json"
)
DEFAULT_SKILLS_ROOT = Path.home() / ".grok" / "skills"

KNOWN_CMDS = frozenset(
    {
        "help",
        "status",
        "health",
        "new",
        "clear",  # alias → new
        "session",
        "cwd",
        "mode",
        "model",
        "m",  # alias → model
        "effort",
        "goal",
        "admin",
        "cancel",
        "retry",
        "wake",
        "ask",
        "collab",
        "pause",
        "resume",
        # skill bangs (also loaded from skill_commands.json)
        "novel-insight",
        "novel_insight",
        "novelinsight",
    }
)

# Class D/E: never research-wake; short unsupported if we name them
UNSUPPORTED_TUI = frozenset(
    {
        "theme",
        "t",
        "vim-mode",
        "multiline",
        "ml",
        "compact-mode",
        "sessions",
        "home",
        "welcome",
        "quit",
        "exit",
        "copy",
        "export",
        "settings",
        "login",
        "logout",
        "privacy",
        "always-approve",
        "yolo",
        "auto",
        "mcps",
        "plugins",
        "marketplace",
        "skills",
        "hooks",
        "terminal-setup",
        "release-notes",
        "changelog",
        "docs",
        "personas",
        "config-agents",
        "timestamps",
        "btw",
        "feedback",
        "plan",
        "view-plan",
        "show-plan",
        "plan-view",
        "memory",
        "mem",
        "flush",
        "dream",
        "remember",
        "loop",
        "imagine",
        "imagine-video",
        "fork",
        "rewind",
        "compact",
        "context",
        "session-info",
        "rename",
        "title",
        # note: bare `/resume` is NF-SPEC-04 collab resume (KNOWN_CMDS), not TUI
        "usage",
        "import-claude",
    }
)

DEFAULT_CWD_ALLOW_ROOTS = (
    str(Path.home() / "IdeaProjects"),
    str(Path.home() / ".grok" / "agency"),
)


def _env(env: dict[str, str] | None) -> dict[str, str]:
    if env is not None:
        return env
    return dict(os.environ)


def control_plane_enabled(env: dict[str, str] | None = None) -> bool:
    """Master switch RC_CONTROL_PLANE (default on)."""
    raw = (_env(env).get("RC_CONTROL_PLANE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def elevation_enabled(env: dict[str, str] | None = None) -> bool:
    raw = (_env(env).get("RC_ELEVATION") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def cmd_prefixes(env: dict[str, str] | None = None) -> tuple[str, ...]:
    raw = (_env(env).get("RC_CMD_PREFIXES") or "/,!").strip()
    parts = [p for p in re.split(r"[\s,]+", raw) if p]
    return tuple(parts) if parts else DEFAULT_CMD_PREFIXES


def admin_confirm_s(env: dict[str, str] | None = None) -> int:
    try:
        return max(5, int((_env(env).get("RC_ADMIN_CONFIRM_S") or "60").strip()))
    except ValueError:
        return 60


def admin_ttl_s(env: dict[str, str] | None = None) -> int:
    try:
        return max(60, int((_env(env).get("RC_ADMIN_TTL_S") or "900").strip()))
    except ValueError:
        return 900


def cwd_allow_roots(env: dict[str, str] | None = None) -> list[Path]:
    raw = (_env(env).get("RC_CWD_ALLOW_ROOTS") or "").strip()
    if raw:
        roots = [Path(p).expanduser() for p in re.split(r"[:\n,]+", raw) if p.strip()]
    else:
        roots = [Path(p) for p in DEFAULT_CWD_ALLOW_ROOTS]
    return [r.resolve() for r in roots]


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedCommand:
    cmd: str
    args: str
    raw: str
    prefix: str


def strip_leading_mentions(text: str) -> str:
    """
    Drop leading @username tokens so channel habits like
    `@grok !novel-insight …` still parse as control-plane commands.
    """
    s = (text or "").strip()
    while True:
        m = re.match(r"^@([A-Za-z0-9._-]+)\s+", s)
        if not m:
            break
        s = s[m.end() :].lstrip()
    if re.fullmatch(r"@[A-Za-z0-9._-]+", s or ""):
        return ""
    return s


def load_skill_command_map(
    map_path: Path | None = None,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Map bang/slash command token → skill directory name under ~/.grok/skills.

    Merges DEFAULT_SKILL_COMMANDS with skill_commands.json (file wins on conflict).
    Env RC_SKILL_COMMANDS_PATH can override the JSON path.
    """
    out = dict(DEFAULT_SKILL_COMMANDS)
    e = _env(env)
    raw_path = (e.get("RC_SKILL_COMMANDS_PATH") or "").strip()
    path = Path(raw_path).expanduser() if raw_path else (map_path or DEFAULT_SKILL_COMMANDS_PATH)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            data = None
        if isinstance(data, dict):
            for k, v in data.items():
                if not isinstance(k, str) or k.startswith("_"):
                    continue
                key = k.strip().lower().lstrip("!/")
                if not key or not isinstance(v, str):
                    continue
                skill = v.strip()
                if skill:
                    out[key] = skill
    return out


def skill_path_for(skill_name: str, *, skills_root: Path | None = None) -> Path:
    root = skills_root or DEFAULT_SKILLS_ROOT
    return (root / skill_name / "SKILL.md").expanduser()


def build_skill_wake_text(
    skill_name: str,
    args: str = "",
    *,
    skill_md: Path | None = None,
) -> str:
    """Synthetic principal text for a skill bang → research wake."""
    path = skill_md or skill_path_for(skill_name)
    focus = (args or "").strip() or (
        "(no extra args — use this room's project cwd, repository, and "
        "conversation context as the domain for the insight.)"
    )
    return (
        f"[RC skill command → {skill_name}]\n\n"
        f"You MUST invoke and follow the skill `{skill_name}` for this turn.\n"
        f"1. Open `{path}` with the read_file tool (or apply it if already loaded).\n"
        f"2. Execute the full skill protocol end-to-end — do not skip phases.\n"
        f"3. Write only the skill's final user-facing output to the reply file "
        f"(markdown ok, chat length).\n\n"
        f"Focus / context from principal:\n{focus}"
    )


def parse_command(
    text: str,
    *,
    prefixes: tuple[str, ...] | None = None,
    env: dict[str, str] | None = None,
    strip_mentions: bool = True,
) -> ParsedCommand | None:
    """
    Parse a principal slash command. Returns None if not command-shaped.

    Match: optional leading @mentions, optional whitespace, prefix, cmd token,
    optional args. Leading @mentions are stripped by default so channel
    `@grok !cmd` works like bare `!cmd`.
    """
    s = (text or "").strip()
    if strip_mentions:
        s = strip_leading_mentions(s)
    if not s:
        return None
    prefs = prefixes if prefixes is not None else cmd_prefixes(env)
    for pref in sorted(prefs, key=len, reverse=True):
        if s.startswith(pref) and len(s) > len(pref):
            rest = s[len(pref) :].strip()
            if not rest:
                return ParsedCommand(cmd="", args="", raw=s, prefix=pref)
            parts = rest.split(None, 1)
            cmd = parts[0].lower()
            # strip zero-width etc.
            cmd = re.sub(r"[\u200b-\u200d\ufeff]", "", cmd)
            args = parts[1].strip() if len(parts) > 1 else ""
            # aliases
            if cmd == "clear":
                cmd = "new"
            if cmd == "m":
                cmd = "model"
            return ParsedCommand(cmd=cmd, args=args, raw=s, prefix=pref)
    return None


def is_confirm_reply(text: str) -> str | None:
    """Return 'yes' or 'no' if text is exactly a confirm token; else None."""
    t = (text or "").strip().lower()
    if t in ("yes", "y"):
        return "yes"
    if t in ("no", "n"):
        return "no"
    return None


# ---------------------------------------------------------------------------
# Room pins (state dict)
# ---------------------------------------------------------------------------


def get_room_model(state: dict, room_id: str) -> str | None:
    models = state.get("room_models") or {}
    if isinstance(models, dict):
        v = models.get(room_id)
        if v:
            return str(v)
    import os
    return os.environ.get("RC_WAKE_MODEL")


def set_room_model(state: dict, room_id: str, model: str | None) -> dict:
    models = dict(state.get("room_models") or {})
    if model:
        models[room_id] = model
    else:
        models.pop(room_id, None)
    state["room_models"] = models
    return state


def get_room_effort(state: dict, room_id: str) -> str | None:
    efforts = state.get("room_effort") or {}
    if isinstance(efforts, dict):
        v = efforts.get(room_id)
        return str(v) if v else None
    return None


def set_room_effort(state: dict, room_id: str, effort: str | None) -> dict:
    efforts = dict(state.get("room_effort") or {})
    if effort:
        efforts[room_id] = effort
    else:
        efforts.pop(room_id, None)
    state["room_effort"] = efforts
    return state


def get_room_goal(state: dict, room_id: str) -> dict | None:
    goals = state.get("room_goals") or {}
    if isinstance(goals, dict):
        g = goals.get(room_id)
        return g if isinstance(g, dict) else None
    return None


def set_room_goal(state: dict, room_id: str, goal: dict | None) -> dict:
    goals = dict(state.get("room_goals") or {})
    if goal:
        goals[room_id] = goal
    else:
        goals.pop(room_id, None)
    state["room_goals"] = goals
    return state


def goal_prompt_block(state: dict, room_id: str) -> str:
    """Injectable preamble for goal-aware wakes. Empty if no active goal."""
    g = get_room_goal(state, room_id)
    if not g:
        return ""
    status = str(g.get("status") or "").lower()
    if status not in ("active", "paused"):
        return ""
    obj = str(g.get("objective") or "").strip()
    if not obj:
        return ""
    lines = [
        "### Active room goal (operator pin)",
        f"Status: {status}",
        f"Objective: {obj}",
        "Work toward this objective unless the principal redirects. "
        "Report progress in the reply when useful.",
    ]
    if g.get("last_progress"):
        lines.append(f"Last progress note: {g['last_progress']}")
    return "\n".join(lines)


def get_last_content(state: dict, room_id: str) -> str | None:
    buf = state.get("last_content_by_room") or {}
    if isinstance(buf, dict):
        entry = buf.get(room_id)
        if isinstance(entry, dict):
            t = entry.get("text")
            return str(t) if t else None
        if isinstance(entry, str) and entry:
            return entry
    return None


def set_last_content(state: dict, room_id: str, text: str, mid: str = "") -> dict:
    buf = dict(state.get("last_content_by_room") or {})
    # Cap stored text
    clipped = (text or "")[:8000]
    buf[room_id] = {
        "text": clipped,
        "mid": mid,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    state["last_content_by_room"] = buf
    return state


def get_room_wake_pid(state: dict, room_id: str) -> int | None:
    pids = state.get("room_wake_pids") or {}
    if isinstance(pids, dict) and room_id in pids:
        try:
            return int(pids[room_id])
        except (TypeError, ValueError):
            return None
    return None


def set_room_wake_pid(state: dict, room_id: str, pid: int | None) -> dict:
    pids = dict(state.get("room_wake_pids") or {})
    if pid is not None and pid > 0:
        pids[room_id] = int(pid)
    else:
        pids.pop(room_id, None)
    state["room_wake_pids"] = pids
    return state


# ---------------------------------------------------------------------------
# CWD allowlist
# ---------------------------------------------------------------------------


def cwd_pin_allowed(
    path: str,
    *,
    env: dict[str, str] | None = None,
    roots: list[Path] | None = None,
) -> tuple[bool, str, str | None]:
    """
    Validate /cwd pin path. Returns (ok, message, resolved_str_or_none).
    """
    raw = (path or "").strip()
    if not raw:
        return False, "Usage: /cwd pin <path>", None
    try:
        p = Path(raw).expanduser()
        # resolve without requiring existence first for message; then check exists
        resolved = p.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        return False, f"Invalid path: {e}", None
    allow = roots if roots is not None else cwd_allow_roots(env)
    try:
        ok_under = any(
            resolved == root or root in resolved.parents for root in allow
        )
    except Exception:
        ok_under = False
    if not ok_under:
        return (
            False,
            f"Path not under allowlisted roots ({', '.join(str(r) for r in allow)}).",
            None,
        )
    if not resolved.is_dir():
        return False, f"Not an existing directory: {resolved}", None
    # Reject if realpath escapes (symlink)
    try:
        real = resolved.resolve(strict=True)
        if not any(real == root or root in real.parents for root in allow):
            return False, "Resolved path escapes allowlist (symlink?).", None
        return True, f"Pinned cwd: {real}", str(real)
    except OSError:
        return False, f"Cannot resolve directory: {resolved}", None


# ---------------------------------------------------------------------------
# Elevation FSM
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_pending_confirm(state: dict, room_id: str) -> dict | None:
    pending = state.get("pending_confirm") or {}
    if isinstance(pending, dict):
        p = pending.get(room_id)
        return p if isinstance(p, dict) else None
    return None


def set_pending_confirm(state: dict, room_id: str, pending: dict | None) -> dict:
    d = dict(state.get("pending_confirm") or {})
    if pending:
        d[room_id] = pending
    else:
        d.pop(room_id, None)
    state["pending_confirm"] = d
    return state


def get_room_elevation(state: dict, room_id: str) -> dict | None:
    elev = state.get("room_elevation") or {}
    if isinstance(elev, dict):
        e = elev.get(room_id)
        return e if isinstance(e, dict) else None
    return None


def set_room_elevation(state: dict, room_id: str, elev: dict | None) -> dict:
    d = dict(state.get("room_elevation") or {})
    if elev:
        d[room_id] = elev
    else:
        d.pop(room_id, None)
    state["room_elevation"] = d
    return state


def clear_expired_pending(state: dict, room_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    p = get_pending_confirm(state, room_id)
    if not p:
        return state
    exp = _parse_iso(p.get("expires_at"))
    if exp and now > exp:
        set_pending_confirm(state, room_id, None)
        _audit(state, room_id, "elevation_confirm_timeout", p.get("kind"))
    return state


def clear_expired_elevation(state: dict, room_id: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    e = get_room_elevation(state, room_id)
    if not e:
        return state
    exp = _parse_iso(e.get("expires_at"))
    if exp and now > exp:
        set_room_elevation(state, room_id, None)
        _audit(state, room_id, "elevation_expire", e.get("mode"))
    return state


def arm_pending_confirm(
    state: dict,
    room_id: str,
    kind: str,
    *,
    confirm_s: int = 60,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    from datetime import timedelta

    expires = now + timedelta(seconds=confirm_s)
    set_pending_confirm(
        state,
        room_id,
        {
            "kind": kind,  # admin_once | admin_ttl
            "expires_at": expires.isoformat(),
            "armed_at": now.isoformat(),
        },
    )
    _audit(state, room_id, "elevation_pending", kind)
    return state


def confirm_yes(
    state: dict,
    room_id: str,
    *,
    ttl_s: int = 900,
    now: datetime | None = None,
) -> tuple[dict, str]:
    """Consume pending confirm; arm elevation. Returns (state, message)."""
    now = now or datetime.now(timezone.utc)
    clear_expired_pending(state, room_id, now)
    p = get_pending_confirm(state, room_id)
    if not p:
        return state, "No pending elevation to confirm."
    kind = str(p.get("kind") or "")
    set_pending_confirm(state, room_id, None)
    from datetime import timedelta

    if kind == "admin_once":
        set_room_elevation(
            state,
            room_id,
            {
                "mode": "admin",
                "uses_remaining": 1,
                "expires_at": None,
                "armed_at": now.isoformat(),
                "armed_by": "principal",
                "kind": "once",
            },
        )
        _audit(state, room_id, "elevation_grant", "once")
        return state, "Admin armed for **next wake only** in this room. Send your task."
    if kind == "admin_ttl":
        exp = now + timedelta(seconds=ttl_s)
        set_room_elevation(
            state,
            room_id,
            {
                "mode": "admin",
                "uses_remaining": None,
                "expires_at": exp.isoformat(),
                "armed_at": now.isoformat(),
                "armed_by": "principal",
                "kind": "ttl",
            },
        )
        _audit(state, room_id, "elevation_grant", f"ttl={ttl_s}s")
        return (
            state,
            f"Admin armed for **{ttl_s}s** in this room (until {exp.isoformat()}). "
            "Send `/admin off` to clear early.",
        )
    return state, f"Unknown pending kind {kind!r}; cleared."


def confirm_no(state: dict, room_id: str) -> tuple[dict, str]:
    p = get_pending_confirm(state, room_id)
    if not p:
        return state, "No pending elevation."
    set_pending_confirm(state, room_id, None)
    _audit(state, room_id, "elevation_deny", p.get("kind"))
    return state, "Elevation cancelled. Mode stays restricted."


def effective_approval_for_room(
    state: dict,
    room_id: str,
    base_mode: str,
    *,
    now: datetime | None = None,
) -> tuple[str, bool]:
    """
    Returns (effective_mode, should_consume_once_after_wake).

    Call consume_once_elevation after the wake if should_consume is True.
    """
    now = now or datetime.now(timezone.utc)
    clear_expired_elevation(state, room_id, now)
    e = get_room_elevation(state, room_id)
    if not e:
        return base_mode, False
    if str(e.get("mode") or "").lower() != "admin":
        return base_mode, False
    uses = e.get("uses_remaining")
    if uses is not None:
        try:
            if int(uses) <= 0:
                set_room_elevation(state, room_id, None)
                return base_mode, False
        except (TypeError, ValueError):
            pass
        return "admin", True  # once
    # TTL
    return "admin", False


def consume_once_elevation(state: dict, room_id: str) -> dict:
    e = get_room_elevation(state, room_id)
    if not e:
        return state
    uses = e.get("uses_remaining")
    if uses is None:
        return state
    try:
        n = int(uses) - 1
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        set_room_elevation(state, room_id, None)
        _audit(state, room_id, "elevation_consume", "once")
    else:
        e = dict(e)
        e["uses_remaining"] = n
        set_room_elevation(state, room_id, e)
    return state


def _audit(state: dict, room_id: str, event: str, detail: Any = None) -> None:
    log = list(state.get("elevation_audit") or [])
    log.append(
        {
            "ts": _now_iso(),
            "room_id": room_id,
            "event": event,
            "detail": detail,
        }
    )
    state["elevation_audit"] = log[-200:]


def elevation_summary(state: dict, room_id: str) -> str:
    clear_expired_pending(state, room_id)
    clear_expired_elevation(state, room_id)
    p = get_pending_confirm(state, room_id)
    e = get_room_elevation(state, room_id)
    if p:
        return f"pending confirm ({p.get('kind')}) until {p.get('expires_at')}"
    if e:
        if e.get("uses_remaining") is not None:
            return f"admin once (uses_remaining={e.get('uses_remaining')})"
        return f"admin ttl until {e.get('expires_at')}"
    return "none"


# ---------------------------------------------------------------------------
# Help / status text
# ---------------------------------------------------------------------------

# Prefer `!` in RC clients: leading `/` is intercepted by Rocket.Chat's own
# slash-command UI (rocket.cat "No such command") and never reaches the room.
# Both `/` and `!` parse the same (RC_CMD_PREFIXES default "/,!").
HELP_LINES = [
    "`!help [topic]` — list commands or short usage",
    "`!status` — mission card (health, session, model, effort, goal, mode)",
    "`!health` — operator / RC health summary",
    "`!new` — clear room Grok session pin (fresh chat next wake)",
    "`!session show|reset` — show session id or reset (alias `!new`)",
    "`!cwd` · `!cwd pin <path>` · `!cwd clear` — project directory pin",
    "`!mode` — approval / elevation mode (not LLM model)",
    "`!model [id|clear]` — pin LLM model for next wakes (`-m`)",
    "`!effort [level|clear]` — pin reasoning effort (`low`…`xhigh`)",
    "`!goal [objective|status|pause|resume|clear]` — room goal pin",
    "`!admin once|on|off` — elevation (confirm with `yes`/`no`)",
    "`!cancel` — stop active wake in this room if owned",
    "`!retry` — re-run last non-command content",
    "`!wake <text>` · `!ask <text>` — explicit content wake",
    "`!novel-insight [focus]` — run novel-insight-engine skill on this room/project",
    "`!collab status|pause|resume` — AGY dual-peer auto-handoff (collab rooms)",
    "`!pause` · `!resume` — aliases for `!collab pause|resume`",
]


def help_text(topic: str = "") -> str:
    t = (topic or "").strip().lower()
    if not t:
        return (
            "**Phone control plane** (principal only)\n\n"
            "**Use `!` prefix in Rocket.Chat** (e.g. `!goal …`). "
            "Messages starting with `/` are captured by Rocket.Chat’s own "
            "slash commands (rocket.cat) and never reach the operator.\n\n"
            + "\n".join(f"- {line}" for line in HELP_LINES)
            + "\n\nUnknown `!…` / `/…` never starts a research wake. "
            "TUI-only commands (e.g. `!theme`) are unsupported on phone."
        )
    topics = {
        "admin": (
            "`!admin once` — confirm, then next content wake is admin once.\n"
            "`!admin on` — confirm, then TTL admin (default 15m).\n"
            "`!admin off` — clear elevation.\n"
            "Reply `yes` or `no` within the confirm window."
        ),
        "model": (
            "`!model` — show pin.\n"
            "`!model <id>` — pin model for subsequent wakes (`--model`).\n"
            "`!model clear` — drop pin.\n"
            "Alias: `!m`. Not the same as `!mode` (approval)."
        ),
        "effort": (
            "`!effort` — show pin.\n"
            "`!effort <level>` — none|minimal|low|medium|high|xhigh|max.\n"
            "`!effort clear` — drop pin."
        ),
        "goal": (
            "`!goal <objective>` — set active room goal.\n"
            "`!goal status|pause|resume|clear` — manage pin.\n"
            "Content wakes inject the goal into the prompt while active.\n"
            "In Rocket.Chat type `!goal` not `/goal` (RC steals leading `/`)."
        ),
        "cwd": (
            "`!cwd` — show resolved cwd.\n"
            "`!cwd pin <path>` — pin under IdeaProjects or ~/.grok/agency.\n"
            "`!cwd clear` — drop pin."
        ),
        "new": "`!new` or `!session reset` clears the room session pin. "
        "Model/effort/goal pins are kept by default.",
        "status": "`!status` — room mission card + operator health.",
        "help": help_text(""),
        "mode": "`!mode` shows **approval** (restricted/admin) and elevation. "
        "For LLM model use `!model`.",
        "cancel": "`!cancel` sends SIGTERM to the room's owned wake child PID if any.",
        "retry": "`!retry` re-enqueues the last retained non-command principal text.",
        "novel-insight": (
            "`!novel-insight [focus]` — invoke the **novel-insight-engine** skill "
            "on this room's project and conversation.\n"
            "Mention-exempt (no @grok required). Optional focus args after the command.\n"
            "Also: `!novel_insight`, `!novelinsight`.\n"
            "Skill map: `wake/skill_commands.json`."
        ),
        "skill": (
            "Skill bangs map command tokens → `~/.grok/skills/<name>/SKILL.md`.\n"
            "Configured in `ops/rocketchat/wake/skill_commands.json`.\n"
            "Example: `!novel-insight residual curvature under fixed τ`."
        ),
    }
    if t in topics:
        return topics[t]
    return f"Unknown topic `{t}`.\n\n" + help_text("")


def format_status_card(
    *,
    room_name: str,
    room_id: str,
    operator_line: str,
    approval_line: str,
    session_id: str | None,
    cwd: str | None,
    cwd_reason: str,
    model: str | None,
    effort: str | None,
    goal: dict | None,
    last_wake_at: str | None = None,
    last_wake_rc: Any = None,
    last_stop_reason: str | None = None,
    queue_line: str = "unknown",
) -> str:
    gline = "none"
    if goal:
        obj = str(goal.get("objective") or "")[:80]
        gline = f"{goal.get('status') or '?'} — {obj}"
    lines = [
        f"## Mission control — {room_name or room_id}",
        f"- operator: {operator_line}",
        f"- approval: {approval_line}",
        f"- model: {model or 'default'}"
        + (" (pinned)" if model else ""),
        f"- effort: {effort or 'default'}"
        + (" (pinned)" if effort else ""),
        f"- goal: {gline}",
        f"- session: {session_id or 'none'}",
        f"- cwd: {cwd or '(unresolved)'} ({cwd_reason})",
        f"- last wake: {last_wake_at or 'n/a'} rc={last_wake_rc if last_wake_rc is not None else 'n/a'}"
        + (f" stopReason={last_stop_reason}" if last_stop_reason else ""),
        f"- queue: {queue_line}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dispatch result
# ---------------------------------------------------------------------------


@dataclass
class CommandResult:
    """Outcome of handling a control-plane command."""

    reply: str
    # If set, operator should enqueue a content wake with this text (not CLI research via freeform)
    wake_text: str | None = None
    # mark principal message processed (True for pure commands)
    mark_processed: bool = True
    # audit / log line for operator log
    log_line: str = ""
    # optional: clear session pin already done in state
    ok: bool = True
    # If set, operator should SIGTERM this owned wake PID (after ownership check)
    cancel_pid: int | None = None


def dispatch_command(
    parsed: ParsedCommand,
    *,
    state: dict,
    room_id: str,
    room_name: str = "",
    room_type: str | None = None,
    env: dict[str, str] | None = None,
    health_reader: Callable[[], str] | None = None,
    base_approval: str = "restricted",
    session_id: str | None = None,
    cwd: str | None = None,
    cwd_reason: str = "",
    now: datetime | None = None,
) -> CommandResult:
    """
    Mutates state for pin/elevation commands. Pure of RC network.
    """
    now = now or datetime.now(timezone.utc)
    env = _env(env)
    cmd = parsed.cmd
    args = (parsed.args or "").strip()

    if not cmd:
        return CommandResult(
            reply="Empty command. Try `/help`.",
            log_line="cmd empty",
            ok=False,
        )

    # Skill bangs (e.g. !novel-insight) → research wake with skill protocol
    skill_map = load_skill_command_map(env=env)
    if cmd in skill_map:
        skill_name = skill_map[cmd]
        skill_md = skill_path_for(skill_name)
        if not skill_md.is_file():
            return CommandResult(
                reply=(
                    f"Skill `{skill_name}` mapped from `!{cmd}` but missing file:\n"
                    f"`{skill_md}`\n"
                    "Fix the skill install or `skill_commands.json`."
                ),
                log_line=f"cmd skill missing={cmd}->{skill_name}",
                ok=False,
            )
        wake_text = build_skill_wake_text(skill_name, args, skill_md=skill_md)
        # No separate ack bubble — enqueued wake owns the single activity bubble.
        return CommandResult(
            reply="",
            wake_text=wake_text,
            mark_processed=True,
            log_line=f"cmd skill={cmd}->{skill_name}",
        )

    # Class D/E unsupported
    if cmd in UNSUPPORTED_TUI or cmd not in KNOWN_CMDS:
        if cmd in UNSUPPORTED_TUI:
            return CommandResult(
                reply=(
                    f"`/{cmd}` is TUI/account-only or unsupported on the phone control plane.\n"
                    "Try `/help` for supported commands."
                ),
                log_line=f"cmd unsupported tui={cmd}",
                ok=False,
            )
        return CommandResult(
            reply=f"Unknown command `/{cmd}`. Try `/help`.",
            log_line=f"cmd unknown={cmd}",
            ok=False,
        )

    if cmd == "help":
        return CommandResult(reply=help_text(args), log_line="cmd help")

    if cmd == "health":
        body = health_reader() if health_reader else "health: (no reader)"
        return CommandResult(reply=body, log_line="cmd health")

    if cmd == "status":
        clear_expired_elevation(state, room_id, now)
        elev = elevation_summary(state, room_id)
        card = format_status_card(
            room_name=room_name or room_id,
            room_id=room_id,
            operator_line=(
                health_reader() if health_reader else "see /health"
            ),
            approval_line=f"{base_approval} (elevation: {elev})",
            session_id=session_id,
            cwd=cwd,
            cwd_reason=cwd_reason or "n/a",
            model=get_room_model(state, room_id),
            effort=get_room_effort(state, room_id),
            goal=get_room_goal(state, room_id),
            last_wake_at=state.get("last_wake_at"),
            last_wake_rc=state.get("last_wake_rc"),
            last_stop_reason=state.get("last_stop_reason"),
            queue_line=f"{len(state.get('pending_wakes') or [])} pending",
        )
        # NF-SPEC-04: append collab block when room has collab state
        try:
            from rc_collab import get_collab_room_state

            c = get_collab_room_state(state, room_id)
            if (
                c.get("conversation_id")
                or c.get("total_hops")
                or c.get("paused_reason")
                or not c.get("auto_handoff", True)
            ):
                card += (
                    f"\n- collab: auto_handoff={c.get('auto_handoff')} "
                    f"paused={c.get('paused_reason') or 'none'} "
                    f"hops={c.get('hop_count_epoch')}/{c.get('hop_budget_epoch')} "
                    f"agy_uuid={(c.get('conversation_id') or 'none')[:8]}"
                )
        except Exception:
            pass
        return CommandResult(reply=card, log_line="cmd status")

    if cmd == "mode":
        clear_expired_elevation(state, room_id, now)
        elev = elevation_summary(state, room_id)
        return CommandResult(
            reply=(
                f"**Approval mode:** {base_approval}\n"
                f"**Elevation:** {elev}\n"
                f"(LLM model pin is `/model`, currently: "
                f"{get_room_model(state, room_id) or 'default'})"
            ),
            log_line="cmd mode",
        )

    if cmd in ("new",) or (cmd == "session" and args.lower().startswith("reset")):
        from wake_lib import set_room_session_id

        set_room_session_id(state, room_id, None)
        return CommandResult(
            reply="Session pin cleared for this room. Next message starts a fresh Grok session.",
            log_line="cmd new",
        )

    if cmd == "session":
        sub = args.split(None, 1)[0].lower() if args else "show"
        if sub == "show" or not args:
            return CommandResult(
                reply=f"Session pin: {session_id or 'none'}",
                log_line="cmd session show",
            )
        return CommandResult(
            reply="Usage: `/session show` or `/session reset`",
            log_line="cmd session bad",
            ok=False,
        )

    if cmd == "cwd":
        if not args:
            return CommandResult(
                reply=f"cwd: {cwd or '(none)'} ({cwd_reason or 'n/a'})",
                log_line="cmd cwd show",
            )
        parts = args.split(None, 1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if sub == "clear":
            from wake_lib import set_room_cwd

            set_room_cwd(state, room_id, None)
            return CommandResult(reply="cwd pin cleared.", log_line="cmd cwd clear")
        if sub == "pin":
            from wake_lib import set_room_cwd

            ok, msg, resolved = cwd_pin_allowed(rest, env=env)
            if not ok or not resolved:
                return CommandResult(reply=msg, log_line="cmd cwd pin reject", ok=False)
            set_room_cwd(state, room_id, resolved)
            return CommandResult(reply=msg, log_line="cmd cwd pin")
        return CommandResult(
            reply="Usage: `/cwd` | `/cwd pin <path>` | `/cwd clear`",
            ok=False,
            log_line="cmd cwd bad",
        )

    if cmd == "model":
        if not args:
            return CommandResult(
                reply=f"Model pin: {get_room_model(state, room_id) or 'default'}",
                log_line="cmd model show",
            )
        if args.lower() == "clear":
            set_room_model(state, room_id, None)
            return CommandResult(reply="Model pin cleared.", log_line="cmd model clear")
        # First token is model id; rest ignored for v1 (effort is separate cmd)
        model_id = args.split(None, 1)[0].strip()
        if not model_id or len(model_id) > 120:
            return CommandResult(reply="Invalid model id.", ok=False, log_line="cmd model bad")
        set_room_model(state, room_id, model_id)
        return CommandResult(
            reply=f"Model pinned: `{model_id}` (applies to next wakes in this room).",
            log_line=f"cmd model set={model_id}",
        )

    if cmd == "effort":
        if not args:
            return CommandResult(
                reply=f"Effort pin: {get_room_effort(state, room_id) or 'default'}",
                log_line="cmd effort show",
            )
        if args.lower() == "clear":
            set_room_effort(state, room_id, None)
            return CommandResult(reply="Effort pin cleared.", log_line="cmd effort clear")
        level = args.split(None, 1)[0].strip().lower()
        if level not in EFFORT_LEVELS:
            return CommandResult(
                reply=(
                    f"Invalid effort `{level}`. "
                    f"Use: {', '.join(sorted(EFFORT_LEVELS))}."
                ),
                ok=False,
                log_line="cmd effort bad",
            )
        level = EFFORT_NORMALIZE.get(level, level)
        set_room_effort(state, room_id, level)
        return CommandResult(
            reply=f"Effort pinned: `{level}` (next wakes).",
            log_line=f"cmd effort set={level}",
        )

    if cmd == "goal":
        if not args:
            g = get_room_goal(state, room_id)
            if not g:
                return CommandResult(reply="Goal: none", log_line="cmd goal show")
            return CommandResult(
                reply=(
                    f"Goal status: {g.get('status')}\n"
                    f"Objective: {g.get('objective')}\n"
                    f"Updated: {g.get('updated_at')}"
                ),
                log_line="cmd goal show",
            )
        sub = args.split(None, 1)
        head = sub[0].lower()
        if head == "clear":
            set_room_goal(state, room_id, None)
            return CommandResult(reply="Goal cleared.", log_line="cmd goal clear")
        if head == "status":
            return dispatch_command(
                ParsedCommand(cmd="goal", args="", raw=parsed.raw, prefix=parsed.prefix),
                state=state,
                room_id=room_id,
                room_name=room_name,
                room_type=room_type,
                env=env,
                health_reader=health_reader,
                base_approval=base_approval,
                session_id=session_id,
                cwd=cwd,
                cwd_reason=cwd_reason,
                now=now,
            )
        if head == "pause":
            g = get_room_goal(state, room_id)
            if not g:
                return CommandResult(reply="No goal to pause.", ok=False, log_line="cmd goal pause empty")
            g = dict(g)
            g["status"] = "paused"
            g["updated_at"] = now.isoformat()
            set_room_goal(state, room_id, g)
            return CommandResult(reply="Goal paused (still shown on /status).", log_line="cmd goal pause")
        if head == "resume":
            g = get_room_goal(state, room_id)
            if not g:
                return CommandResult(reply="No goal to resume.", ok=False, log_line="cmd goal resume empty")
            g = dict(g)
            g["status"] = "active"
            g["updated_at"] = now.isoformat()
            set_room_goal(state, room_id, g)
            return CommandResult(reply="Goal resumed (active).", log_line="cmd goal resume")
        # treat full args as objective
        set_room_goal(
            state,
            room_id,
            {
                "objective": args,
                "status": "active",
                "updated_at": now.isoformat(),
                "last_progress": None,
            },
        )
        return CommandResult(
            reply=f"Goal set (active):\n{args}\n\nNext content wakes in this room are goal-aware.",
            log_line="cmd goal set",
        )

    if cmd == "admin":
        if not elevation_enabled(env):
            return CommandResult(
                reply="Elevation disabled (`RC_ELEVATION=0`). Other commands still work; try `/help`.",
                ok=False,
                log_line="cmd admin elevation off",
            )
        sub = (args.split(None, 1)[0].lower() if args else "")
        if sub == "off":
            set_room_elevation(state, room_id, None)
            set_pending_confirm(state, room_id, None)
            _audit(state, room_id, "elevation_off", None)
            return CommandResult(reply="Elevation cleared.", log_line="cmd admin off")
        if sub == "once":
            arm_pending_confirm(
                state, room_id, "admin_once", confirm_s=admin_confirm_s(env), now=now
            )
            return CommandResult(
                reply=(
                    "Confirm admin for **next wake only** in this room?\n"
                    f"Reply `yes` or `no` within {admin_confirm_s(env)}s."
                ),
                log_line="cmd admin once pending",
            )
        if sub == "on":
            arm_pending_confirm(
                state, room_id, "admin_ttl", confirm_s=admin_confirm_s(env), now=now
            )
            return CommandResult(
                reply=(
                    f"Confirm admin for **{admin_ttl_s(env)}s** in this room?\n"
                    f"Reply `yes` or `no` within {admin_confirm_s(env)}s."
                ),
                log_line="cmd admin on pending",
            )
        return CommandResult(
            reply="Usage: `/admin once` | `/admin on` | `/admin off`",
            ok=False,
            log_line="cmd admin bad",
        )

    if cmd == "cancel":
        pid = get_room_wake_pid(state, room_id)
        if not pid:
            return CommandResult(
                reply="No active wake PID recorded for this room.",
                log_line="cmd cancel none",
            )
        return CommandResult(
            reply=f"Attempting cancel of owned wake pid={pid}…",
            log_line=f"cmd cancel pid={pid}",
            cancel_pid=pid,
        )

    if cmd == "retry":
        last = get_last_content(state, room_id)
        if not last:
            return CommandResult(
                reply="No retained content to retry in this room.",
                ok=False,
                log_line="cmd retry empty",
            )
        return CommandResult(
            reply="Re-running last content…",
            wake_text=last,
            mark_processed=True,
            log_line="cmd retry",
        )

    if cmd in ("wake", "ask"):
        if not args:
            return CommandResult(
                reply=f"Usage: `/{cmd} <text>`",
                ok=False,
                log_line=f"cmd {cmd} empty",
            )
        return CommandResult(
            reply=f"Waking on: {args[:200]}{'…' if len(args) > 200 else ''}",
            wake_text=args,
            mark_processed=True,
            log_line=f"cmd {cmd}",
        )

    # NF-SPEC-04 collab control (also /pause /resume aliases)
    if cmd in ("collab", "pause", "resume"):
        try:
            from rc_collab import (
                get_collab_room_state,
                pause_auto_handoff,
                resume_auto_handoff,
                ensure_collab_budget,
            )
        except ImportError:
            return CommandResult(
                reply="Collab module unavailable.",
                ok=False,
                log_line="cmd collab import fail",
            )
        ensure_collab_budget(state, room_id)
        sub = args.strip().lower() if cmd == "collab" else cmd
        if cmd == "collab" and not sub:
            sub = "status"
        if sub in ("status", "show", ""):
            c = get_collab_room_state(state, room_id)
            return CommandResult(
                reply=(
                    f"**Collab** room `{room_name or room_id}`\n"
                    f"- auto_handoff: {c.get('auto_handoff')}\n"
                    f"- paused_reason: {c.get('paused_reason') or 'none'}\n"
                    f"- hops epoch: {c.get('hop_count_epoch')}/{c.get('hop_budget_epoch')} "
                    f"(epoch {c.get('epoch')})\n"
                    f"- total_hops: {c.get('total_hops')}\n"
                    f"- agy.conversation_id: {c.get('conversation_id') or 'none'}\n"
                    f"- last_speaker: {c.get('last_speaker') or 'n/a'}"
                ),
                log_line="cmd collab status",
            )
        if sub == "pause":
            pause_auto_handoff(state, room_id, "principal")
            return CommandResult(
                reply="Collab auto-handoff **paused**. Sessions retained. `/resume` to restore.",
                log_line="cmd collab pause",
            )
        if sub == "resume":
            resume_auto_handoff(state, room_id, reset_epoch_hops=False)
            return CommandResult(
                reply="Collab auto-handoff **resumed**.",
                log_line="cmd collab resume",
            )
        return CommandResult(
            reply="Usage: `/collab status|pause|resume` (or `/pause` / `/resume`)",
            ok=False,
            log_line="cmd collab bad",
        )

    return CommandResult(
        reply=f"Unhandled command `/{cmd}`. Try `/help`.",
        ok=False,
        log_line=f"cmd unhandled={cmd}",
    )
