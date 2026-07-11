# 09 — Align Grok turn-limit defaults

**Impact:** Medium · **Phase:** C · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

`MAX_TURNS` / env default “20” disagrees with `wake_grok` fallback “12” and call-bot “8”. One documented source of truth.

## Implementation notes (2026-07-10)

DEFAULT_WAKE_MAX_TURNS=12 unified; MAX_TURNS default 12
