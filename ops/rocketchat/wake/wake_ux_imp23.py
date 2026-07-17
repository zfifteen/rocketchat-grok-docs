#!/usr/bin/env python3
"""IMP-23 pure helpers: S1 rate-limit backoff, S2 salvage/retry gates, S7 cwd.

No Rocket.Chat I/O. Safe to unit-test and mirror under docs-repo ops/rocketchat/wake/.
Runtime also loads from ~/.grok/agency/ops/rocketchat/wake/ when deployed.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Mapping

# --- S2 salvage thresholds (Cancelled empty-reply UX) ---
# Short progress monologues stay unsalvageable; structured / long / Cancelled
# partial answers become FINAL_OK so we avoid empty-reply re-wake churn.
SALVAGE_MIN_CHARS = 80
SALVAGE_LONG_CHARS = 120  # was 200 — many Cancelled stream answers are mid-length
SALVAGE_CANCELLED_MIN_CHARS = 80

# --- S1 cross-process / local 429 backoff ---
DEFAULT_429_BACKOFF_S = 6.0
DEFAULT_429_BACKOFF_MAX_S = 32.0

# Redact key: value through end of line so "Authorization: Bearer <jwt>" cannot
# leave the token after a single \S+ match. Also catch sk-… API key shapes.
_SECRET_LIKE = re.compile(
    r"(?i)(?:(authorization|x-auth-token|api[_-]?key|token)\s*[:=]\s*.+|sk-[A-Za-z0-9]{10,})"
)


def _env_float(source: Mapping[str, str], key: str, default: float, *, floor: float = 0.0) -> float:
    try:
        v = float((source.get(key) or str(default)).strip())
    except (TypeError, ValueError):
        return default
    return max(floor, v)


# ---------------------------------------------------------------------------
# Phase 1 scaffold — signatures + logic comments only until Phase 3 fills bodies
# (Implemented immediately below after Phase 2 review — single authoring pass
# kept in one module for PR reviewability.)
# ---------------------------------------------------------------------------


def is_salvageable_wake_text(
    text: str | None,
    *,
    stop_reason: str | None = None,
) -> bool:
    """True when headless/stream text is good enough as a user-facing answer (S2).

    Logic:
    - empty / < SALVAGE_MIN_CHARS → False
    - markdown structure (bullets, headings, bold, fences) → True
    - len >= SALVAGE_LONG_CHARS → True
    - stopReason Cancelled and len >= SALVAGE_CANCELLED_MIN_CHARS → True
      (Cancelled often streams a partial but usable answer)
    """
    t = (text or "").strip()
    if len(t) < SALVAGE_MIN_CHARS:
        return False
    if re.search(r"(?m)^\s*[-*•]", t) or re.search(r"(?m)^\s*#{1,3}\s+\S", t):
        return True
    if "**" in t or "```" in t:
        return True
    if len(t) >= SALVAGE_LONG_CHARS:
        return True
    sr = (stop_reason or "").strip().lower()
    if sr in ("cancelled", "canceled") and len(t) >= SALVAGE_CANCELLED_MIN_CHARS:
        return True
    return False


def extract_salvageable_body(
    text: str | None,
    *,
    stop_reason: str | None = None,
) -> str | None:
    """Clean salvage body, or None (S2).

    Prefer a *trailing* structured section when present:
    - last markdown heading (``#`` / ``##`` / ``###``) through EOF, else
    - start of the last contiguous bullet list (blank lines allowed inside).
    Otherwise keep the full text when it is salvageable.
    """
    t = (text or "").strip()
    if not t:
        return None
    lines = t.splitlines()
    last_heading: int | None = None
    last_bullet_run_start: int | None = None
    bullet_run: int | None = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*#{1,3}\s+\S", line):
            last_heading = i
            bullet_run = None
            continue
        if re.match(r"^\s*[-*•]\s+\S", line):
            if bullet_run is None:
                bullet_run = i
            last_bullet_run_start = bullet_run
            continue
        # Non-empty prose breaks an open bullet run (blank lines do not).
        if line.strip():
            bullet_run = None
    start: int | None = None
    if last_heading is not None:
        start = last_heading
    elif last_bullet_run_start is not None:
        start = last_bullet_run_start
    candidate = t
    if start is not None:
        tail = "\n".join(lines[start:]).strip()
        if is_salvageable_wake_text(tail, stop_reason=stop_reason):
            candidate = tail
    if not is_salvageable_wake_text(candidate, stop_reason=stop_reason):
        return None
    # Light redaction — never put raw tokens in the bubble.
    return _SECRET_LIKE.sub("[redacted]", candidate)


def should_skip_empty_reply_retry(
    *,
    phase: str,
    reply_file_empty: bool,
    stop_reason: str | None,
    rc: int | None,
    already_retry: bool,
    auto_retry_enabled: bool = True,
    stream_text: str | None = None,
) -> bool:
    """True when operator must NOT schedule empty-reply recovery (S2).

    Skip retry when:
    - auto retry off, or already a retry, or reply file not empty
    - phase already FINAL_OK (stream salvage succeeded)
    - stopReason not Cancelled / rc != 0
    - strong salvageable stream_text available (finalize that instead of re-wake)
    """
    if not auto_retry_enabled or already_retry or not reply_file_empty:
        return True
    phase_u = (phase or "").strip().upper()
    if phase_u in ("FINAL_OK", "PHASE_FINAL_OK", "OK"):
        return True
    sr = (stop_reason or "").strip().lower()
    if sr not in ("cancelled", "canceled"):
        return True
    if rc is not None and rc != 0:
        return True
    if extract_salvageable_body(stream_text, stop_reason=stop_reason):
        return True
    return False


def validate_wake_cwd(path: str | Path | None) -> tuple[bool, str]:
    """S7: (ok, reason). ok False when path set but missing/not a directory."""
    if path is None:
        return True, "default"
    raw = str(path).strip()
    if not raw:
        return True, "default"
    p = Path(raw).expanduser()
    try:
        resolved = p.resolve(strict=False)
    except OSError as e:
        return False, f"cwd unresolvable: {e}"
    if not resolved.exists():
        return False, f"cwd missing: {resolved}"
    if not resolved.is_dir():
        return False, f"cwd not a directory: {resolved}"
    return True, "ok"


def format_missing_cwd_err(path: str | Path, *, mid_short: str | None = None) -> str:
    """Bubble body for S7 missing/invalid cwd FINAL_ERR."""
    lines = [
        "(Could not start wake — project cwd is missing or invalid.)",
        f"cwd: {path}",
        "hint: re-pin with !cwd or fix the room project path.",
        "stopReason: cwd_missing",
        "rc: -",
    ]
    if mid_short:
        lines.append(f"mid: {mid_short}")
    return "\n".join(lines)


class RateLimitBackoff:
    """S1: local backoff after HTTP 429 so non-final updates yield to FINAL.

    Usage: call note_429() when chat.update returns 429; allow_nonfinal() is
    False until backoff elapses. FINAL path should still proceed (with cool-down).
    """

    def __init__(
        self,
        *,
        base_s: float = DEFAULT_429_BACKOFF_S,
        max_s: float = DEFAULT_429_BACKOFF_MAX_S,
    ) -> None:
        self.base_s = base_s
        self.max_s = max_s
        self.strikes = 0
        self.blocked_until = 0.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RateLimitBackoff":
        source = env if env is not None else os.environ
        base = _env_float(source, "RC_429_BACKOFF_S", DEFAULT_429_BACKOFF_S, floor=1.0)
        mx = _env_float(source, "RC_429_BACKOFF_MAX_S", DEFAULT_429_BACKOFF_MAX_S, floor=base)
        return cls(base_s=base, max_s=mx)

    def note_429(self, *, now: float | None = None) -> float:
        """Record a 429; return seconds to wait before next non-final update."""
        t = time.monotonic() if now is None else now
        self.strikes += 1
        wait = min(self.max_s, self.base_s * (2 ** max(0, self.strikes - 1)))
        self.blocked_until = t + wait
        return wait

    def note_success(self) -> None:
        """Clear strikes after a successful update."""
        self.strikes = 0
        self.blocked_until = 0.0

    def allow_nonfinal(self, *, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else now
        return t >= self.blocked_until

    def remaining(self, *, now: float | None = None) -> float:
        t = time.monotonic() if now is None else now
        return max(0.0, self.blocked_until - t)


def cross_process_update_wait(
    bucket_path: Path | str,
    *,
    min_gap_s: float = 0.35,
    now: float | None = None,
) -> float:
    """S4-lite: file mtime token bucket. Returns seconds caller should sleep.

    Pass the *same* path on every operator (use ``default_shared_update_bucket()``).
    Per-operator ``LOG_DIR/rc-update.bucket`` is only a local gap, not host-wide.
    """
    path = Path(bucket_path)
    t = time.time() if now is None else now
    try:
        if path.is_file():
            age = t - path.stat().st_mtime
            if age < min_gap_s:
                return min_gap_s - age
    except OSError:
        return 0.0
    return 0.0


def cross_process_update_touch(bucket_path: Path | str, *, now: float | None = None) -> None:
    """Record that an update was attempted (best-effort)."""
    path = Path(bucket_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(time.time() if now is None else now), encoding="utf-8")
    except OSError:
        pass


def default_shared_update_bucket() -> Path:
    """Canonical host-wide S4 bucket — every operator process must share this path.

    Live wire must NOT use per-bot ``LOG_DIR / rc-update.bucket`` if the goal is
    a room/host-wide chat.update budget. Override with env ``RC_UPDATE_BUCKET``
    when set (absolute or ~-expandable path).
    """
    raw = (os.environ.get("RC_UPDATE_BUCKET") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "logs" / "rocketchat-shared" / "rc-update.bucket"


def final_cool_sleep_s(
    cool_remaining: float,
    *,
    floor_s: float = 1.0,
    ceil_s: float = 8.0,
) -> float:
    """Clamp B4 cool-down for finalize_thinking_message (S1)."""
    try:
        v = float(cool_remaining)
    except (TypeError, ValueError):
        v = floor_s
    return max(floor_s, min(ceil_s, v))
