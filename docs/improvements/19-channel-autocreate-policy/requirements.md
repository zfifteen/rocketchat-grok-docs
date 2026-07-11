# Requirements: Channel auto-create policy

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-19 |
| **Priority** | Low–medium |
| **Phase** | D |
| **Status** | Done (2026-07-10) |
| **Primary code** | `wake_lib.resolve_project_cwd`, `channel_projects.json` |

---

## Problem

Any joined channel can create a new IdeaProjects directory. Clutters the workspace for casual/test channels.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Config `RC_AUTO_CREATE_PROJECTS` default **false** (or opt-in true with docs). |
| R2 | When false: unmapped channel uses existing match only; else falls back to agency **or** fails wake with clear RC message — choose and document. |
| R3 | `channel_projects.json` remains the explicit allow/map list. |
| R4 | DM behavior unchanged (agency cwd). |
| R5 | Log reason code already partially present (`created` \| `map` \| …) stays accurate. |

---

## Acceptance criteria

- [x] New unmapped channel does not create a directory under default policy.
- [x] Mapped channel (e.g. Prime-Gap-Structure) still resolves correctly.
- [x] DM still uses agency.

## Implementation notes (2026-07-10)

RC_AUTO_CREATE_PROJECTS default 0; reason no_create
