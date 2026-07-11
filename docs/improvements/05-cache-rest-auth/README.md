# 05 — Cache REST auth tokens

**Impact:** High · **Phase:** B (ops truth) · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Operator currently performs a full Rocket.Chat login on nearly every REST call. Cache token/userId for the process lifetime and refresh on 401.

## Implementation notes (2026-07-10)

operator _operator_auth cache + 401 retry; auth_login_count in health
