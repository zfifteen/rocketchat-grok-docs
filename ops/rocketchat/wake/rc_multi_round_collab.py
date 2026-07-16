#!/usr/bin/env python3
"""
Multi-round Rocket.Chat collab — pure policy helpers.

Contract (principal lock-in):
- Grok is lead; one protocol for grok/hermes/agy/claude.
- Shared rooms: tag-to-talk starts; return-notify on peer wake completion
  **only when the trigger author is a bot operator** (lead/peer hop).
- Direct principal→peer is solo: no return-notify (no false collab to grok).
- Return-notify target: assigner if assigner is a bot operator, else grok
  (target resolution only; emit still requires bot assigner).
- After plain-language lead DONE, suppress automatic return-notify.
- No hard hop-budget state machine; no required machine DONE footer.

No network I/O. Unit-testable without Rocket.Chat.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Mapping

# --- Constants ----------------------------------------------------------------

GROK_LEAD = "grok"
PRINCIPAL = "principal"  # default username; override via RC_PRINCIPAL_USERNAME
ALL_OPERATORS = frozenset({"grok", "hermes", "agy", "claude"})
PEER_OPERATORS = frozenset({"hermes", "agy", "claude"})

# Posted by the operator after a peer collab wake completes (wakes assigner|lead).
COLLAB_RETURN_MARKER = "collab-return"
# Operator template shape only — prose discussing "collab-return" must not match.
_COLLAB_RETURN_TEMPLATE_RE = re.compile(
    r"(?<!\w)@([A-Za-z0-9._-]+)\s+collab-return\s+from\s+`?([A-Za-z0-9._-]+)`?",
    re.I,
)

DEFAULT_PLAYBOOK_NAME = "RC_MULTI_ROUND_COLLAB_PLAYBOOK.md"
DEFAULT_STATE_NAME = "multi_round_collab_state.json"

# Plain-language lead DONE (acceptance: no machine footer required).
# Patterns require collab/goal closure language — not mid-task "done with X" / "concludes my analysis".
_LEAD_DONE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bthis\s+concludes\s+(?:the\s+)?(?:collab|collaboration)\b", re.I),
    re.compile(r"\bthis\s+(?:collab|collaboration)\s+(?:is\s+)?(?:finished|complete|done)\b", re.I),
    re.compile(r"\bcollaboration\s+(?:is\s+)?complete\b", re.I),
    re.compile(r"\bcollab(?:oration)?\s+(?:is\s+)?done\b", re.I),
    re.compile(r"\bgoal\s+(?:is\s+)?(?:met|achieved|complete)\b", re.I),
    re.compile(r"\bno\s+further\s+(?:work|rounds|handoffs|assignments)\b", re.I),
    re.compile(r"\bfinal\s+conclusion\s*:", re.I),
    re.compile(r"\bdeclaring\s+(?:the\s+)?(?:collab\s+)?done\b", re.I),
    # "we're done" only when collab/goal/handoff language is also present
    re.compile(
        r"\bwe(?:'re|\s+are)\s+done\b[\s\S]{0,120}\b(?:collab|collaboration|goal|handoffs?)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:collab|collaboration|goal|handoffs?)\b[\s\S]{0,120}\bwe(?:'re|\s+are)\s+done\b",
        re.I,
    ),
)
# "done with inventory" / task-slice language is not whole-collab DONE unless collab keywords present.
_PARTIAL_DONE_WITH_RE = re.compile(r"\bdone\s+with\b", re.I)

# Peer close-out / silence acks after DONE must not return-notify the lead (anti-loop).
_PEER_CLOSEOUT_ACK_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcollaboration\s+(?:is\s+)?complete\b", re.I),
    re.compile(r"\bcollab(?:oration)?\s+(?:is\s+)?done\b", re.I),
    re.compile(r"\bstay(?:ing)?\s+silent\b", re.I),
    re.compile(r"\bsilence\s+(?:is\s+)?correct\b", re.I),
    re.compile(r"\bstanding\s+by\b", re.I),
    re.compile(r"\bno\s+further\s+(?:work|rounds|handoffs|assignments)\b", re.I),
    re.compile(r"\bclosed\s+goals?\b", re.I),
    re.compile(r"\bprevent\s+the\s+loop\b", re.I),
)

_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9._-]+)\b")

_state_lock = threading.Lock()


# --- Flags --------------------------------------------------------------------


def _env_truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def multi_round_enabled(env: Mapping[str, str] | None = None) -> bool:
    """
    RC_MULTI_ROUND_COLLAB — master switch (default ON).

    Explicit 0/false/off disables return-notify + playbook inject preference.
    """
    e = env if env is not None else os.environ
    if "RC_MULTI_ROUND_COLLAB" in e:
        return _env_truthy(str(e.get("RC_MULTI_ROUND_COLLAB", "")))
    return True


def principal_username(env: Mapping[str, str] | None = None) -> str:
    """RC_PRINCIPAL_USERNAME override; default `principal`."""
    e = env if env is not None else os.environ
    raw = (e.get("RC_PRINCIPAL_USERNAME") or "").strip()
    return normalize_username(raw) if raw else PRINCIPAL


def playbook_path(env: Mapping[str, str] | None = None, *, wake_dir: Path | None = None) -> Path:
    e = env if env is not None else os.environ
    raw = (e.get("RC_MULTI_ROUND_PLAYBOOK") or "").strip()
    if raw:
        return Path(raw).expanduser()
    base = wake_dir or Path(__file__).resolve().parent
    return base / DEFAULT_PLAYBOOK_NAME


def shared_state_path(env: Mapping[str, str] | None = None, *, wake_dir: Path | None = None) -> Path:
    """Cross-operator durable state (lead_done per room). Shared file for all launchd bots."""
    e = env if env is not None else os.environ
    raw = (e.get("RC_MULTI_ROUND_STATE") or "").strip()
    if raw:
        return Path(raw).expanduser()
    base = wake_dir or Path(__file__).resolve().parent
    return base / DEFAULT_STATE_NAME


def load_playbook_text(env: Mapping[str, str] | None = None, *, wake_dir: Path | None = None) -> str:
    path = playbook_path(env, wake_dir=wake_dir)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return (
            "# Multi-round RC collab (fallback)\n\n"
            "Grok is lead. Peers deliver then return-notify re-engages assigner|grok. "
            "Lead must re-assign with @tags or declare done in plain language.\n"
        )


def playbook_inject_block(env: Mapping[str, str] | None = None, *, wake_dir: Path | None = None) -> str:
    """Block appended into every wake prompt when multi-round is enabled."""
    if not multi_round_enabled(env):
        return ""
    body = load_playbook_text(env, wake_dir=wake_dir).strip()
    return (
        "\n\n---\n"
        "## Multi-round Rocket.Chat collab playbook (mandatory)\n\n"
        f"{body}\n"
        "---\n"
    )


# --- Assigner / return-notify resolution --------------------------------------


def normalize_username(name: str | None) -> str:
    return (name or "").strip().lower()


def is_operator_username(name: str | None) -> bool:
    return normalize_username(name) in ALL_OPERATORS


def is_peer_operator(name: str | None) -> bool:
    return normalize_username(name) in PEER_OPERATORS


def is_lead_operator(name: str | None) -> bool:
    return normalize_username(name) == GROK_LEAD


def resolve_return_notify_target(
    assigner: str | None,
    *,
    lead: str = GROK_LEAD,
    operators: frozenset[str] | None = None,
    completing_operator: str | None = None,
) -> str:
    """
    Assigner if that user is a bot operator, else lead (grok).

    Never returns the completing operator (would self-notify). Falls back to lead.
    """
    ops = operators if operators is not None else ALL_OPERATORS
    lead_u = normalize_username(lead) or GROK_LEAD
    a = normalize_username(assigner)
    self_u = normalize_username(completing_operator)
    if a and a in ops and a != self_u:
        return a
    if lead_u != self_u:
        return lead_u
    # Completing operator is lead and assigner unclear — no sensible other target.
    return lead_u


def message_is_collab_return(text: str | None) -> bool:
    """
    True if body matches the operator return-notify template shape.

    Requires ``@target collab-return from `peer``` — bare substring
    "collab-return" in prose (e.g. playbook discussion) must not match.
    """
    if not text:
        return False
    return bool(_COLLAB_RETURN_TEMPLATE_RE.search(str(text)))


def extract_mention_usernames(text: str | None) -> set[str]:
    if not text:
        return set()
    return {m.group(1).lower() for m in _MENTION_RE.finditer(text)}


def extract_structured_mention_usernames(msg: Mapping[str, Any] | None) -> set[str]:
    """Rocket.Chat structured mentions[] usernames (B1 enqueue residual)."""
    out: set[str] = set()
    if not msg:
        return out
    mentions = msg.get("mentions")
    if not isinstance(mentions, list):
        return out
    for item in mentions:
        if not isinstance(item, dict):
            continue
        uname = normalize_username(item.get("username") or item.get("name"))
        if uname:
            out.add(uname)
    return out


def extract_glued_mention_usernames(text: str | None) -> set[str]:
    """Recover peers from glued forms like @grok@hermes (B1 residual)."""
    if not text:
        return set()
    out: set[str] = set()
    for run in re.finditer(r"(?:@([A-Za-z0-9._-]+))+", str(text)):
        chunk = run.group(0)
        out.update(m.lower() for m in re.findall(r"@([A-Za-z0-9._-]+)", chunk))
    return out


def extract_all_mention_usernames(
    msg: Mapping[str, Any] | None = None,
    text: str | None = None,
) -> set[str]:
    """Union of structured + text + glued-run mentions for lead-only gate."""
    body = text if text is not None else ((msg or {}).get("msg") or "")
    body_s = body if isinstance(body, str) else ""
    return (
        extract_structured_mention_usernames(msg)
        | extract_mention_usernames(body_s)
        | extract_glued_mention_usernames(body_s)
    )


def lead_done_language_present(text: str | None) -> bool:
    """True if plain-language collab-closure patterns appear (ignores @tags)."""
    if not text or not str(text).strip():
        return False
    body = str(text)
    if _PARTIAL_DONE_WITH_RE.search(body):
        if not re.search(r"\b(collab|collaboration|goal|handoffs?)\b", body, re.I):
            return False
    return any(p.search(body) for p in _LEAD_DONE_RES)


# Open assign language: peer tag is a real handoff, not a close-out "Copy @agy".
_OPEN_ASSIGN_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"@(?:hermes|agy|claude)\b[\s\S]{0,80}\b("
        r"please|dig|continue|task|assign|check|run|write|fix|retry|expand|falsify"
        r")\b",
        re.I,
    ),
    re.compile(
        r"\b("
        r"please|dig|continue|your task|next steps?|re-?assign"
        r")\b[\s\S]{0,80}@(?:hermes|agy|claude)\b",
        re.I,
    ),
)


def lead_reply_has_open_peer_assign(text: str | None) -> bool:
    """True when lead is handing open work to peers (not mere @mention in a DONE ack)."""
    if not text:
        return False
    body = str(text)
    if not (extract_mention_usernames(body) & PEER_OPERATORS):
        return False
    return any(p.search(body) for p in _OPEN_ASSIGN_RES)


def reply_declares_lead_done(text: str | None) -> bool:
    """
    Heuristic plain-language DONE detection for lead replies.

    Close-out loop fix (Prime-Gap-Structure 2026-07-14): lead often wrote
    "Collaboration complete. Copy @agy" — peer @tags must not veto strong DONE
    language, or lead_done never sticks and return-notify thrash continues.

    Still not DONE for mid-collab "We're done with inventory; @hermes dig …"
    (open assign + weak/partial done-with language).
    """
    if not lead_done_language_present(text):
        return False
    body = str(text)
    # Strong DONE + open assign in the same bubble → treat as continue (new work).
    if lead_reply_has_open_peer_assign(body):
        return False
    # Strong DONE with incidental @peer ("Copy @agy") → DONE for state.
    return True


def should_skip_lead_llm_on_collab_return(
    *,
    operator: str,
    trigger_text: str | None,
    lead_done: bool,
    env: Mapping[str, str] | None = None,
) -> bool:
    """
    After lead DONE, collab-return pings must not spawn another lead LLM wake.

    Peers may still have in-flight returns; short-circuit stops the close-out loop.
    """
    if not multi_round_enabled(env):
        return False
    if normalize_username(operator) != GROK_LEAD:
        return False
    if not lead_done:
        return False
    return message_is_collab_return(trigger_text)


def should_skip_lead_llm_on_peer_closeout_ack(
    *,
    operator: str,
    author: str | None,
    trigger_text: str | None,
    lead_done: bool,
    env: Mapping[str, str] | None = None,
) -> bool:
    """
    After lead DONE, peer "standing by @grok" acks must not spawn lead LLM.

    Skill forbids peer @grok on stand-down; this is the operator safety net.
    """
    if not multi_round_enabled(env):
        return False
    if normalize_username(operator) != GROK_LEAD:
        return False
    if not lead_done:
        return False
    auth = normalize_username(author)
    if auth not in PEER_OPERATORS:
        return False
    if message_is_collab_return(trigger_text):
        return True
    return peer_reply_is_closeout_ack(trigger_text)


def shared_room_type(room_type: str | None) -> bool:
    """Channels and private groups are shared; DMs are not multi-round return-notify scope."""
    t = (room_type or "").strip().lower()
    return t in {"c", "p"}


def peer_reply_is_closeout_ack(text: str | None) -> bool:
    """
    True when a peer reply is only acknowledging close / silence / standing-by,
    not delivering open work that the lead must synthesize.

    Used to suppress return-notify after DONE when lead_done was not yet durable
    or peers re-ack closed goals (close-out loop).
    """
    if not text or not str(text).strip():
        return False
    body = str(text)
    # New peer handoff keeps the collab open — still notify.
    if extract_mention_usernames(body) & PEER_OPERATORS:
        return False
    return any(p.search(body) for p in _PEER_CLOSEOUT_ACK_RES)


# Operator error / empty-hop templates that must not spam the lead while collab is open.
_EMPTY_FAILURE_TEMPLATES: tuple[re.Pattern[str], ...] = (
    re.compile(r"could\s+not\s+complete\s+this\s+reply", re.I),
    re.compile(r"wake\s+did\s+not\s+produce\s+a\s+reply\s+file", re.I),
    re.compile(r"wake\s+failed", re.I),
    re.compile(r"\brc:\s*1\b", re.I),
    re.compile(r"stopReason:\s*unknown", re.I),
    re.compile(r"send\s+another\s+message\s+to\s+retry", re.I),
    re.compile(r"\(first\s+attempt\s+ended\s+incomplete", re.I),
)

_STRUCTURED_FAILURE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bblocked\b", re.I),
    re.compile(r"\bcould\s+not\b.+\bbecause\b", re.I),
    re.compile(r"\breassign\b|\bre-?assign\b", re.I),
    re.compile(r"\bwhat\s+failed\b|\bwhy\b.+\bnext\b", re.I),
)


def reply_body_is_operator_empty_failure(reply_body: str | None) -> bool:
    """True for empty or template-only wake failure bubbles (not useful peer content)."""
    if reply_body is None:
        return True
    body = str(reply_body).strip()
    if not body:
        return True
    # Strip thought stream if present
    if body.lstrip().startswith("*Thoughts*"):
        parts = [p.strip() for p in body.split("\n\n") if p.strip()]
        # last non-thought chunk
        for p in reversed(parts):
            if not p.startswith("*Thoughts*"):
                body = p
                break
        else:
            body = parts[-1] if parts else body
    if len(body) < 12:
        return True
    hits = sum(1 for p in _EMPTY_FAILURE_TEMPLATES if p.search(body))
    if hits >= 1 and len(body) < 600:
        # Structured failure with diagnostics still counts as useful.
        if any(p.search(body) for p in _STRUCTURED_FAILURE_RES) and len(body) > 80:
            return False
        return True
    return False


def reply_body_useful_for_return_notify(
    reply_body: str | None,
    *,
    phase: str | None = None,
    rc: int | None = None,
) -> bool:
    """
    Quality gate for open-collab return-notify (issue #2 P0).

    Empty / operator error templates must not spam the lead. Structured
    \"blocked + why + next\" failures may still notify.
    """
    body = (reply_body or "").strip()
    phase_u = (phase or "").upper()
    # Decision table: empty body + hard fail → never notify
    if not body and rc is not None and int(rc) != 0:
        return False
    if not body and phase_u in {"FINAL_ERR", "PHASE_FINAL_ERR", "ERR"}:
        return False
    if reply_body_is_operator_empty_failure(reply_body):
        return False
    return True


def principal_lead_only_enabled(env: Mapping[str, str] | None = None) -> bool:
    """
    RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY — default ON.

    When on, principal multi-@ of lead+peers enqueues lead only (issue #2 Phase 1).
    Set to 0/false/off to restore legacy multi-@ concurrent peer wakes.
    """
    e = env if env is not None else os.environ
    if "RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY" in e:
        return _env_truthy(str(e.get("RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY", "")))
    return True


def principal_multi_mention_lead_only(
    *,
    author: str | None,
    operator: str | None,
    text: str | None,
    room_type: str | None,
    lead: str = GROK_LEAD,
    env: Mapping[str, str] | None = None,
    msg: Mapping[str, Any] | None = None,
) -> bool:
    """
    When True, this operator must **not** enqueue despite being @mentioned.

    Phase 1 (issue #2): principal opens multi-round work by tagging lead **and**
    peers in one message → only the lead may wake; peers wait for lead assign.
    Direct principal→@peer (lead not mentioned) still wakes that peer.
    Peer-authored tags unchanged (returns False).

    B1 residual: union structured mentions[] + text + glued runs (@grok@hermes)
    so peers do not slip through while lead-only only saw text-regex lead.
    """
    if not multi_round_enabled(env):
        return False
    if not principal_lead_only_enabled(env):
        return False
    if not shared_room_type(room_type):
        return False
    if normalize_username(author) != principal_username(env):
        return False
    op = normalize_username(operator)
    lead_u = normalize_username(lead) or GROK_LEAD
    if not op or op == lead_u:
        return False  # lead always may enqueue when tagged
    mentions = extract_all_mention_usernames(msg, text=text)
    if lead_u not in mentions:
        return False  # principal → single peer direct assign OK
    if not (mentions & PEER_OPERATORS):
        return False
    # Principal tagged lead + at least one peer → peers skip; lead handles fan-out.
    return op in PEER_OPERATORS


def should_emit_return_notify(
    *,
    operator: str,
    assigner: str | None,
    room_type: str | None,
    lead_done: bool,
    reply_body: str | None = None,
    trigger_text: str | None = None,
    phase: str | None = None,
    rc: int | None = None,
    env: Mapping[str, str] | None = None,
    room_id: str | None = None,
    path: Path | None = None,
) -> bool:
    """
    Whether the completing process should post a return-notify @target message.

    - Multi-round enabled
    - Shared room (c/p)
    - Completing operator is a peer (not lead) — lead continues via @tags or DONE
    - Trigger author (assigner) is a bot operator — lead or peer opened the hop
    - Lead has not declared DONE for this room
    - When room_id is set: completing operator must be an assignee of the open epoch (B7)
    - Trigger must not itself be a collab-return ping (blocks peer↔peer ping-pong)
    - Skip if reply body already @mentions the resolved return target (avoid double ping)
    - Skip pure peer close-out / standing-by acks (anti-loop after DONE)
    - Skip empty / operator-error templates (open-collab quality gate)

    Direct principal→peer (e.g. ``@hermes dig residuals`` with no lead hop) is a
    **solo** task: do not return-notify @grok. Bug observed 2026-07-15 in
    #Prime-Gap-Structure; fixed in runtime and mirrored here.
    """
    if not multi_round_enabled(env):
        return False
    if lead_done:
        return False
    # Completing a wake that was itself a return-notify must not emit another
    # (agy ←collab-return— hermes ←collab-return— agy …).
    if message_is_collab_return(trigger_text):
        return False
    if not shared_room_type(room_type):
        return False
    op = normalize_username(operator)
    if not op or op not in ALL_OPERATORS:
        return False
    # Only peers auto return-notify. Lead uses explicit @tags or declares done.
    if op == GROK_LEAD:
        return False
    # Solo principal (or any non-bot) → peer: not multi-round collab.
    assigner_u = normalize_username(assigner)
    if not assigner_u or assigner_u not in ALL_OPERATORS:
        return False
    # B7 second belt: only assignees of an open epoch emit collab-return.
    # Optional when room_id omitted (unit tests for earlier gates only).
    if room_id:
        st = load_shared_state(path=path, env=env)
        entry = (st.get("rooms") or {}).get(str(room_id)) or {}
        if entry.get("lead_done"):
            return False
        assignees = {
            normalize_username(a)
            for a in (entry.get("assignees") or [])
            if normalize_username(a)
        }
        if op not in assignees:
            return False
    # Peer "I'll stay silent / collaboration complete / standing by" must not
    # re-wake the lead (close-out loop). Open work still uses @peer tags or
    # non-closeout delivery bodies.
    if peer_reply_is_closeout_ack(reply_body):
        return False
    if not reply_body_useful_for_return_notify(reply_body, phase=phase, rc=rc):
        return False
    target = resolve_return_notify_target(
        assigner, lead=GROK_LEAD, completing_operator=op
    )
    if target == op:
        return False
    # If the peer already @mentioned the return target in the user-facing reply, skip.
    if reply_body and target in extract_mention_usernames(reply_body):
        return False
    return True


def build_return_notify_text(
    *,
    target: str,
    completing_operator: str,
    source_mid: str | None,
    room_name: str = "",
    summary: str = "",
    epoch: str | None = None,
) -> str:
    """
    Short channel message that @tags the next hop (assigner|lead).

    Cross-process wake: the target bot's operator sees peer @tag and enqueues.
    Optional epoch= stamp ties the notify to the collab epoch (P1).
    """
    tgt = normalize_username(target) or GROK_LEAD
    who = normalize_username(completing_operator) or "peer"
    mid = (source_mid or "").strip() or "unknown"
    room = (room_name or "").strip()
    room_bit = f" room={room}" if room else ""
    ep = (epoch or "").strip()
    epoch_bit = f" epoch=`{ep}`" if ep else ""
    sum_bit = ""
    if summary:
        one = " ".join(str(summary).split())
        if len(one) > 160:
            one = one[:157] + "..."
        sum_bit = f"\nStatus: {one}"
    return (
        f"@{tgt} {COLLAB_RETURN_MARKER} from `{who}` · mid=`{mid}`{room_bit}{epoch_bit}. "
        f"Peer finished a collab wake — continue (synthesize, re-assign with @tags, "
        f"or declare done in plain language).{sum_bit}"
    )


def should_suppress_return_notify_for_lead_done(
    *,
    lead_done: bool,
) -> bool:
    """Acceptance helper: after lead DONE, return-notify alone does not re-arm."""
    return bool(lead_done)


# --- Durable shared state (lead_done per room) ---------------------------------
#
# Cross-process safety: four launchd operators share one JSON file. Every
# read-modify-write must hold the flock for the **entire** critical section
# (load → mutate → write). Writing under flock alone is last-writer-wins.


def empty_state() -> dict[str, Any]:
    return {"version": 2, "rooms": {}}


def _flock_path(state_path: Path) -> Path:
    return state_path.with_suffix(state_path.suffix + ".lock")


def _load_shared_state_unlocked(p: Path) -> dict[str, Any]:
    if not p.is_file():
        return empty_state()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_state()
    if not isinstance(data, dict):
        return empty_state()
    rooms = data.get("rooms")
    if not isinstance(rooms, dict):
        data["rooms"] = {}
    data.setdefault("version", 2)
    return data


def _write_shared_state_unlocked(p: Path, state: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(p)


def load_shared_state(path: Path | None = None, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Read-only snapshot (no flock). Prefer update_shared_state for mutations."""
    p = path or shared_state_path(env)
    with _state_lock:
        return _load_shared_state_unlocked(p)


def save_shared_state(
    state: dict[str, Any],
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """
    Write a full state dict under flock.

    Prefer update_shared_state for RMW — callers that load outside the lock
    and then save can still lose concurrent updates.
    """
    p = path or shared_state_path(env)
    lock_p = _flock_path(p)
    with _state_lock:
        try:
            import fcntl  # Unix; principal Mac ops path

            with lock_p.open("a+", encoding="utf-8") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    _write_shared_state_unlocked(p, state)
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception:
            _write_shared_state_unlocked(p, state)


def update_shared_state(
    mutator,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Any:
    """
    Atomic cross-process RMW: flock → load → mutator(state) → write → unlock.

    ``mutator(state)`` may mutate ``state`` in place and may return a value
    (returned to the caller). Thread Lock alone is insufficient across processes.
    """
    p = path or shared_state_path(env)
    lock_p = _flock_path(p)
    with _state_lock:
        try:
            import fcntl

            with lock_p.open("a+", encoding="utf-8") as lf:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    st = _load_shared_state_unlocked(p)
                    result = mutator(st)
                    _write_shared_state_unlocked(p, st)
                    return result
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        except Exception:
            # Fallback (tests / non-Unix): process-local lock only
            st = _load_shared_state_unlocked(p)
            result = mutator(st)
            _write_shared_state_unlocked(p, st)
            return result


def get_room_collab_flags(state: Mapping[str, Any], room_id: str) -> dict[str, Any]:
    rooms = state.get("rooms") if isinstance(state, Mapping) else None
    if not isinstance(rooms, dict):
        return {"lead_done": False, "epoch": None, "assignees": [], "delivered": {}}
    entry = rooms.get(room_id) or rooms.get(str(room_id))
    if not isinstance(entry, dict):
        return {"lead_done": False, "epoch": None, "assignees": [], "delivered": {}}
    delivered = entry.get("delivered") if isinstance(entry.get("delivered"), dict) else {}
    assignees = entry.get("assignees") if isinstance(entry.get("assignees"), list) else []
    return {
        "lead_done": bool(entry.get("lead_done")),
        "lead_done_at": entry.get("lead_done_at"),
        "lead_done_mid": entry.get("lead_done_mid"),
        "epoch": entry.get("epoch"),
        "assignees": list(assignees),
        "delivered": dict(delivered),
    }


def set_room_lead_done(
    state: dict[str, Any],
    room_id: str,
    *,
    done: bool,
    at: str | None = None,
    mid: str | None = None,
) -> dict[str, Any]:
    rooms = state.setdefault("rooms", {})
    if not isinstance(rooms, dict):
        rooms = {}
        state["rooms"] = rooms
    rid = str(room_id)
    entry = dict(rooms.get(rid) or {})
    entry["lead_done"] = bool(done)
    if done:
        if at:
            entry["lead_done_at"] = at
        if mid:
            entry["lead_done_mid"] = mid
    else:
        entry.pop("lead_done_at", None)
        entry.pop("lead_done_mid", None)
    rooms[rid] = entry
    return state


def room_lead_done(room_id: str, *, path: Path | None = None, env: Mapping[str, str] | None = None) -> bool:
    st = load_shared_state(path=path, env=env)
    return bool(get_room_collab_flags(st, room_id).get("lead_done"))


def mark_lead_done(
    room_id: str,
    *,
    at: str | None = None,
    mid: str | None = None,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    def _mut(st: dict[str, Any]) -> None:
        set_room_lead_done(st, room_id, done=True, at=at, mid=mid)

    update_shared_state(_mut, path=path, env=env)


def clear_lead_done(
    room_id: str,
    *,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    def _mut(st: dict[str, Any]) -> None:
        set_room_lead_done(st, room_id, done=False)

    update_shared_state(_mut, path=path, env=env)


def maybe_clear_lead_done_on_new_work(
    *,
    room_id: str,
    author: str | None,
    operator: str | None,
    trigger_text: str | None,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """
    Clear lead_done only for a **principal** opening new multi-round work.

    Close-out loop fix: lead messages like "Copy @agy — collaboration complete"
    used to clear lead_done (author=grok + peer @tag), re-arming return-notify
    and thrashing the room. Lead must not reopen via incidental peer tags.

    Principal re-opens by @-tagging at least one bot (usually @grok) with a new
    ask, excluding pure loop diagnostics without a new goal/task.
    Return-notify pings never clear DONE.
    Returns True if cleared.
    """
    if message_is_collab_return(trigger_text):
        return False
    auth = normalize_username(author)
    # Only the human principal re-opens a closed collab.
    if auth != principal_username(env):
        return False
    if lead_done_language_present(trigger_text) or reply_declares_lead_done(trigger_text):
        return False
    text = str(trigger_text or "")
    mentions = extract_mention_usernames(text)
    if not (mentions & ALL_OPERATORS):
        return False
    # Ops diagnostics about an existing loop must not re-arm return-notify.
    if re.search(r"\b(loop|stuck|pinging|close[-\s]?out)\b", text, re.I):
        if not re.search(r"\b(new\s+(goal|collab|task)|start\s+(a\s+)?new)\b", text, re.I):
            return False

    def _mut(st: dict[str, Any]) -> bool:
        if not bool(get_room_collab_flags(st, room_id).get("lead_done")):
            return False
        set_room_lead_done(st, room_id, done=False)
        return True

    return bool(update_shared_state(_mut, path=path, env=env))


def summary_from_reply(reply_body: str | None, *, limit: int = 160) -> str:
    if not reply_body:
        return ""
    # Drop thought stream if present
    text = str(reply_body)
    if "\n\n" in text and text.lstrip().startswith("*Thoughts*"):
        parts = text.split("\n\n")
        # last non-empty chunk often final answer
        for part in reversed(parts):
            p = part.strip()
            if p and not p.startswith("*Thoughts*"):
                text = p
                break
    one = " ".join(text.split())
    if len(one) > limit:
        return one[: limit - 3] + "..."
    return one


# --- Soft peer delivery footer (optional) -------------------------------------

_FOOTER_LINE_RE = re.compile(
    r"^\s*(STATUS|FOR|EPOCH)\s*:\s*(.+?)\s*$",
    re.I | re.M,
)


def parse_peer_delivery_footer(text: str | None) -> dict[str, str] | None:
    """
    Parse optional soft footer lines:
      STATUS: done | blocked
      FOR: @grok
      EPOCH: <id>
    Returns dict of lower-case keys or None if no footer fields found.
    """
    if not text:
        return None
    found: dict[str, str] = {}
    for m in _FOOTER_LINE_RE.finditer(str(text)):
        found[m.group(1).lower()] = m.group(2).strip()
    return found or None


# --- Epoch / assignee bookkeeping (P1) ----------------------------------------


def open_collab_epoch(
    room_id: str,
    *,
    assignees: list[str] | set[str] | None = None,
    opened_by: str | None = None,
    mid: str | None = None,
    force: bool = False,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """
    Open or reuse a collab epoch for the room.

    Default (force=False): if the room already has an active epoch (epoch set
    and lead_done is false), **reuse** it and merge assignees — do not wipe
    the delivered map. force=True or lead_done/no-epoch opens a fresh epoch
    (clears delivered + lead_done).

    Returns epoch id string.
    """
    import time
    import uuid

    new_asg = {
        normalize_username(a)
        for a in (assignees or [])
        if normalize_username(a) in ALL_OPERATORS
    }

    def _mut(st: dict[str, Any]) -> str:
        rooms = st.setdefault("rooms", {})
        if not isinstance(rooms, dict):
            rooms = {}
            st["rooms"] = rooms
        rid = str(room_id)
        entry = dict(rooms.get(rid) or {})
        existing = entry.get("epoch")
        active = bool(existing) and not bool(entry.get("lead_done"))
        if active and not force:
            # Reuse: merge assignees; keep delivered
            prev = set(entry.get("assignees") or [])
            entry["assignees"] = sorted(prev | new_asg)
            rooms[rid] = entry
            return str(existing)
        epoch = f"e{int(time.time())}-{uuid.uuid4().hex[:8]}"
        entry["epoch"] = epoch
        entry["lead_done"] = False
        entry.pop("lead_done_at", None)
        entry.pop("lead_done_mid", None)
        if opened_by:
            entry["opened_by"] = normalize_username(opened_by)
        if mid:
            entry["opened_mid"] = mid
        entry["assignees"] = sorted(new_asg)
        entry["delivered"] = {}
        rooms[rid] = entry
        return epoch

    return str(update_shared_state(_mut, path=path, env=env))


def record_assignee_delivered(
    room_id: str,
    assignee: str,
    *,
    mid: str | None = None,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    # TODO(issue #2 P1): wire assignee_already_delivered into peer enqueue so
    # bookkeeping becomes enforcement (skip re-wake when delivered this epoch
    # unless explicit retry). Record alone is observability only.
    who = normalize_username(assignee)
    ts = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()

    def _mut(st: dict[str, Any]) -> None:
        rooms = st.setdefault("rooms", {})
        rid = str(room_id)
        entry = dict(rooms.get(rid) or {})
        # B2 hard gate: do not stamp delivered after lead DONE or for non-assignees.
        if entry.get("lead_done"):
            return
        assignees = {
            normalize_username(a)
            for a in (entry.get("assignees") or [])
            if normalize_username(a)
        }
        if who not in assignees:
            return
        delivered = dict(entry.get("delivered") or {})
        delivered[who] = {"mid": mid or "", "ts": ts}
        entry["delivered"] = delivered
        rooms[rid] = entry

    update_shared_state(_mut, path=path, env=env)


def assignee_already_delivered(
    room_id: str,
    assignee: str,
    *,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    st = load_shared_state(path=path, env=env)
    flags = get_room_collab_flags(st, room_id)
    delivered = flags.get("delivered") or {}
    if not isinstance(delivered, dict):
        return False
    return normalize_username(assignee) in delivered


def room_epoch(room_id: str, *, path: Path | None = None, env: Mapping[str, str] | None = None) -> str | None:
    st = load_shared_state(path=path, env=env)
    rooms = st.get("rooms") or {}
    entry = rooms.get(str(room_id)) or {}
    ep = entry.get("epoch")
    return str(ep) if ep else None


def extract_peer_assignees_from_text(text: str | None) -> list[str]:
    """Peer operators @-mentioned in text (for epoch open on lead kickoff)."""
    return sorted(extract_mention_usernames(text) & PEER_OPERATORS)


def health_multi_round_fields(
    room_id: str | None = None,
    *,
    path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Compact multi-round snapshot for health / status (P2 observability)."""
    st = load_shared_state(path=path, env=env)
    out: dict[str, Any] = {
        "multi_round_enabled": multi_round_enabled(env),
        "state_version": st.get("version"),
    }
    if room_id:
        rooms = st.get("rooms") or {}
        entry = dict(rooms.get(str(room_id)) or {})
        out["room"] = {
            "room_id": str(room_id),
            "lead_done": bool(entry.get("lead_done")),
            "epoch": entry.get("epoch"),
            "assignees": entry.get("assignees") or [],
            "delivered": list((entry.get("delivered") or {}).keys()),
        }
    return out
