# 02 — Fix wake-lock TTL vs wake timeout

**Impact:** Critical · **Phase:** A (safety) · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Single-flight wake lock becomes stealable after ~3 minutes while Grok wakes may run up to 600s. Align lock lifetime with wake duration and prefer PID liveness over pure mtime.

## Implementation notes (2026-07-10)

stale default=timeout+300; live PID never stolen; heartbeat during wake; tests updated
