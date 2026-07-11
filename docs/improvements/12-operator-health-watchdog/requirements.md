# Requirements: Operator health endpoint / watchdog

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-12 |
| **Priority** | Medium |
| **Phase** | D |
| **Status** | Done (2026-07-10) |
| **Related** | [IMP-05](../05-cache-rest-auth/), [IMP-04](../04-docker-healthcheck/) |

---

## Problem

Operator can be “running” but disconnected, stuck, or not receiving rooms. No machine-readable health.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Periodically write `health.json` under log dir: `ts`, `ws_connected`, `rooms_count`, `last_event_at`, `last_wake_at`, `pid`. |
| R2 | Update interval configurable (default ≤ 60s). |
| R3 | Optional `rc-health-check.sh`: exit 0 if health fresh and `ws_connected`; else non-zero. |
| R4 | Document how to wire launchd WatchPaths / cron / manual check. |
| R5 | No secrets in health.json. |

---

## Acceptance criteria

- [x] During normal operation, health.json age < 2× interval.
- [x] Kill WS (or block RC): health shows disconnected within interval.
- [x] Check script returns non-zero on stale file.

## Implementation notes (2026-07-10)

health.json + scripts/rc_health_check.sh


## Skeptic fix (2026-07-10)

imp12_health_check_script executes shipped rc_health_check.sh for fresh/stale/ws_connected=false.
