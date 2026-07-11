# Requirements: Fix wake-lock TTL vs wake timeout

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-02 |
| **Priority** | Critical |
| **Phase** | A — safety |
| **Status** | Done (2026-07-10) |
| **Primary code** | `wake/wake_lib.py` (`acquire_wake_lock`, `release_wake_lock`), `wake/rc_operator_agent.py` (`_run_wake_once`, drain) |
| **Related** | [IMP-10](../10-per-room-wake-queue/requirements.md), [IMP-14](../14-per-room-state-model/requirements.md) |

---

## Problem

| Constant | Approx value |
| --- | --- |
| Wake subprocess timeout | 600s |
| Lock `stale_after_s` | 180s (3 min) |

A long wake can lose the lock while still running; a second drain may start. That risks concurrent Grok processes, racing `state.json` writes, and duplicate side effects.

---

## Goals

1. A live wake must **never** lose the lock to a stale reclaim.
2. Truly dead holders (crashed process) must still be reclaimable.
3. Behavior covered by unit tests with fake time/PID where possible.

---

## Non-goals

- Multi-room parallel wakes (see IMP-10).
- Distributed locks across machines.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | `stale_after_s` must be **strictly greater** than the wake subprocess timeout, **or** lock must be heartbeated while the wake runs (mtime/PID refresh). |
| R2 | If `holder.pid` exists and process is alive, acquire must **fail** (no steal), regardless of age. |
| R3 | If `holder.pid` is dead or missing and age > stale threshold, reclaim is allowed. |
| R4 | Normal completion path always releases the lock (including timeout kill path). |
| R5 | Constants/timeouts configurable via env (`RC_WAKE_TIMEOUT_S`, `RC_WAKE_LOCK_STALE_S`) with safe defaults. |

---

## Acceptance criteria

- [x] No configuration allows `stale_after_s < wake_timeout` without heartbeat.
- [x] Unit tests simulate long wake + concurrent acquire → second fails while PID alive.
- [x] Unit tests simulate dead PID + old mtime → reclaim succeeds.
- [x] Drain timeout path releases lock (manual or automated).

---

## Risks

- Heartbeat thread bugs could keep locks forever — pair with PID check on acquire.

## Implementation notes (2026-07-10)

stale default=timeout+300; live PID never stolen; heartbeat during wake; tests updated
