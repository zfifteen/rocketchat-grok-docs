# 19 — Channel auto-create policy

**Impact:** Low–medium · **Phase:** D · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Stop auto-creating `~/IdeaProjects/<slug>` for every new channel by default; prefer explicit map entries.

## Implementation notes (2026-07-10)

RC_AUTO_CREATE_PROJECTS default 0; reason no_create
