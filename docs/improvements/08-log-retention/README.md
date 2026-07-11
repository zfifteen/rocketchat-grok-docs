# 08 — Log and artifact retention

**Impact:** Medium–high · **Phase:** B · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Wake prompts, run logs, and call-media accumulate without rotation. Add retention policy and optional prompt scrubbing.

## Implementation notes (2026-07-10)

prune_log_artifacts + scripts/prune_logs.py + prune-on-start
