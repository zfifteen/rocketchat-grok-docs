#!/usr/bin/env python3
"""IMP-08: prune aged wake/call artifacts under the RC log dir."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

WAKE = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"
sys.path.insert(0, str(WAKE))
from wake_lib import DEFAULT_LOG_DIR, prune_log_artifacts  # noqa: E402

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    p.add_argument("--max-age-days", type=float, default=7.0)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    removed = prune_log_artifacts(
        args.log_dir,
        max_age_s=args.max_age_days * 86400,
        dry_run=args.dry_run,
    )
    for path in removed:
        print(("would remove" if args.dry_run else "removed"), path)
    print(f"count={len(removed)} dry_run={args.dry_run}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
