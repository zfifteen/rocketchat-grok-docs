# Research: AGY collab enablement

**Nav:** [README](./README.md) · [Spec](./spec.md)

| Field | Value |
| --- | --- |
| **ID** | NF-R-09 |
| **Date** | 2026-07-12 |
| **Enhancement #** | 16 |
| **Parent** | [NF-SPEC-04](../04-agy-rocketchat-collab/spec.md) |

---

## Problem

Collab code paths may be present while production remains single-operator. Enabling dual agents without gates risks:

- Infinite @mention loops  
- Double wakes on every message  
- Cost (two models)  
- Confused channel history  

## Options

| Option | Verdict |
| --- | --- |
| Always-on collab in all rooms | **Reject** |
| Per-room arm via principal command | **Preferred** |
| Separate collab-only server | Overkill |

## Recommendation

Default **disarmed**. Principal `/collab on` in a private room after allowlist. Hard hop budget. Self-wake filter. Align with NF-SPEC-04 profiles under `04-agy-rocketchat-collab/profiles/`.

## Relationship to NF-04

| Layer | Role |
| --- | --- |
| NF-SPEC-04 | Protocol, mention routing, hop FSM, agy CLI contracts |
| NF-SPEC-09 (this) | Production enablement, flags, principal gates, cutover checklist, ops acceptance |
