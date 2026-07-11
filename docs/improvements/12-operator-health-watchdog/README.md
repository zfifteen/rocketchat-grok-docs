# 12 — Operator health endpoint / watchdog

**Impact:** Medium · **Phase:** D · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

KeepAlive restarts processes but not “WS connected and useful.” Write a health snapshot and optional external check.

## Implementation notes (2026-07-10)

health.json + scripts/rc_health_check.sh
