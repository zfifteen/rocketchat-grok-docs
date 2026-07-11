# 10 — Per-room / concurrent wake queue

**Impact:** Medium · **Phase:** D · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Global single-flight lock serializes all rooms. Allow limited concurrency (e.g. per-room locks) without breaking no-duplicate-posts.

## Implementation notes (2026-07-10)

room_wake_lock_dir + RC_WAKE_MAX_CONCURRENT (default 1)
