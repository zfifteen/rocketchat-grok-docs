# Research: DM health card

**Nav:** [README](./README.md) · [Spec](./spec.md)

| Field | Value |
| --- | --- |
| **ID** | NF-R-08 |
| **Date** | 2026-07-12 |
| **Enhancement #** | 15 |

---

## Problem

Failure modes (Docker down, stuck wake lock, Call backend misconfigured, disk full) require SSH/logs. Control plane already intercepts `/status`-class commands before Thinking.

## Options

| Option | Verdict |
| --- | --- |
| Full Grok wake to “check health” | Too slow; overkill |
| `/health` control-plane card | **Preferred** |
| External status page | Optional later (P3 dashboard) |

## Recommendation

Extend NF-SPEC-03 control plane with `/health` (alias `/ops`). Pure gatherers + one markdown table. No secrets. No Grok CLI.
