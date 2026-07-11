# Test plan: Operator health endpoint / watchdog

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-12-TP |
| **Requirements** | [IMP-12](./requirements.md) |

---

## Test cases

### T1 — Healthy write

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Run operator | `health.json` appears |
| 2 | Schema keys present | R1; no tokens |

**Pass:** R1, R5.

### T2 — Freshness

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Wait 2 intervals | `ts` advances |

**Pass:** R2.

### T3 — Check script

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Fresh healthy file | exit 0 |
| 2 | Backdate ts | exit ≠ 0 |
| 3 | `ws_connected=false` | exit ≠ 0 |

**Pass:** R3.

### T4 — Disconnect signal (integration)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Stop RC briefly | health flips or reconnects; documented behavior |

**Pass:** acceptance.

---

## Exit criteria

T1–T3 required; T4 best-effort.

## Execution record (2026-07-10, skeptic-honest)

Test: imp12_health_check_script (rc_health_check.sh exit 0 fresh / nonzero stale / ws_connected false); health_check_ok helper; live health.json written by operator.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

