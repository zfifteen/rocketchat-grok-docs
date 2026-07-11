# Requirements: Quarantine or remove poll path

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-18 |
| **Priority** | Low (high if re-enabled) |
| **Phase** | D |
| **Status** | Done (2026-07-10) |
| **Related** | [IMP-11](../11-launchd-templates/) |

---

## Problem

`com.velocityworks.rocketchat-dm-wake` plist remains on disk with `StartInterval=20` and `RunAtLoad`. Currently not loaded — good — but easy to revive dual consumers of DMs.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Choose **delete** or **quarantine** strategy; document decision. |
| R2 | If kept: plist has `Disabled=true` (or not installed by default); `run_poll.sh` exits 0 immediately if operator health/lock indicates active operator **or** env `RC_POLL_ENABLED≠1`. |
| R3 | Ops docs state: primary = WebSocket operator only. |
| R4 | Comment in ROCKETCHAT.md: do not load poll without disabling operator. |

---

## Acceptance criteria

- [x] `launchctl print` cannot find poll **or** shows disabled.
- [x] Accidental `kickstart` of poll does not double-process (guard).

## Implementation notes (2026-07-10)

run_poll.sh requires RC_POLL_ENABLED=1; plist Disabled
