# 20 — PGS / bot auth via shared token surface

**Impact:** Low · **Phase:** D · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Optional hardening: prefer Rocket.Chat personal access tokens (or equivalent) for `grok` bot shared by operator and PGS notify, via the single config surface—not long-lived password in every script.

## Implementation notes (2026-07-10)

ROCKETCHAT_OPERATOR_TOKEN+USER_ID preferred in _operator_auth; password fallback
