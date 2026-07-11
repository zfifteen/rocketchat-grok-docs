# Requirements: Sync stale docs and dual runbooks

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-17 |
| **Priority** | Low–medium |
| **Phase** | B |
| **Status** | Done (2026-07-10) |
| **Paths** | `ops/ROCKETCHAT.md`, `ops/NGROK.md`, this project |

---

## Problem

`NGROK.md` can claim no always-on tunnel while launchd KeepAlive is live. Dual docs risk drift.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Define ownership: **runtime status** in `ops/ROCKETCHAT.md` (+ NGROK); **architecture/map/backlog** in this project. |
| R2 | Fix any statement contradicting live launchd/ngrok state when editing. |
| R3 | Cross-links both directions (already partially done). |
| R4 | Optional: `rc status` script prints facts for pasting into runbook “Last verified”. |
| R5 | CHANGELOG entry in this project when map-affecting changes ship. |

---

## Acceptance criteria

- [x] NGROK.md matches live tunnel agent state.
- [x] No contradictory public URL across docs.
- [x] Index of improvements linked from main README (this package).

## Implementation notes (2026-07-10)

NGROK.md always-on tunnel; INDEX/CHANGELOG batch
