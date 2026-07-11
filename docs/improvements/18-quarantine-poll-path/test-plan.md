# Test plan: Quarantine or remove poll path

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-18-TP |
| **Requirements** | [IMP-18](./requirements.md) |

---

## Test cases

### T1 — Not loaded by default

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `launchctl print gui/$UID/com.velocityworks.rocketchat-dm-wake` | Not found **or** disabled |

**Pass:** R1, acceptance.

### T2 — Guard

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Run `run_poll.sh` with operator up and poll not enabled | No-op / exit without wake |
| 2 | Only with `RC_POLL_ENABLED=1` and operator stopped (if dual-mode supported) | Documented behavior |

**Pass:** R2.

### T3 — Docs

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Read ROCKETCHAT.md / operations | Poll marked backup-only / do not load |

**Pass:** R3, R4.

---

## Exit criteria

T1–T3 pass.

## Execution record (2026-07-10, skeptic-honest)

run_poll.sh requires RC_POLL_ENABLED=1; poll plist Disabled=true (structural).

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

