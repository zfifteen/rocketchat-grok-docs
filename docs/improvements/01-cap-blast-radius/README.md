# 01 — Cap blast radius of phone-driven Grok

**Impact:** Critical · **Phase:** A (safety) · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Phone/channel messages currently spawn Grok with `--always-approve`, giving unrestricted tool use in the mapped project cwd. Restrict default approval scope; reserve full power only for an explicit admin profile.
