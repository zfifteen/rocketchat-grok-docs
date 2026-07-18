# 25 — IMP-B stream / intentional wake honesty

**Status:** plan draft v2 (feynman pass-with-edits folded) — awaiting re-pass  
**Lead:** hermes (principal 2026-07-18)  
**Ship rank:** this week (from protocol collab close)

| Doc | Path |
| --- | --- |
| Implementation plan | [implementation-plan.md](./implementation-plan.md) |
| Test plan | [test-plan.md](./test-plan.md) |

**v2 product rule:** (1) intermediate paints always wrap `*Thoughts*\n\n`; (2) delete intentional short-circuit in `looks_like_nonfinal_stream` so shell head without final marker is always nonfinal.

**Related:** improvement 21 B3/B10, IMP-24 epoch ownership (month residual)
