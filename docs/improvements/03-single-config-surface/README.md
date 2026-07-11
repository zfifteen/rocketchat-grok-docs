# 03 — Single configuration surface + startup validation

**Impact:** High · **Phase:** C (structure) · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Collapse secrets, compose env, hardcoded paths, and partial `RC_*` overrides into one validated config loaded by all components, with fail-fast startup checks.

## Implementation notes (2026-07-10)

wake/rc_config.py load_rc_config + validate_config_startup; env path overrides
