#!/usr/bin/env python3
"""IMP-22: extract tool/permission denials from wake logs for FINAL_ERR UX.

Pure helpers — safe to unit-test without Rocket.Chat or secrets.
Mirrored under agency ops wake/ and docs-repo ops/rocketchat/wake/.
"""

from __future__ import annotations

import os
import re
from typing import Mapping

# Cap denial lines shown in the RC bubble (R2).
DEFAULT_MAX_DENIALS = 3

# Patterns that usually mean a tool was blocked rather than a soft model refusal.
_DENIAL_LINE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"BLOCKED\b.*", re.I),
    re.compile(r"User denied this (?:command|action|tool)\b.*", re.I),
    re.compile(r"(?:tool|command|action)\s+(?:was\s+)?denied\b.*", re.I),
    re.compile(r"permission(?:s)?\s+denied\b.*", re.I),
    re.compile(r"not (?:authorized|permitted) (?:to|for)\b.*", re.I),
    re.compile(r"requires?\s+(?:approval|confirmation|--yolo)\b.*", re.I),
    re.compile(r"approval (?:required|needed|rejected|cancelled)\b.*", re.I),
    re.compile(r"--permission-mode\b.*(?:denied|reject|cancel).*", re.I),
    re.compile(r"acceptEdits\b.*(?:denied|cancel|block).*", re.I),
    re.compile(
        r"(?:write_file|read_file|terminal|patch|execute_code|shell)\b[^\n]{0,120}"
        r"(?:denied|blocked|rejected|not allowed|cancelled)",
        re.I,
    ),
    re.compile(
        r"(?:denied|blocked|rejected)[^\n]{0,80}"
        r"(?:write_file|read_file|terminal|patch|execute_code|shell)",
        re.I,
    ),
    re.compile(r"dangerously-skip-permissions.*(?:fail|denied|error).*", re.I),
)

_SECRET_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"gho_[A-Za-z0-9]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{10,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)(password|token|secret|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"/Users/[^/\s]+/\.grok/agency/secrets/[^\s]+"),
    re.compile(r"/Users/[^/\s]+/\.hermes/[^\s]*\.env"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"),
)

_TOOL_NAME_RE = re.compile(
    r"\b(write_file|read_file|terminal|patch|execute_code|shell|"
    r"web_search|web_extract|browser_\w+|skill_\w+|delegate_task|"
    r"search_files|todo|memory|gh|git)\b",
    re.I,
)


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


def denial_footer_enabled(env: Mapping[str, str] | None = None) -> bool:
    """RC_WAKE_DENIAL_FOOTER — default ON (R8)."""
    source = env if env is not None else os.environ
    return _env_flag(source.get("RC_WAKE_DENIAL_FOOTER"), default=True)


def redact_secrets(text: str) -> str:
    """Strip common secret shapes from a single denial line."""
    out = text or ""
    for cre in _SECRET_RES:
        out = cre.sub("[redacted]", out)
    # Collapse home paths a bit without leaking username+secret path combos
    out = re.sub(r"/Users/[^/\s]+/", "~/…/", out)
    return out


def _normalize_denial_line(raw: str) -> str:
    line = " ".join((raw or "").strip().split())
    if len(line) > 180:
        line = line[:177] + "..."
    return redact_secrets(line)


def _dedupe_key(line: str) -> str:
    tools = tuple(sorted({m.group(1).lower() for m in _TOOL_NAME_RE.finditer(line)}))
    if tools:
        return "tools:" + ",".join(tools)
    # Fallback: first 80 chars lower
    return re.sub(r"\s+", " ", line.lower())[:80]


def extract_tool_denials(
    log_text: str | None,
    *,
    max_items: int = DEFAULT_MAX_DENIALS,
) -> list[str]:
    """
    Return up to max_items distinct denial one-liners from a wake log (R1–R4).

    Empty input → []. Order is first-seen in the log (stable).
    """
    if not log_text or not str(log_text).strip():
        return []
    if max_items < 1:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for line in str(log_text).splitlines():
        s = line.strip()
        if not s or len(s) < 8:
            continue
        matched = False
        for cre in _DENIAL_LINE_RES:
            m = cre.search(s)
            if not m:
                continue
            # Prefer the match span when the whole line is huge noise
            chunk = m.group(0) if len(s) > 200 else s
            norm = _normalize_denial_line(chunk)
            key = _dedupe_key(norm)
            if key in seen:
                matched = True
                break
            seen.add(key)
            found.append(norm)
            matched = True
            break
        if matched and len(found) >= max_items:
            break
    return found


def format_denial_section(denials: list[str] | None) -> list[str]:
    """Lines to insert under FINAL_ERR (or empty)."""
    if not denials:
        return []
    out = ["tools_blocked:"]
    for d in denials:
        out.append(f"  - {d}")
    return out


def append_denial_footer(body: str, denials: list[str] | None) -> str:
    """R8: short footer when reply exists but tools were blocked."""
    if not denials:
        return body
    names: list[str] = []
    for d in denials:
        for m in _TOOL_NAME_RE.finditer(d):
            n = m.group(1)
            if n not in names:
                names.append(n)
    if names:
        foot = "Tools blocked: " + ", ".join(names)
    else:
        foot = "Tools blocked: " + "; ".join(denials[:2])
    base = (body or "").rstrip()
    if not base:
        return foot
    if foot in base:
        return base
    return base + "\n\n" + foot


def elevation_hint_for_cancelled(
    *,
    stop_reason: str | None,
    approval_mode: str = "",
    default_hint: str | None = None,
) -> str | None:
    """R10: concrete elevate path on permission-like Cancelled in restricted mode."""
    sr = (stop_reason or "").lower()
    mode = (approval_mode or "").strip().lower()
    if sr not in ("cancelled", "canceled"):
        return default_hint
    if mode and mode not in ("restricted", "restrict", "safe", "auto"):
        return default_hint
    return (
        "Headless tool approval cancelled or incomplete turn. "
        "On a channel (restricted), elevate via DM admin / `!mode`, or retry; "
        "see wake log for tools_blocked lines."
    )


__all__ = [
    "DEFAULT_MAX_DENIALS",
    "append_denial_footer",
    "denial_footer_enabled",
    "elevation_hint_for_cancelled",
    "extract_tool_denials",
    "format_denial_section",
    "redact_secrets",
]
