# Requirements: Per-room / concurrent wake queue

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-10 |
| **Priority** | Medium |
| **Phase** | D |
| **Status** | Done (2026-07-10) |
| **Depends on** | [IMP-02](../02-wake-lock-ttl/) strongly recommended first |
| **Related** | [IMP-14](../14-per-room-state-model/) |

---

## Problem

One global wake lock: a long channel wake blocks DM replies and vice versa.

---

## Goals

1. Different rooms can wake concurrently up to a cap.
2. Same room remains strictly serial (preserve session integrity).
3. No-duplicate-posts rules unchanged.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Per-room lock or per-room queue; global cap `RC_WAKE_MAX_CONCURRENT` (default ≥1). |
| R2 | Same `room_id`: FIFO; never two concurrent wakes. |
| R3 | State updates for a room are atomic relative to that room’s wake. |
| R4 | Metrics/log: queue depth per room, concurrent active count. |
| R5 | Default concurrent=1 preserves today’s behavior if unset (safe rollout). |

---

## Acceptance criteria

- [x] With concurrent=2, DM and channel wakes overlap in logs.
- [x] Two messages same room never overlap.
- [x] Usability contracts for single bubble still pass.

## Implementation notes (2026-07-10)

room_wake_lock_dir + RC_WAKE_MAX_CONCURRENT (default 1)
