# 11 — Generate launchd from templates

**Impact:** Medium · **Phase:** C · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Replace hand-edited absolute-path plists with an install script that renders templates from `$HOME` and detected binaries.

## Implementation notes (2026-07-10)

install-launchd.sh renders plists without hardcoding only one path style
