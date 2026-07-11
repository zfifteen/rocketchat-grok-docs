# Test plan: Per-room / concurrent wake queue

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-10-TP |
| **Requirements** | [IMP-10](./requirements.md) |

---

## Test cases

### T1 — Default serial

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `RC_WAKE_MAX_CONCURRENT=1` | Same as today: second room waits |

**Pass:** R5.

### T2 — Cross-room parallel

| Step | Action | Expected |
| --- | --- | --- |
| 1 | concurrent=2; enqueue room A and B with mocked long wake | Overlapping active intervals in log |
| 2 | State files consistent | No crossed session ids |

**Pass:** R1, R3.

### T3 — Same-room serial

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Two messages room A | Second starts only after first completes |

**Pass:** R2.

### T4 — No-duplicate contracts

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Run usability contract suite | Pass |

**Pass:** acceptance.

---

## Exit criteria

T1–T4 pass under unit/integration with mocks (live optional).

## Execution record (2026-07-10, skeptic-honest)

Test: test_imp_batch_helpers room_wake_lock_dir + max_concurrent_wakes_from_env; drain uses per-room locks (default concurrent=1).

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

