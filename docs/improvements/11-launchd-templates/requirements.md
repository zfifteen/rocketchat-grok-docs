# Requirements: Generate launchd from templates

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-11 |
| **Priority** | Medium |
| **Phase** | C |
| **Status** | Done (2026-07-10) |
| **Related** | [IMP-03](../03-single-config-surface/), [IMP-18](../18-quarantine-poll-path/) |

---

## Problem

Plists hardcode `/Users/velocityworks/...` and Python 3.13 framework paths. Fragile on reinstall/migration.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Templates for operator + ngrok (and poll if kept) under ops/rocketchat or extracted project. |
| R2 | `install-launchd.sh` writes to `~/Library/LaunchAgents/` with substituted HOME, GROK_BIN, PYTHON_BIN, script paths. |
| R3 | Idempotent re-run; optional `--unload` / `--load`. |
| R4 | Poll agent either omitted or installed **disabled** by default (IMP-18). |
| R5 | Script prints resulting labels and how to kickstart. |
| R6 | Does not embed secrets in plists. |

---

## Acceptance criteria

- [x] Fresh install on this Mac produces working operator KeepAlive.
- [x] No username hardcoding in templates (only placeholders).
- [x] Documented in [operations](../../operations.md).

## Implementation notes (2026-07-10)

install-launchd.sh renders plists without hardcoding only one path style
