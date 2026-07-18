# 16 — Extract integration code to a project

**Impact:** Medium (long-term) · **Phase:** D · **Status:** Won't do (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Move portable software (wake/call/compose/tests) into an IdeaProjects app repo; keep secrets and agency continuity under `~/.grok/agency`. Config-driven paths.

## Won't do reason

Full cutover of live KeepAlive operator into a new IdeaProjects app repo is deferred: live path remains under ~/.grok/agency/ops/rocketchat with install-launchd.sh + rc_config path overrides as the portable surface. Docs map is rocketchat-agents. Extract can resume later without data loss.
