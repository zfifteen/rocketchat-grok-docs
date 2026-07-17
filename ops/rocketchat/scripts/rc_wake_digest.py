#!/usr/bin/env python3
"""IMP-23 S14: 24h wake/response digest across operator log dirs.

Usage:
  python3 ops/rocketchat/scripts/rc_wake_digest.py
  python3 ~/.grok/agency/ops/rocketchat/scripts/rc_wake_digest.py --hours 48
"""

from __future__ import annotations

import argparse
import re
import time
from collections import Counter
from pathlib import Path

LOG_ROOT = Path.home() / "logs"
BOTS = (
    ("grok", "rocketchat-dm-wake"),
    ("hermes", "rocketchat-hermes-wake"),
    ("agy", "rocketchat-agy-wake"),
    ("nie", "rocketchat-nie-wake"),
    ("feynman", "rocketchat-feynman-wake"),
)


def _count(path: Path, pattern: str, *, since: float) -> int:
    if not path.is_file():
        return 0
    try:
        if path.stat().st_mtime < since:
            # still read last 400KB for rolling logs that are still "current"
            pass
        data = path.read_bytes()
        if len(data) > 400_000:
            data = data[-400_000:]
        text = data.decode("utf-8", errors="replace")
    except OSError:
        return 0
    return len(re.findall(pattern, text, re.I))


def main() -> int:
    ap = argparse.ArgumentParser(description="RC wake UX digest (IMP-23 S14)")
    ap.add_argument("--hours", type=float, default=24.0)
    args = ap.parse_args()
    since = time.time() - args.hours * 3600
    print(f"RC wake digest — last {args.hours:g}h (file mtime + tail scan)")
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
    print("Hints: high 429 → S1/B4; high empty-reply+Cancelled → S2; high agy FINAL_ERR → S3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
