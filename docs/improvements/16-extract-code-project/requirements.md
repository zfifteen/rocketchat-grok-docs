# Requirements: Extract integration code to a project

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-16 |
| **Priority** | Medium (long-term) |
| **Phase** | D |
| **Status** | Won't do (2026-07-10) |
| **Depends on** | [IMP-03](../03-single-config-surface/), [IMP-11](../11-launchd-templates/) recommended first |
| **Related** | This docs project remains the map |

---

## Problem

Application code lives inside agency ops tree, mixed with continuity state, hard to version and review.

---

## Goals

1. Git-friendly code home under `~/IdeaProjects/` (name TBD, e.g. `rocketchat-grok`).
2. Secrets + STATE stay at `~/.grok/agency`.
3. Zero-downtime migration path (symlink or cutover install).

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | New repo contains: wake/, call/, tests/, compose, scripts, README. |
| R2 | All paths via config (IMP-03); no required residence under `.grok/agency/ops`. |
| R3 | `install.sh` wires launchd, venv, points secrets path at agency. |
| R4 | Agency `ops/ROCKETCHAT.md` becomes short pointer to new repo + this docs project. |
| R5 | Migration runbook: stop operator → move/copy → install → start → smoke. |
| R6 | PGS notify may keep using secrets path only (no code move required). |

---

## Non-goals

- Moving IdeaProjects channel workspaces into the app repo.
- Moving Mongo volume into git.

---

## Acceptance criteria

- [ ] Operator runs from new path for ≥24h without regression.
- [ ] Old path removed or reduced to stub README.
- [ ] Docs filesystem map updated.

## Won't do reason

Full cutover of live KeepAlive operator into a new IdeaProjects app repo is deferred: live path remains under ~/.grok/agency/ops/rocketchat with install-launchd.sh + rc_config path overrides as the portable surface. Docs map is rocketchat-grok-docs. Extract can resume later without data loss.
