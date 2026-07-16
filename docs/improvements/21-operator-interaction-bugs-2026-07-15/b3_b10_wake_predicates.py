#!/usr/bin/env python3
"""Proposed pure wake predicates for B3 (stream/activity) + B10 (prose @bot).

Port target (runtime):
  ~/.grok/agency/ops/rocketchat/wake/wake_lib.py  (message_mentions / should_enqueue)
  ~/.grok/agency/ops/rocketchat/wake/rc_multi_round_collab.py  (principal_multi_mention_lead_only)

This module is intentionally self-contained so unit tests run without secrets
or the live operator process. Lead should wire helpers into wake_lib after
review — do not assume this file is imported by launchd yet.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

ACTIVITY_PLACEHOLDER = "…"
THINKING_PLACEHOLDER = "Thinking..."

ALL_OPERATORS = frozenset({"grok", "hermes", "agy", "claude"})
PEER_OPERATORS = frozenset({"hermes", "agy", "claude"})
GROK_LEAD = "grok"
PRINCIPAL_DEFAULT = "principal"

# Same surface as wake_lib / rc_multi_round_collab today.
_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9._-]+)\b")

# Thought-stream / recovery chrome that is not a final assign.
_STREAM_SHELL_RES = (
    re.compile(r"^\s*\*Thoughts?\*\s*", re.I),
    re.compile(r"^\s*Thinking\b", re.I),
    re.compile(r"^\s*Recovery wake\b", re.I),
    re.compile(r"^\s*PHASE\s*[:=]", re.I),
)

# Intentional assign verbs after @op (lead/peer tasking language).
_ASSIGN_VERB_RE = re.compile(
    r"@([A-Za-z0-9._-]+)\b\s+"
    r"(?:please\s+)?"
    r"(?:dig|own|fix|trace|run|do|check|write|propose|add|test|handle|"
    r"implement|review|pressure-test|pressure_test|take|cover|look|"
    r"investigate|deliver|spec|patch|report)\b",
    re.I,
)

_COLLAB_RETURN_TEMPLATE_RE = re.compile(
    r"(?<!\w)@([A-Za-z0-9._-]+)\s+collab-return\s+from\s+`?([A-Za-z0-9._-]+)`?",
    re.I,
)


def normalize_username(raw: str | None) -> str:
    return (raw or "").strip().lower()


def extract_mention_usernames(text: str | None) -> set[str]:
    """Text-only @mentions (current operator physics)."""
    if not text:
        return set()
    return {m.group(1).lower() for m in _MENTION_RE.finditer(text)}


def extract_structured_mention_usernames(msg: Mapping[str, Any] | None) -> set[str]:
    """Rocket.Chat structured mentions[] usernames."""
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


def extract_all_mention_usernames(
    msg: Mapping[str, Any] | None,
    text: str | None = None,
) -> set[str]:
    """Union of structured + text mentions (what message_mentions_operator uses)."""
    body = text if text is not None else ((msg or {}).get("msg") or "")
    return extract_structured_mention_usernames(msg) | extract_mention_usernames(
        body if isinstance(body, str) else ""
    )


def is_activity_or_stream_shell(text: str | None) -> bool:
    """True for empty / placeholder / pure intermediate chrome with no assign body.

    B3: activity bubble ``…`` and early thought shells must never enqueue peers.
    """
    raw = (text or "").strip()
    if not raw:
        return True
    if raw in {ACTIVITY_PLACEHOLDER, THINKING_PLACEHOLDER, "...", "…"}:
        return True
    # Single-line pure chrome
    if raw in {"Thinking…", "thinking..."}:
        return True
    return False


def looks_like_nonfinal_stream(text: str | None) -> bool:
    """Heuristic: intermediate thought stream, not a final assign post.

    chat.update reuses one mid; stream-room-messages redelivers the same mid
    with growing body. Early bodies often start with *Thoughts* / Thinking.
    """
    raw = (text or "").strip()
    if not raw:
        return True
    if is_activity_or_stream_shell(raw):
        return True
    head = raw[:240]
    for cre in _STREAM_SHELL_RES:
        if cre.search(head):
            # Still allow if the same body also has a hard assign line — rare.
            if intentional_line_start_mentions(raw):
                return False
            return True
    return False


def intentional_line_start_mentions(text: str | None) -> set[str]:
    """@op at the start of any line → intentional address."""
    if not text:
        return set()
    found: set[str] = set()
    for line in str(text).splitlines():
        m = re.match(r"^\s*@([A-Za-z0-9._-]+)\b", line)
        if m:
            found.add(m.group(1).lower())
    return found


def intentional_assign_verb_mentions(text: str | None) -> set[str]:
    """@op followed by task verb → intentional assign."""
    if not text:
        return set()
    return {m.group(1).lower() for m in _ASSIGN_VERB_RE.finditer(text)}


def collab_return_targets(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        m.group(1).lower()
        for m in _COLLAB_RETURN_TEMPLATE_RE.finditer(text)
    }


def intentional_operator_mentions(text: str | None) -> set[str]:
    """Mentions that should be allowed to wake when author is a bot."""
    return (
        intentional_line_start_mentions(text)
        | intentional_assign_verb_mentions(text)
        | collab_return_targets(text)
    )


def message_mentions_operator_literal(
    msg: Mapping[str, Any] | None,
    operator: str,
    *,
    text: str | None = None,
) -> bool:
    """Current wake_lib behavior: any structured or text @op."""
    op = normalize_username(operator)
    if not op:
        return False
    return op in extract_all_mention_usernames(msg, text=text)


def message_mentions_operator_intentional(
    msg: Mapping[str, Any] | None,
    operator: str,
    *,
    text: str | None = None,
    author: str | None = None,
    principal: str = PRINCIPAL_DEFAULT,
) -> bool:
    """B10-aware mention check.

    - Principal (or unknown human): keep literal any-@op (channel tag-to-talk).
    - Bot operators: only intentional @op (line-start, assign verb, collab-return).
      Structured mentions[] alone are **not** enough when the text only has
      prose mid-sentence @op (avoids RC autocomplete ghosts + B10).
    """
    op = normalize_username(operator)
    if not op:
        return False
    body = text if text is not None else ((msg or {}).get("msg") or "")
    body_s = body if isinstance(body, str) else ""
    author_u = normalize_username(author)
    if not author_u:
        author_u = normalize_username(((msg or {}).get("u") or {}).get("username"))

    if author_u not in ALL_OPERATORS:
        # Humans (principal / others): literal path.
        return message_mentions_operator_literal(msg, op, text=body_s)

    # Bot-authored: intentional text shapes only.
    return op in intentional_operator_mentions(body_s)


def should_enqueue_llm_wake_proposed(
    msg: dict,
    *,
    operator: str,
    principal: str = PRINCIPAL_DEFAULT,
    last_seen_id: str | None = None,
    processed_ids: list[str] | None = None,
    room_type: str | None = None,
    require_mention_in_shared: bool = True,
    peer_tag_wake: bool = True,
    text: str | None = None,
) -> bool:
    """Proposed full enqueue predicate (pure; mirrors wake_lib + B3/B10 gates).

    Not a drop-in of every env flag — enough for unit kill cases.
    """
    mid = msg.get("_id")
    if not mid:
        return False
    user = normalize_username(((msg.get("u") or {}).get("username")))
    op = normalize_username(operator)
    if not user or not op:
        return False
    if user == op:
        return False  # never self
    if last_seen_id == mid:
        return False
    if processed_ids and mid in processed_ids:
        return False

    body = text if text is not None else (msg.get("msg") or "")
    body_s = (body if isinstance(body, str) else "").strip()
    has_files = bool(msg.get("file") or msg.get("files") or msg.get("attachments"))
    if not body_s and not has_files:
        return False

    # B3 shell: pure activity / thinking placeholder never wakes.
    if body_s and is_activity_or_stream_shell(body_s) and not has_files:
        return False

    is_principal = user == normalize_username(principal)
    shared = (room_type or "").strip().lower() in {"c", "p"}

    if is_principal:
        if require_mention_in_shared and shared:
            return message_mentions_operator_literal(msg, op, text=body_s)
        return True

    if not peer_tag_wake:
        return False

    # B3: bot author intermediate stream chrome → no peer enqueue.
    if user in ALL_OPERATORS and looks_like_nonfinal_stream(body_s):
        return False

    # B10: bot authors need intentional @op; humans use literal.
    return message_mentions_operator_intentional(
        msg, op, text=body_s, author=user, principal=principal
    )


def principal_multi_mention_lead_only_proposed(
    *,
    author: str,
    operator: str,
    text: str | None,
    room_type: str | None,
    msg: Mapping[str, Any] | None = None,
    principal: str = PRINCIPAL_DEFAULT,
    lead: str = GROK_LEAD,
    enabled: bool = True,
) -> bool:
    """B1-hardened lead-only gate using structured+text mentions.

    Current runtime only scans text regex — glued ``@grok@hermes`` loses peer
    tokens, and structured mentions[] are ignored. Peers can still enqueue via
    mentions[] in should_enqueue while lead-only thinks only lead was tagged.
    """
    if not enabled:
        return False
    if (room_type or "").strip().lower() not in {"c", "p"}:
        return False
    if normalize_username(author) != normalize_username(principal):
        return False
    op = normalize_username(operator)
    lead_u = normalize_username(lead) or GROK_LEAD
    if not op or op == lead_u:
        return False
    mentions = extract_all_mention_usernames(msg, text=text)
    # Also split glued tokens: @grok@hermes → try secondary scan
    mentions |= _extract_glued_mentions(text)
    if lead_u not in mentions:
        return False  # principal → peer direct OK
    if not (mentions & PEER_OPERATORS):
        return False
    return op in PEER_OPERATORS


def _extract_glued_mentions(text: str | None) -> set[str]:
    """Recover peers from glued forms like @grok@hermes@agy.

    Standard \\b after grok sees the next @ as a boundary for the first token
    only; subsequent @tokens fail (?<!\\w) because the previous char is wordish
    for some clients, or simply only the first match is human-intended glue.
    Scan with a looser splitter on runs of @name.
    """
    if not text:
        return set()
    # Find runs: @a@b@c
    out: set[str] = set()
    for run in re.finditer(r"(?:@([A-Za-z0-9._-]+))+", text):
        chunk = run.group(0)
        out.update(m.lower() for m in re.findall(r"@([A-Za-z0-9._-]+)", chunk))
    return out


__all__ = [
    "is_activity_or_stream_shell",
    "looks_like_nonfinal_stream",
    "intentional_operator_mentions",
    "message_mentions_operator_literal",
    "message_mentions_operator_intentional",
    "should_enqueue_llm_wake_proposed",
    "principal_multi_mention_lead_only_proposed",
    "extract_all_mention_usernames",
    "_extract_glued_mentions",
]
