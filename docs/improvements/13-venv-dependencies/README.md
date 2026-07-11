# 13 — Pinned venv dependencies (no runtime pip)

**Impact:** Medium · **Phase:** C · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Remove launchd-time `pip install websocket-client`. Use a dedicated venv and requirements lock for operator/call code.

## Implementation notes (2026-07-10)

requirements.txt + setup-venv.sh; no runtime pip install
