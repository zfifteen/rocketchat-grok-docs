#!/usr/bin/env python3
"""
NF-SPEC-04 — AGY dual-peer Rocket.Chat collab (pure helpers).

Tag-to-talk mention routing, author allowlist, self-wake filter, soft hop
budget / pause FSM, durable collab room state, and local `agy` CLI contracts.

No network I/O. Unit-testable without Rocket.Chat or subprocesses.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

# --- Constants ----------------------------------------------------------------

PRINCIPAL = "principal"
GROK_USER = "grok"
AGY_USER = "agy"

DEFAULT_AGY_USER = "agy"
DEFAULT_HOP_BUDGET_EPOCH = 100
DEFAULT_CHECKPOINT_EVERY = 15
DEFAULT_PRINT_TIMEOUT = "10m"
DEFAULT_AGY_WAKE_TIMEOUT_S = 1200
DEFAULT_AGY_AGENT = "rc_collab"
DEFAULT_AGY_BIN = str(Path.home() / ".local" / "bin" / "agy")
DEFAULT_AGY_HELPER = str(
    Path.home() / ".grok" / "skills" / "agy-cli-collab" / "scripts" / "agy_cli.py"
)

COLLAB_MODE = "agy-collab"
COLLAB_AUTHORS = frozenset({PRINCIPAL, GROK_USER, AGY_USER})
AGENT_TARGETS = frozenset({GROK_USER, AGY_USER})

# Word-boundary @username (case-insensitive match applied after capture).
_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9._-]+)\b")

# Global serialize for agy CLI (skill: never parallel agy subprocesses).
_agy_cli_lock = threading.Lock()


# --- Config / flags -----------------------------------------------------------


def _env_truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def collab_master_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Master switch RC_AGY_COLLAB (default off)."""
    e = env if env is not None else os.environ
    return _env_truthy(str(e.get("RC_AGY_COLLAB", "0")))


def agy_rc_username(env: Mapping[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return (e.get("RC_AGY_USER") or DEFAULT_AGY_USER).strip() or DEFAULT_AGY_USER


def hop_budget_default(env: Mapping[str, str] | None = None) -> int:
    e = env if env is not None else os.environ
    raw = (e.get("RC_AGY_HOP_BUDGET_EPOCH") or str(DEFAULT_HOP_BUDGET_EPOCH)).strip()
    try:
        n = int(raw)
        return max(1, n)
    except ValueError:
        return DEFAULT_HOP_BUDGET_EPOCH


def checkpoint_every_default(env: Mapping[str, str] | None = None) -> int:
    e = env if env is not None else os.environ
    raw = (e.get("RC_AGY_CHECKPOINT_EVERY") or str(DEFAULT_CHECKPOINT_EVERY)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_CHECKPOINT_EVERY


def agy_print_timeout(env: Mapping[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return (e.get("RC_AGY_PRINT_TIMEOUT") or DEFAULT_PRINT_TIMEOUT).strip() or DEFAULT_PRINT_TIMEOUT


def agy_wake_timeout_s(env: Mapping[str, str] | None = None) -> int:
    e = env if env is not None else os.environ
    raw = (e.get("RC_AGY_WAKE_TIMEOUT_S") or str(DEFAULT_AGY_WAKE_TIMEOUT_S)).strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_AGY_WAKE_TIMEOUT_S


def agy_bin_path(env: Mapping[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return (e.get("RC_AGY_BIN") or DEFAULT_AGY_BIN).strip() or DEFAULT_AGY_BIN


def agy_helper_path(env: Mapping[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return (e.get("RC_AGY_HELPER") or DEFAULT_AGY_HELPER).strip() or DEFAULT_AGY_HELPER


def agy_agent_name(env: Mapping[str, str] | None = None) -> str:
    e = env if env is not None else os.environ
    return (e.get("RC_AGY_AGENT") or DEFAULT_AGY_AGENT).strip() or DEFAULT_AGY_AGENT


# --- Room profile -------------------------------------------------------------


def _normalize_profile_entry(value: Any) -> dict[str, Any] | None:
    """
    Accept either a legacy string cwd or a dict profile.

    Returns a profile dict with at least optional keys: cwd, mode, hop_budget_epoch, …
    """
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        return {"cwd": s}
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str) or k.startswith("_"):
                continue
            out[k] = v
        return out if out else None
    return None


def load_channel_profiles(map_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """
    Load channel_projects.json supporting string cwd *or* object profiles.

    Keys: room name, #name, or slug. Meta keys starting with `_` are skipped.
    """
    if map_path is None:
        map_path = (
            Path.home()
            / ".grok"
            / "agency"
            / "ops"
            / "rocketchat"
            / "wake"
            / "channel_projects.json"
        )
    if not map_path.is_file():
        return {}
    try:
        raw = json.loads(map_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or k.startswith("_"):
            continue
        prof = _normalize_profile_entry(v)
        if prof is not None:
            out[k.strip()] = prof
    return out


def lookup_room_profile(
    room_name: str,
    profiles: Mapping[str, dict[str, Any]] | None = None,
    *,
    map_path: Path | None = None,
) -> dict[str, Any] | None:
    """Find a profile for room_name by exact / strip-# / lowercase / slug keys."""
    profs = profiles if profiles is not None else load_channel_profiles(map_path)
    name = (room_name or "").strip()
    if not name:
        return None
    slug = name.lstrip("#").lower().replace("_", "-").replace(" ", "-")
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    for key in (name, name.lstrip("#"), name.lower(), slug, f"#{name.lstrip('#')}"):
        if key in profs:
            return dict(profs[key])
    return None


def is_collab_profile(profile: Mapping[str, Any] | None) -> bool:
    if not profile:
        return False
    mode = str(profile.get("mode") or "").strip().lower()
    return mode == COLLAB_MODE


def collab_armed_for_room(
    room_name: str,
    *,
    env: Mapping[str, str] | None = None,
    profile: Mapping[str, Any] | None = None,
    profiles: Mapping[str, dict[str, Any]] | None = None,
    map_path: Path | None = None,
    room_type: str | None = None,
) -> bool:
    """
    True only when master flag on AND room profile mode=agy-collab.

    DMs and unprofiled channels never arm dual-peer (FR-A0–A2).
    """
    if not collab_master_enabled(env):
        return False
    rtype = (room_type or "").strip().lower()
    name = (room_name or "").strip()
    if rtype == "d" or name.lower().startswith("dm:") or name.lower() == "dm":
        return False
    prof = profile if profile is not None else lookup_room_profile(name, profiles, map_path=map_path)
    return is_collab_profile(prof)


def profile_cwd(profile: Mapping[str, Any] | None) -> str | None:
    if not profile:
        return None
    cwd = profile.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd.strip()
    return None


def profile_hop_budget(
    profile: Mapping[str, Any] | None,
    env: Mapping[str, str] | None = None,
) -> int:
    if profile and profile.get("hop_budget_epoch") is not None:
        try:
            return max(1, int(profile["hop_budget_epoch"]))
        except (TypeError, ValueError):
            pass
    return hop_budget_default(env)


# --- Mention parse ------------------------------------------------------------


def resolve_mention_targets(
    msg: Mapping[str, Any] | None,
    *,
    text: str | None = None,
    agent_usernames: frozenset[str] | set[str] | None = None,
) -> set[str]:
    """
    Prefer structured mentions[]; fall back to word-boundary @username in text.

    Returns lowercased agent targets intersected with {grok, agy} (or custom set).
    """
    agents = {u.lower() for u in (agent_usernames or AGENT_TARGETS)}
    found: set[str] = set()

    payload = msg or {}
    mentions = payload.get("mentions")
    if isinstance(mentions, list):
        for m in mentions:
            if not isinstance(m, dict):
                continue
            uname = (m.get("username") or m.get("name") or "").strip().lower()
            if uname in agents:
                found.add(uname)

    body = text if text is not None else (payload.get("msg") or "")
    if isinstance(body, str) and body:
        for m in _MENTION_RE.finditer(body):
            uname = m.group(1).lower()
            if uname in agents:
                found.add(uname)

    return found


def is_self_only_mention(author: str, targets: set[str]) -> bool:
    """True when the only target is the author (self-wake forbidden)."""
    a = (author or "").strip().lower()
    if not targets:
        return False
    return targets == {a} and a in AGENT_TARGETS


# --- Decision / routing -------------------------------------------------------


@dataclass
class CollabDecision:
    """Outcome of collab message classification (pure; no side effects)."""

    action: str  # wake | ignore | reject | notify_budget
    target: str | None = None  # grok | agy
    reason: str = ""
    reply: str = ""  # optional in-channel reply for reject/notify
    log_line: str = ""


def classify_collab_message(
    *,
    author: str,
    targets: set[str],
    collab_armed: bool,
    auto_handoff: bool = True,
    paused_reason: str | None = None,
    hop_count_epoch: int = 0,
    hop_budget_epoch: int = DEFAULT_HOP_BUDGET_EPOCH,
    principal: str = PRINCIPAL,
    grok_user: str = GROK_USER,
    agy_user: str = AGY_USER,
) -> CollabDecision:
    """
    Normative routing sketch from NF-SPEC-04 §4.3 (OD-A1: reject double-mention).

    Does not enqueue; caller enforces action.
    """
    author_l = (author or "").strip().lower()
    allow = {principal.lower(), grok_user.lower(), agy_user.lower()}
    agents = {grok_user.lower(), agy_user.lower()}
    tset = {t.lower() for t in targets} & agents

    if not collab_armed:
        return CollabDecision(
            action="ignore",
            reason="collab_not_armed",
            log_line="collab skip not_armed",
        )

    # author allowlist removed: allow anyone to trigger bots if tagged

    if not tset:
        return CollabDecision(
            action="ignore",
            reason="no_agent_mention",
            log_line=f"collab skip untagged author={author_l}",
        )

    if is_self_only_mention(author_l, tset):
        return CollabDecision(
            action="ignore",
            reason="self_mention",
            log_line=f"collab skip self_mention author={author_l}",
        )

    # Double-target: principal → reject with help (OD-A1); bots should not dual-tag.
    if len(tset) > 1:
        if author_l == principal.lower():
            return CollabDecision(
                action="reject",
                reason="double_mention",
                reply=(
                    "Mention **one** target agent per message "
                    f"(`@{grok_user}` or `@{agy_user}`), not both."
                ),
                log_line=f"collab reject double_mention author={author_l}",
            )
        # Bot dual-tag: pick peer that is not self if possible
        peer = next((t for t in sorted(tset) if t != author_l), None)
        if peer is None:
            return CollabDecision(
                action="ignore",
                reason="self_mention_multi",
                log_line=f"collab skip multi self author={author_l}",
            )
        tset = {peer}

    target = next(iter(tset))

    # Self still in multi after filter? already handled.
    if target == author_l:
        return CollabDecision(
            action="ignore",
            reason="self_mention",
            log_line=f"collab skip self_target author={author_l}",
        )

    paused = bool(paused_reason) or (not auto_handoff)
    budget_hit = hop_count_epoch >= hop_budget_epoch

    # Bot authors blocked when paused or budget exhausted (principal may still wake).
    if author_l in agents:
        if paused:
            return CollabDecision(
                action="ignore",
                reason="paused",
                log_line=(
                    f"collab skip paused author={author_l} reason={paused_reason or 'auto_off'}"
                ),
            )
        if budget_hit:
            return CollabDecision(
                action="notify_budget",
                reason="hop_budget",
                reply=(
                    f"Collab hop budget reached ({hop_count_epoch}/{hop_budget_epoch}). "
                    "Auto-handoff paused; sessions retained. "
                    "Principal: use `/resume` or `@`-wake after raising budget."
                ),
                log_line=(
                    f"collab pause reason=budget epoch_count={hop_count_epoch}/"
                    f"{hop_budget_epoch}"
                ),
            )

    return CollabDecision(
        action="wake",
        target=target,
        reason="mention",
        log_line=(
            f"collab mention author={author_l} targets={sorted(tset)} "
            f"wake_target={target}"
        ),
    )


# --- Durable collab room state ------------------------------------------------


def _rooms_bucket(state: dict) -> dict:
    rooms = state.get("rooms")
    if not isinstance(rooms, dict):
        rooms = {}
        state["rooms"] = rooms
    return rooms


def _room_entry(state: dict, room_id: str) -> dict:
    rooms = _rooms_bucket(state)
    entry = rooms.get(room_id)
    if not isinstance(entry, dict):
        entry = {}
        rooms[room_id] = entry
    return entry


def get_collab_room_state(state: dict, room_id: str) -> dict[str, Any]:
    """
    Normalized collab sub-object for a room (FR-A29 fields).

    Stored under state['rooms'][room_id]['collab'] with flat fallbacks.
    """
    entry = _room_entry(state, room_id)
    collab = entry.get("collab")
    if not isinstance(collab, dict):
        collab = {}
    # Flat legacy keys under room entry also accepted
    return {
        "conversation_id": collab.get("conversation_id")
        or entry.get("agy_conversation_id")
        or None,
        "epoch": int(collab.get("epoch") or entry.get("collab_epoch") or 1),
        "hop_count_epoch": int(
            collab.get("hop_count_epoch") or entry.get("hop_count_epoch") or 0
        ),
        "hop_budget_epoch": int(
            collab.get("hop_budget_epoch")
            or entry.get("hop_budget_epoch")
            or DEFAULT_HOP_BUDGET_EPOCH
        ),
        "total_hops": int(collab.get("total_hops") or entry.get("total_hops") or 0),
        "auto_handoff": bool(
            collab["auto_handoff"]
            if "auto_handoff" in collab
            else entry.get("auto_handoff", True)
        ),
        "paused_reason": collab.get("paused_reason")
        or entry.get("paused_reason")
        or None,
        "last_speaker": collab.get("last_speaker") or entry.get("last_speaker") or None,
        "last_hop_at": collab.get("last_hop_at") or entry.get("last_hop_at") or None,
    }


def set_collab_room_state(state: dict, room_id: str, collab: Mapping[str, Any]) -> dict:
    """Write collab sub-object; returns state for chaining."""
    entry = _room_entry(state, room_id)
    clean: dict[str, Any] = {
        "conversation_id": collab.get("conversation_id"),
        "epoch": int(collab.get("epoch") or 1),
        "hop_count_epoch": int(collab.get("hop_count_epoch") or 0),
        "hop_budget_epoch": int(
            collab.get("hop_budget_epoch") or DEFAULT_HOP_BUDGET_EPOCH
        ),
        "total_hops": int(collab.get("total_hops") or 0),
        "auto_handoff": bool(collab.get("auto_handoff", True)),
        "paused_reason": collab.get("paused_reason"),
        "last_speaker": collab.get("last_speaker"),
        "last_hop_at": collab.get("last_hop_at"),
    }
    entry["collab"] = clean
    return state


def ensure_collab_budget(
    state: dict,
    room_id: str,
    *,
    budget: int | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Ensure collab state exists with budget filled from env/profile default."""
    cur = get_collab_room_state(state, room_id)
    if budget is not None:
        cur["hop_budget_epoch"] = max(1, int(budget))
    elif not cur.get("hop_budget_epoch"):
        cur["hop_budget_epoch"] = hop_budget_default(env)
    set_collab_room_state(state, room_id, cur)
    return cur


def set_agy_conversation_id(state: dict, room_id: str, conversation_id: str | None) -> dict:
    cur = get_collab_room_state(state, room_id)
    cur["conversation_id"] = conversation_id
    return set_collab_room_state(state, room_id, cur)


def get_agy_conversation_id(state: dict, room_id: str) -> str | None:
    cid = get_collab_room_state(state, room_id).get("conversation_id")
    if isinstance(cid, str) and cid.strip():
        return cid.strip()
    return None


def pause_auto_handoff(state: dict, room_id: str, reason: str) -> dict:
    cur = get_collab_room_state(state, room_id)
    cur["auto_handoff"] = False
    cur["paused_reason"] = reason or "paused"
    return set_collab_room_state(state, room_id, cur)


def resume_auto_handoff(state: dict, room_id: str, *, reset_epoch_hops: bool = False) -> dict:
    cur = get_collab_room_state(state, room_id)
    cur["auto_handoff"] = True
    cur["paused_reason"] = None
    if reset_epoch_hops:
        cur["hop_count_epoch"] = 0
        cur["epoch"] = int(cur.get("epoch") or 1) + 1
    return set_collab_room_state(state, room_id, cur)


def record_collab_hop(
    state: dict,
    room_id: str,
    *,
    author: str,
    target: str,
    hop_at: str | None = None,
    count_toward_budget: bool | None = None,
) -> dict[str, Any]:
    """
    Increment hop counters after a successful collab wake enqueue/complete.

    Bot↔bot hops count toward epoch budget by default; principal→bot does not
    (FR-A33 soft bot↔bot budget).
    """
    cur = get_collab_room_state(state, room_id)
    author_l = (author or "").strip().lower()
    if count_toward_budget is None:
        count_toward_budget = author_l in AGENT_TARGETS
    if count_toward_budget:
        cur["hop_count_epoch"] = int(cur.get("hop_count_epoch") or 0) + 1
        cur["total_hops"] = int(cur.get("total_hops") or 0) + 1
    cur["last_speaker"] = target
    if hop_at:
        cur["last_hop_at"] = hop_at
    # Auto-pause at budget after recording
    if int(cur["hop_count_epoch"]) >= int(cur.get("hop_budget_epoch") or DEFAULT_HOP_BUDGET_EPOCH):
        cur["auto_handoff"] = False
        cur["paused_reason"] = cur.get("paused_reason") or "budget"
    set_collab_room_state(state, room_id, cur)
    return cur


def budget_exhausted(collab: Mapping[str, Any]) -> bool:
    return int(collab.get("hop_count_epoch") or 0) >= int(
        collab.get("hop_budget_epoch") or DEFAULT_HOP_BUDGET_EPOCH
    )


# --- Spin heuristic (lightweight) ---------------------------------------------


def looks_like_empty_handoff(text: str, peer_username: str) -> bool:
    """Near-empty body that only peer-tags (spin signal)."""
    body = (text or "").strip()
    if not body:
        return True
    # strip peer mention and whitespace/punctuation
    peer = peer_username.lower()
    cleaned = _MENTION_RE.sub(
        lambda m: "" if m.group(1).lower() == peer else m.group(0), body
    )
    cleaned = re.sub(r"[\s\W_]+", "", cleaned, flags=re.UNICODE)
    return len(cleaned) < 8


# --- Agy CLI (no MCP) ---------------------------------------------------------


@dataclass
class AgyCliPlan:
    """Planned local agy helper invocation (argv only; no execution)."""

    mode: str  # start | conversation | continue
    argv: list[str] = field(default_factory=list)
    conversation_id: str | None = None
    prompt_file: str = ""
    log_file: str = ""
    state_file: str = ""
    cwd: str = ""
    print_timeout: str = DEFAULT_PRINT_TIMEOUT
    uses_mcp: bool = False  # always False — contract guard


def build_agy_helper_plan(
    *,
    cwd: str,
    prompt_file: str,
    log_file: str,
    state_file: str,
    conversation_id: str | None = None,
    env: Mapping[str, str] | None = None,
    new_project: bool = True,
    project_name: str | None = None,
    python_bin: str = "python3",
) -> AgyCliPlan:
    """
    Build argv for skill helper agy_cli.py (CLI-only; never MCP).

    mode=conversation when conversation_id known; else start.
    """
    helper = agy_helper_path(env)
    agy = agy_bin_path(env)
    timeout = agy_print_timeout(env)
    mode = "conversation" if conversation_id else "start"
    argv = [
        python_bin,
        helper,
        "--cwd",
        cwd,
        "--agy",
        agy,
        "--mode",
        mode,
        "--prompt-file",
        prompt_file,
        "--log-file",
        log_file,
        "--state-file",
        state_file,
        "--print-timeout",
        timeout,
    ]
    if mode == "conversation" and conversation_id:
        argv.extend(["--conversation", conversation_id])
    if mode == "start" and new_project:
        argv.append("--new-project")
        if project_name:
            argv.extend(["--project", project_name])
    return AgyCliPlan(
        mode=mode,
        argv=argv,
        conversation_id=conversation_id,
        prompt_file=prompt_file,
        log_file=log_file,
        state_file=state_file,
        cwd=cwd,
        print_timeout=timeout,
        uses_mcp=False,
    )


def agy_cli_lock() -> threading.Lock:
    """Global lock — serialize agy subprocesses (FR-A22)."""
    return _agy_cli_lock


def assert_no_mcp_agy_in_argv(argv: list[str]) -> None:
    """Hard guard: argv must never reference MCP agy_* tool names as invocation."""
    joined = " ".join(argv).lower()
    for forbidden in ("agy_ask", "agy_ping", "agy_models", "agy_version", "mcp"):
        # allow path segments like "agy_cli.py" but not tool names
        if forbidden in ("agy_ask", "agy_ping", "agy_models", "agy_version"):
            if forbidden in joined:
                raise ValueError(f"forbidden MCP-style token in agy argv: {forbidden}")


# --- Inject / L3 --------------------------------------------------------------


def build_agy_l3_inject(
    *,
    mention_body: str,
    room_id: str,
    room_name: str,
    cwd: str,
    author: str,
    collab: Mapping[str, Any],
    write_scope: str = "read-only",
    peer_last_summary: str = "",
) -> str:
    """Per-turn inject for agy print prompt (FR-A41)."""
    lines = [
        "# RC collab turn brief (agy peer)",
        "",
        f"- Room: {room_name or room_id} (`{room_id}`)",
        f"- cwd: {cwd}",
        f"- Author of wake message: {author}",
        f"- You post as Rocket.Chat user **agy** (stdout is the channel body).",
        f"- auto_handoff: {collab.get('auto_handoff', True)}",
        f"- paused_reason: {collab.get('paused_reason') or 'none'}",
        f"- epoch: {collab.get('epoch', 1)}",
        f"- hop_count_epoch: {collab.get('hop_count_epoch', 0)}/"
        f"{collab.get('hop_budget_epoch', DEFAULT_HOP_BUDGET_EPOCH)}",
        f"- total_hops: {collab.get('total_hops', 0)}",
        f"- agy.conversation_id: {collab.get('conversation_id') or 'NONE'}",
        f"- write_scope: {write_scope}",
        "",
        "## Handoff protocol",
        "- To continue with Grok, include a real **@grok** mention and a concrete ask.",
        "- To yield, omit @grok.",
        "- Do not self-mention only @agy.",
        "- Do not impersonate grok or invent Grok's words.",
        "",
    ]
    if peer_last_summary:
        lines.extend(["## Peer context (summary)", peer_last_summary, ""])
    lines.extend(["## Message that mentioned you", mention_body.strip(), ""])
    if not collab.get("auto_handoff", True) or collab.get("paused_reason"):
        lines.extend(
            [
                "## Pause note",
                "Auto-handoff is paused — do **not** @grok; summarize for principal.",
                "",
            ]
        )
    return "\n".join(lines)


def build_grok_collab_inject_block(
    *,
    collab: Mapping[str, Any],
    inject_template: str = "",
    author: str = "",
) -> str:
    """
    Fragment to prepend for Grok-target wakes in collab rooms (FR-A42).

    If inject_template provided (file body), append hop/status footer.
    """
    header = (inject_template or "").strip()
    if not header:
        header = (
            "You are Rocket.Chat user **grok** in a dual-peer collab room with **agy**.\n"
            "Do **not** shell out to the `agy` CLI or MCP `agy_*` — Gemini speaks as user `agy`.\n"
            "To hand off, include a real **@agy** mention; omit it to yield.\n"
            "Write the final answer only to the reply file (NO DUPLICATE POSTS).\n"
        )
    footer = (
        f"\n---\nCollab status: auto_handoff={collab.get('auto_handoff', True)} "
        f"paused={collab.get('paused_reason') or 'none'} "
        f"hops={collab.get('hop_count_epoch', 0)}/"
        f"{collab.get('hop_budget_epoch', DEFAULT_HOP_BUDGET_EPOCH)} "
        f"epoch={collab.get('epoch', 1)} author={author or '?'}\n"
    )
    return header + footer


def load_grok_inject_template(path: Path | None = None) -> str:
    """Load optional inject file; empty string if missing."""
    p = path or (
        Path.home()
        / ".grok"
        / "agency"
        / "ops"
        / "rocketchat"
        / "wake"
        / "collab_inject_grok.md"
    )
    if not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


# --- Auth helpers (pure resolution; no network) -------------------------------


@dataclass
class IdentityCreds:
    username: str
    token: str | None = None
    user_id: str | None = None
    password: str | None = None


def resolve_identity_creds(
    identity: str,
    secrets: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
) -> IdentityCreds:
    """
    Resolve RC credentials for grok (operator) or agy peer from secrets/env.

    Does not perform login. Agy secrets: RC_AGY_TOKEN + RC_AGY_USER_ID or
    ROCKETCHAT_AGY_PASSWORD / RC_AGY_PASSWORD.
    """
    s = dict(secrets or {})
    e = env if env is not None else os.environ
    # merge env over secrets for non-secret flags; secrets win for passwords if both
    ident = (identity or "").strip().lower()
    if ident in ("", GROK_USER, "operator"):
        return IdentityCreds(
            username=s.get("ROCKETCHAT_OPERATOR_USERNAME") or GROK_USER,
            token=(
                s.get("ROCKETCHAT_OPERATOR_TOKEN")
                or s.get("ROCKETCHAT_BOT_TOKEN")
                or None
            ),
            user_id=(
                s.get("ROCKETCHAT_OPERATOR_USER_ID")
                or s.get("ROCKETCHAT_BOT_USER_ID")
                or None
            ),
            password=s.get("ROCKETCHAT_OPERATOR_PASSWORD") or None,
        )
    # agy
    uname = (
        e.get("RC_AGY_USER")
        or s.get("RC_AGY_USER")
        or s.get("ROCKETCHAT_AGY_USERNAME")
        or DEFAULT_AGY_USER
    )
    token = (
        e.get("RC_AGY_TOKEN")
        or s.get("RC_AGY_TOKEN")
        or s.get("ROCKETCHAT_AGY_TOKEN")
        or None
    )
    uid = (
        e.get("RC_AGY_USER_ID")
        or s.get("RC_AGY_USER_ID")
        or s.get("ROCKETCHAT_AGY_USER_ID")
        or None
    )
    password = (
        e.get("RC_AGY_PASSWORD")
        or s.get("RC_AGY_PASSWORD")
        or s.get("ROCKETCHAT_AGY_PASSWORD")
        or None
    )
    return IdentityCreds(
        username=str(uname).strip() or DEFAULT_AGY_USER,
        token=str(token).strip() if token else None,
        user_id=str(uid).strip() if uid else None,
        password=str(password) if password else None,
    )


def format_agy_cli_error(rc: int, stderr_tail: str = "", log_name: str = "") -> str:
    """Honest failure body for agy bubble (FR-A20) — never fabricates Gemini content."""
    lines = [
        "(agy CLI did not produce a usable reply.)",
        "",
        f"- exit code: {rc}",
    ]
    if log_name:
        lines.append(f"- log: `{log_name}`")
    if stderr_tail:
        tail = stderr_tail.strip()[-800:]
        lines.append("")
        lines.append("```")
        lines.append(tail)
        lines.append("```")
    lines.append("")
    lines.append("No MCP fallback. Retry or check local `agy` auth.")
    return "\n".join(lines)
