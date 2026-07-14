# 19 — Channel auto-create policy

**Impact:** Low–medium · **Phase:** D · **Status:** Superseded default (2026-07-14)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

IMP-19 introduced `RC_AUTO_CREATE_PROJECTS` as a control for whether new channels auto-mkdir under `~/IdeaProjects/<slug>`.

**Current product intent (2026-07-14):** auto-create is **always on** by default. The flag remains as a **kill switch** (`0` / `false` / `off`).

## Implementation notes

| Date | Policy |
| --- | --- |
| 2026-07-10 | Default `0` (`no_create`); prefer explicit map |
| 2026-07-14 | Default `1` (always create); launchd + code default on; `0` is opt-out only |
