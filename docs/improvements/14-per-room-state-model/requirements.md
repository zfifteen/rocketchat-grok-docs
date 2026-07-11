# Requirements: Per-room state model cleanup

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-14 |
| **Priority** | Medium |
| **Phase** | D |
| **Status** | Done (2026-07-10) |
| **Primary code** | `wake/state.json`, `wake_lib` session/cwd helpers, operator mark/enqueue |
| **Related** | [IMP-10](../10-per-room-wake-queue/), [IMP-02](../02-wake-lock-ttl/) |

---

## Problem

`state.json` mixes global `last_seen_id` / `room_id` with per-room `grok_sessions` / `grok_cwds` and global `processed_ids` / `pending_wakes`. Harder to reason about multi-room catch-up.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Schema v2: `version`, `rooms[rid]{last_seen_id, session_id, cwd, …}`, `pending_wakes[]`, `processed_ids` (global or per-room — pick one, document). |
| R2 | Loader migrates v1 → v2 on read; atomic write. |
| R3 | No message loss during migration (processed set preserved). |
| R4 | Unit tests for migrate empty, single-room, multi-room legacy. |
| R5 | Optional: cap `processed_ids` remains. |

---

## Acceptance criteria

- [x] Existing production state loads without re-processing old messages.
- [x] New fields used by mark/enqueue paths.
- [x] Migration tested with fixture copies of real state (sanitized).

## Implementation notes (2026-07-10)

migrate_state_to_v2 on load/save
