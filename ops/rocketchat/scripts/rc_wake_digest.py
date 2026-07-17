#!/usr/bin/env python3
"""IMP-23 S14: wake/response digest across operator log dirs.

Counts only log lines whose leading ISO timestamp falls within the window
(default last 24h). Operator lines look like:
  [2026-07-09T12:48:32Z] finalize … phase=FINAL_OK …

Usage:
  python3 ops/rocketchat/scripts/rc_wake_digest.py
  python3 ~/.grok/agency/ops/rocketchat/scripts/rc_wake_digest.py --hours 48
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_ROOT = Path.home() / "logs"
BOTS = (
    ("grok", "rocketchat-dm-wake"),
    ("hermes", "rocketchat-hermes-wake"),
    ("agy", "rocketchat-agy-wake"),
    ("nie", "rocketchat-nie-wake"),
    ("feynman", "rocketchat-feynman-wake"),
)

# Leading [ISO8601] stamp used by rc_operator_agent log().
_LINE_TS = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)\]"
)


def _line_epoch(line: str) -> float | None:
    """Parse leading [ISO] timestamp to epoch seconds, or None if missing/bad."""
    m = _LINE_TS.match(line)
    if not m:
        return None
    raw = m.group(1)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _count(path: Path, pattern: str, *, since: float) -> int:
    """Count regex matches on timestamped lines with ts >= since (tail-capped)."""
    if not path.is_file():
        return 0
    try:
        data = path.read_bytes()
        if len(data) > 400_000:
            data = data[-400_000:]
        text = data.decode("utf-8", errors="replace")
    except OSError:
        return 0
    cre = re.compile(pattern, re.I)
    n = 0
    for line in text.splitlines():
        ts = _line_epoch(line)
        if ts is None or ts < since:
            continue
        if cre.search(line):
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="RC wake UX digest (IMP-23 S14)")
    ap.add_argument("--hours", type=float, default=24.0)
    args = ap.parse_args()
    since = time.time() - args.hours * 3600
    print(
        f"RC wake digest — last {args.hours:g}h "
        f"(ISO-timestamped lines only; last ≤400KB of each log)"
    )
    print(
        f"{'bot':<10} {'FINAL_OK':>8} {'FINAL_ERR':>9} {'429':>6} "
        f"{'empty-reply':>11} {'Cancelled':>9} {'q_gate':>6}"
    )
    for bot, folder in BOTS:
        log = LOG_ROOT / folder / "operator-agent.log"
        row = {
            "ok": _count(log, r"phase=FINAL_OK", since=since),
            "err": _count(log, r"phase=FINAL_ERR", since=since),
            "429": _count(log, r"HTTP Error 429|Too Many Requests", since=since),
            "empty": _count(log, r"empty-reply recovery", since=since),
            "canc": _count(log, r"stopReason=Cancelled", since=since),
            "qg": _count(log, r"quality_gate", since=since),
        }
        print(
            f"{bot:<10} {row['ok']:>8} {row['err']:>9} {row['429']:>6} "
            f"{row['empty']:>11} {row['canc']:>9} {row['qg']:>6}"
        )
    print()
    print(
        "Hints: high 429 → S1/B4; high empty-reply+Cancelled → S2; "
        "high agy FINAL_ERR → S3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
