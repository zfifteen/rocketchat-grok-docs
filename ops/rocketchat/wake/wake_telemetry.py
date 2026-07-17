#!/usr/bin/env python3
"""
NF-SPEC-02 Streaming Thinking telemetry — pure helpers.

No Rocket.Chat I/O. Unit-tested via golden wake-log fixtures.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Bubble phases (operator-owned)
PHASE_PLACEHOLDER = "PLACEHOLDER"
PHASE_RUNNING_META = "RUNNING_META"
PHASE_STREAMING_PARTIAL = "STREAMING_PARTIAL"
PHASE_FINAL_OK = "FINAL_OK"
PHASE_FINAL_ERR = "FINAL_ERR"

# RC chat.update rate-limits hard (HTTP 429). Thought mid-updates must stay sparse
# so FINAL chat.update is not starved. Live logs: 10–13 updates in ~20s → 429 on finalize.
DEFAULT_MIN_INTERVAL_MS = 2000
DEFAULT_MAX_UPDATES = 12
DEFAULT_MAX_CHARS = 3500
# Do not paint the first single token ("The") alone — wait for more text or a short delay.
DEFAULT_THOUGHT_FIRST_MIN_CHARS = 40
DEFAULT_THOUGHT_FIRST_WAIT_MS = 500
DEFAULT_THOUGHT_FLUSH_MS = 2000
# B4: gap between last non-final chat.update and FINAL (RC 429 mitigation).
DEFAULT_FINAL_COOL_S = 3.0
DEFAULT_FINAL_COOL_FLOOR_S = 1.0
DEFAULT_FINAL_COOL_CEIL_S = 8.0
# B5: per-room empty-reply retry cooldown.
DEFAULT_RETRY_COOLDOWN_S = 60.0


def wake_stream_enabled(env: dict[str, str] | None = None) -> bool:
    """
    RC_WAKE_STREAM: headless streaming-json + live thought bubble updates.

    Default **on** — intermediate agent bubble shows thought chunks; final still
    comes from the reply file. Set RC_WAKE_STREAM=0 for batch json only.
    """
    source = env if env is not None else os.environ
    raw = (source.get("RC_WAKE_STREAM") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def wake_meta_enabled(env: dict[str, str] | None = None) -> bool:
    """RC_WAKE_META: non-final Working… updates (default on)."""
    source = env if env is not None else os.environ
    raw = (source.get("RC_WAKE_META") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def stream_min_interval_ms(env: dict[str, str] | None = None) -> int:
    source = env if env is not None else os.environ
    try:
        return max(100, int((source.get("RC_STREAM_MIN_INTERVAL_MS") or str(DEFAULT_MIN_INTERVAL_MS)).strip()))
    except ValueError:
        return DEFAULT_MIN_INTERVAL_MS


def stream_max_updates(env: dict[str, str] | None = None) -> int:
    source = env if env is not None else os.environ
    try:
        return max(1, int((source.get("RC_STREAM_MAX_UPDATES") or str(DEFAULT_MAX_UPDATES)).strip()))
    except ValueError:
        return DEFAULT_MAX_UPDATES


def stream_max_chars(env: dict[str, str] | None = None) -> int:
    source = env if env is not None else os.environ
    try:
        return max(200, int((source.get("RC_STREAM_MAX_CHARS") or str(DEFAULT_MAX_CHARS)).strip()))
    except ValueError:
        return DEFAULT_MAX_CHARS


def final_cool_s(env: dict[str, str] | None = None) -> float:
    """RC_FINAL_COOL_S: min seconds between last non-final update and FINAL (B4)."""
    source = env if env is not None else os.environ
    try:
        v = float((source.get("RC_FINAL_COOL_S") or str(DEFAULT_FINAL_COOL_S)).strip())
    except ValueError:
        return DEFAULT_FINAL_COOL_S
    return max(DEFAULT_FINAL_COOL_FLOOR_S, min(DEFAULT_FINAL_COOL_CEIL_S, v))


def retry_cooldown_s(env: dict[str, str] | None = None) -> float:
    """RC_RETRY_COOLDOWN_S: min seconds between empty-reply retries per room (B5)."""
    source = env if env is not None else os.environ
    try:
        return max(0.0, float((source.get("RC_RETRY_COOLDOWN_S") or str(DEFAULT_RETRY_COOLDOWN_S)).strip()))
    except ValueError:
        return DEFAULT_RETRY_COOLDOWN_S


def wake_auto_retry_enabled(env: dict[str, str] | None = None) -> bool:
    """RC_WAKE_AUTO_RETRY: empty-reply auto-retry (default on)."""
    source = env if env is not None else os.environ
    raw = (source.get("RC_WAKE_AUTO_RETRY") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def stream_heartbeat_s(env: dict[str, str] | None = None) -> float:
    source = env if env is not None else os.environ
    try:
        return max(5.0, float((source.get("RC_STREAM_HEARTBEAT_S") or "15").strip()))
    except ValueError:
        return 15.0


def thought_first_min_chars(env: dict[str, str] | None = None) -> int:
    source = env if env is not None else os.environ
    try:
        return max(1, int((source.get("RC_THOUGHT_FIRST_MIN_CHARS") or str(DEFAULT_THOUGHT_FIRST_MIN_CHARS)).strip()))
    except ValueError:
        return DEFAULT_THOUGHT_FIRST_MIN_CHARS


def thought_first_wait_ms(env: dict[str, str] | None = None) -> int:
    source = env if env is not None else os.environ
    try:
        return max(50, int((source.get("RC_THOUGHT_FIRST_WAIT_MS") or str(DEFAULT_THOUGHT_FIRST_WAIT_MS)).strip()))
    except ValueError:
        return DEFAULT_THOUGHT_FIRST_WAIT_MS


def thought_flush_ms(env: dict[str, str] | None = None) -> int:
    """Background flusher interval for live thought bubble updates."""
    source = env if env is not None else os.environ
    try:
        return max(100, int((source.get("RC_THOUGHT_FLUSH_MS") or str(DEFAULT_THOUGHT_FLUSH_MS)).strip()))
    except ValueError:
        return DEFAULT_THOUGHT_FLUSH_MS


@dataclass
class WakeTerminal:
    """Parsed terminal fields from a wake-run log / JSON blob."""

    stop_reason: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    text_preview: str | None = None
    # Full headless `text` from the last JSON object that has one (may be long).
    text: str | None = None
    raw_objects: list[dict[str, Any]] = field(default_factory=list)


def parse_wake_terminal(log_text: str) -> WakeTerminal:
    """
    Best-effort parse of headless Grok wake stdout/log for stopReason etc.

    Handles:
    - Pretty-printed JSON object(s) with stopReason / sessionId
    - streaming-json style one JSON object per line
    - embedded "stopReason": "Cancelled" regex fallback
    """
    result = WakeTerminal()
    if not log_text:
        return result

    # Collect JSON objects from the log (skip leading "cmd: ..." line)
    objects: list[dict[str, Any]] = []
    # Whole-file JSON after first {
    brace = log_text.find("{")
    if brace >= 0:
        blob = log_text[brace:]
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(blob):
            while idx < len(blob) and blob[idx] in " \t\r\n":
                idx += 1
            if idx >= len(blob) or blob[idx] != "{":
                # skip to next brace
                nxt = blob.find("{", idx)
                if nxt < 0:
                    break
                idx = nxt
                continue
            try:
                obj, end = decoder.raw_decode(blob, idx)
                if isinstance(obj, dict):
                    objects.append(obj)
                idx = end
            except json.JSONDecodeError:
                idx += 1

    # Line-wise JSON (streaming-json)
    for line in log_text.splitlines():
        s = line.strip()
        if not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
            if isinstance(obj, dict) and obj not in objects:
                objects.append(obj)
        except json.JSONDecodeError:
            continue

    result.raw_objects = objects

    # Prefer last object that has stopReason
    for obj in reversed(objects):
        sr = obj.get("stopReason") or obj.get("stop_reason")
        if isinstance(sr, str) and sr.strip():
            result.stop_reason = sr.strip()
            break
    for obj in reversed(objects):
        sid = obj.get("sessionId") or obj.get("session_id")
        if isinstance(sid, str) and sid.strip():
            result.session_id = sid.strip()
            break
    for obj in reversed(objects):
        rid = obj.get("requestId") or obj.get("request_id")
        if isinstance(rid, str) and rid.strip():
            result.request_id = rid.strip()
            break
    for obj in reversed(objects):
        t = obj.get("text")
        if isinstance(t, str) and t.strip():
            full = t.strip()
            result.text = full
            result.text_preview = full[:200]
            break

    # streaming-json: assistant output arrives as many {"type":"text","data":...}
    # lines; the terminal "end" object has no "text" field. Reconstruct if needed.
    if not result.text:
        stream_parts: list[str] = []
        for obj in objects:
            if obj.get("type") == "text" and obj.get("data") is not None:
                stream_parts.append(str(obj.get("data") or ""))
        if stream_parts:
            full = "".join(stream_parts).strip()
            if full:
                result.text = full
                result.text_preview = full[:200]

    if not result.stop_reason:
        m = re.search(r'"stopReason"\s*:\s*"([^"]+)"', log_text)
        if m:
            result.stop_reason = m.group(1).strip()
        else:
            m2 = re.search(r"stopReason[=:]\s*([A-Za-z0-9_]+)", log_text)
            if m2:
                result.stop_reason = m2.group(1).strip()

    if not result.session_id:
        m = re.search(r'"sessionId"\s*:\s*"([^"]+)"', log_text)
        if m:
            result.session_id = m.group(1).strip()

    return result


def format_running_meta(
    *,
    room_name: str = "",
    cwd: str = "",
    approval_mode: str = "",
    phase: str = "running",
    elapsed_s: float = 0.0,
    session_short: str = "",
    extra_line: str = "",
    max_chars: int | None = None,
) -> str:
    """Non-final bubble body (Working… chrome). Must not look like FINAL_OK."""
    cwd_base = Path(cwd).name if cwd else ""
    lines = [
        "Working…",
        f"• room: {room_name or '(unknown)'}",
    ]
    if cwd_base:
        lines.append(f"• cwd: {cwd_base}")
    if approval_mode:
        lines.append(f"• mode: {approval_mode}")
    lines.append(f"• phase: {phase}")
    lines.append(f"• elapsed: {int(elapsed_s)}s")
    if session_short:
        lines.append(f"• session: {session_short}")
    if extra_line:
        lines.append(f"• {extra_line}")
    text = "\n".join(lines)
    limit = max_chars if max_chars is not None else DEFAULT_MAX_CHARS
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def format_final_err(
    *,
    rc: int | None,
    stop_reason: str | None,
    approval_mode: str = "",
    log_basename: str = "",
    hint: str | None = None,
    denials: list[str] | None = None,
    mid_short: str | None = None,
) -> str:
    """
    Structured FINAL_ERR for empty reply file (NF-SPEC-02 UX-S2 + IMP-22).

    Includes human one-liner, optional tools_blocked extract, rc, stopReason,
    approval_mode, log basename, optional mid short hash.
    """
    # Local import keeps module load light if wake_denials is mid-deploy.
    try:
        from wake_denials import (  # type: ignore
            elevation_hint_for_cancelled,
            format_denial_section,
        )
    except ImportError:  # pragma: no cover
        elevation_hint_for_cancelled = None  # type: ignore
        format_denial_section = lambda _d: []  # type: ignore

    one_liner = "(Wake did not produce a reply file.)"
    if rc is not None and rc != 0:
        one_liner = f"(Could not complete this reply; wake rc={rc}.)"
    elif stop_reason and stop_reason.lower() in ("cancelled", "canceled"):
        one_liner = "(Wake ended without a reply file — cancelled or incomplete turn.)"

    if hint is None:
        if stop_reason and stop_reason.lower() in ("cancelled", "canceled"):
            if callable(elevation_hint_for_cancelled):
                hint = elevation_hint_for_cancelled(
                    stop_reason=stop_reason,
                    approval_mode=approval_mode,
                )
            else:
                hint = (
                    "Headless tool approval cancelled or incomplete turn; "
                    "retry or elevate if needed."
                )
        elif rc is not None and rc != 0:
            hint = "Send another message to retry."
        else:
            hint = "The work may have failed silently — please retry."

    lines = [one_liner]
    # IMP-22 R1–R3: denials immediately under the one-liner (error-first).
    lines.extend(format_denial_section(denials))
    lines.extend(
        [
            f"stopReason: {stop_reason or 'unknown'}",
            f"rc: {rc if rc is not None else 'unknown'}",
            f"approval_mode: {approval_mode or 'unknown'}",
            f"hint: {hint}",
        ]
    )
    if log_basename:
        lines.append(f"log: {log_basename}")
    if mid_short:
        lines.append(f"mid: {mid_short}")
    return "\n".join(lines)


def truncate_nonfinal(text: str, max_chars: int | None = None) -> str:
    limit = max_chars if max_chars is not None else DEFAULT_MAX_CHARS
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


@dataclass
class StreamThrottle:
    """Rate limiter for non-final bubble updates (not applied to final)."""

    min_interval_ms: int = DEFAULT_MIN_INTERVAL_MS
    max_updates: int = DEFAULT_MAX_UPDATES
    updates: int = 0
    last_update_at: float = 0.0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "StreamThrottle":
        return cls(
            min_interval_ms=stream_min_interval_ms(env),
            max_updates=stream_max_updates(env),
        )

    def allow(self, *, now: float | None = None, force: bool = False) -> bool:
        """
        True if a non-final update may proceed.

        force=True: skip min-interval (e.g. first meta right after Thinking…);
        still respects max_updates.
        """
        t = time.monotonic() if now is None else now
        if self.updates >= self.max_updates:
            return False
        if self.updates > 0 and not force:
            elapsed_ms = (t - self.last_update_at) * 1000.0
            if elapsed_ms < self.min_interval_ms:
                return False
        self.updates += 1
        self.last_update_at = t
        return True

    def seconds_since_last(self, *, now: float | None = None) -> float:
        """Seconds since last non-final update; inf if none (B4)."""
        t = time.monotonic() if now is None else now
        # updates==0 is the only "never updated" signal — last_update_at may be 0.0
        # in pure tests that inject now=0.
        if self.updates == 0:
            return float("inf")
        return t - self.last_update_at

    def final_cool_remaining(self, cool_s: float, *, now: float | None = None) -> float:
        """Seconds to sleep before FINAL so RC rate window can clear (B4)."""
        elapsed = self.seconds_since_last(now=now)
        try:
            cool = float(cool_s)
        except (TypeError, ValueError):
            cool = DEFAULT_FINAL_COOL_S
        return max(0.0, cool - elapsed)


def redact_stream_secrets(text: str) -> str:
    """Lightweight redaction for partial stream text (no secrets in bubble)."""
    if not text:
        return text
    # Bearer / token-ish patterns
    out = re.sub(
        r"(?i)(authorization|x-auth-token|api[_-]?key|token)\s*[:=]\s*\S+",
        r"\1: [redacted]",
        text,
    )
    out = re.sub(r"sk-[A-Za-z0-9]{10,}", "[redacted-key]", out)
    return out


# Initial non-final bubble when no thought text yet (matches wake_lib).
ACTIVITY_PLACEHOLDER = "…"


def parse_streaming_json_line(line: str) -> dict[str, Any] | None:
    """
    Parse one NDJSON line from headless --output-format streaming-json.

    Returns None for blank lines, log noise, or invalid JSON.
    """
    raw = (line or "").strip()
    if not raw or raw[0] != "{":
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def format_thought_intermediate(
    thought: str,
    *,
    max_chars: int | None = None,
    empty: str = ACTIVITY_PLACEHOLDER,
) -> str:
    """
    User-visible intermediate bubble body from accumulated thought text.

    Keeps the *tail* when over max_chars so the latest reasoning stays visible.
    Does not include tool calls or final answer text.
    """
    t = redact_stream_secrets((thought or "").strip())
    if not t:
        return empty
    limit = max_chars if max_chars is not None else stream_max_chars()
    if len(t) <= limit:
        return t
    # Prefer newest reasoning when the buffer is long.
    return "…" + t[-(limit - 1) :]


@dataclass
class ThoughtAccumulator:
    """Concatenate streaming-json thought chunks for the intermediate bubble."""

    text: str = ""

    def consume_event(self, event: dict[str, Any] | None) -> bool:
        """
        Apply one stream event. Returns True if thought text changed.
        """
        if not event or event.get("type") != "thought":
            return False
        chunk = event.get("data")
        if chunk is None:
            return False
        piece = str(chunk)
        if not piece:
            return False
        self.text += piece
        return True

    def format(self, *, max_chars: int | None = None) -> str:
        return format_thought_intermediate(self.text, max_chars=max_chars)


# Minimum length for salvaging headless JSON `text` when the reply file is empty.
# Short mid-turn monologues (e.g. "Investigating…") stay FINAL_ERR.
# IMP-23 S2: delegate thresholds to wake_ux_imp23 (Cancelled mid-length salvage).
SALVAGE_MIN_CHARS = 80


def is_salvageable_wake_text(
    text: str | None,
    *,
    stop_reason: str | None = None,
) -> bool:
    """
    True when headless wake `text` is usable as a user-facing answer.

    Rejects empty / tiny progress monologues. Accepts structured bullets or
    longer substantive paragraphs (common when stopReason=Cancelled after tools).
    IMP-23: Cancelled mid-length unstructured text (≥80) is salvageable.
    """
    try:
        from wake_ux_imp23 import is_salvageable_wake_text as _imp23

        return _imp23(text, stop_reason=stop_reason)
    except ImportError:  # pragma: no cover
        t = (text or "").strip()
        if len(t) < SALVAGE_MIN_CHARS:
            return False
        if re.search(r"(?m)^\s*[-*•]", t) or re.search(r"(?m)^\s*#{1,3}\s+\S", t):
            return True
        if "**" in t or "```" in t:
            return True
        if len(t) >= 120:
            return True
        sr = (stop_reason or "").strip().lower()
        if sr in ("cancelled", "canceled") and len(t) >= SALVAGE_MIN_CHARS:
            return True
        return False


def extract_salvageable_body(
    text: str | None,
    *,
    stop_reason: str | None = None,
) -> str | None:
    """
    Return cleaned salvage body from headless `text`, or None if not salvageable.

    If a trailing bullet/heading block exists, prefer that (often the final report
    after tool thrash monologue). Otherwise return the full text when salvageable.
    """
    try:
        from wake_ux_imp23 import extract_salvageable_body as _imp23

        return _imp23(text, stop_reason=stop_reason)
    except ImportError:  # pragma: no cover
        t = (text or "").strip()
        if not t:
            return None
        lines = t.splitlines()
        start = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*[-*•]\s+\S", line) or re.match(r"^\s*#{1,3}\s+\S", line):
                start = i
                break
        candidate = t
        if start is not None:
            tail = "\n".join(lines[start:]).strip()
            if is_salvageable_wake_text(tail, stop_reason=stop_reason):
                candidate = tail
        if not is_salvageable_wake_text(candidate, stop_reason=stop_reason):
            return None
        return candidate


def choose_final_body(
    *,
    reply_file_body: str,
    rc: int | None,
    log_text: str = "",
    approval_mode: str = "",
    log_basename: str = "",
    compose_ok,  # callable str -> str (compose_unified_reply)
    mid_short: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, str, WakeTerminal]:
    """
    FINAL_OK vs FINAL_ERR decision.

    Order:
      1) non-empty reply file → FINAL_OK (+ optional tools_blocked footer, IMP-22 R8)
      2) salvageable headless JSON `text` (e.g. Cancelled with content) → FINAL_OK
      3) structured FINAL_ERR with denial extract (never leave Thinking placeholder)

    Returns (final_body, phase, terminal).
    """
    try:
        from wake_denials import (  # type: ignore
            append_denial_footer,
            denial_footer_enabled,
            extract_tool_denials,
        )
    except ImportError:  # pragma: no cover
        extract_tool_denials = lambda _t, max_items=3: []  # type: ignore
        append_denial_footer = lambda b, _d: b  # type: ignore
        denial_footer_enabled = lambda _e=None: False  # type: ignore

    terminal = parse_wake_terminal(log_text)
    denials = extract_tool_denials(log_text)
    body = (reply_file_body or "").strip()
    if body:
        composed = compose_ok(body)
        if denials and denial_footer_enabled(env):
            composed = append_denial_footer(composed, denials)
        return composed, PHASE_FINAL_OK, terminal

    # IMP-23 S2: pass stop_reason so Cancelled mid-length stream text salvages.
    salvaged = extract_salvageable_body(
        terminal.text, stop_reason=terminal.stop_reason
    )
    if salvaged:
        # Silent salvage: principal sees the answer only. Operator may still
        # auto-retry Cancelled+empty-reply-file (rc_operator_agent) before this
        # path becomes the final post. Do not append a "recovered" footnote —
        # that read as an error loop in chat (principal 2026-07-16).
        composed = compose_ok(salvaged)
        if denials and denial_footer_enabled(env):
            composed = append_denial_footer(composed, denials)
        return composed, PHASE_FINAL_OK, terminal

    err = format_final_err(
        rc=rc,
        stop_reason=terminal.stop_reason,
        approval_mode=approval_mode,
        log_basename=log_basename,
        denials=denials,
        mid_short=mid_short,
    )
    return err, PHASE_FINAL_ERR, terminal
