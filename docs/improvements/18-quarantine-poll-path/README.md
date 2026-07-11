# 18 — Quarantine or remove poll path

**Impact:** Low if unloaded; high if re-enabled · **Phase:** D · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Poll launchd plist still exists with RunAtLoad. Remove it or install disabled with hard guards so dual-wake cannot return by accident.

## Implementation notes (2026-07-10)

run_poll.sh requires RC_POLL_ENABLED=1; plist Disabled
