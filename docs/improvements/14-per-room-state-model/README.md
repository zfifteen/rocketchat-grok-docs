# 14 — Per-room state model cleanup

**Impact:** Medium · **Phase:** D · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Migrate flat `state.json` (global last_seen + mixed fields) to an explicit per-room schema with backward-compatible load.

## Implementation notes (2026-07-10)

migrate_state_to_v2 on load/save
