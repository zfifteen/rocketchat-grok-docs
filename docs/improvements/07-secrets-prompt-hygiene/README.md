# 07 — Secrets out of model prompt

**Impact:** High · **Phase:** A (safety) · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Stop instructing Grok to load `rocketchat.env`. Operator should fetch any needed RC history and inject sanitized context only.

## Implementation notes (2026-07-10)

reply_prompt no longer instructs loading rocketchat.env
