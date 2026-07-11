# Test plan: Fix wake-lock TTL vs wake timeout

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-02-TP |
| **Requirements** | [IMP-02](./requirements.md) |

---

## Preconditions

- Writable temp lock dir for tests (do not use production `~/logs/…/wake.lock.d` for unit tests).
- Access to `wake_lib.acquire_wake_lock` / `release_wake_lock` / `force_clear_wake_lock`.

---

## Test cases

### T1 — Defaults are consistent

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Read configured wake timeout and stale threshold | `stale > timeout` **or** heartbeat enabled flag true |
| 2 | Document values in evidence | Numeric pair recorded |

**Pass:** R1, R5.

### T2 — Live PID cannot be stolen

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Acquire lock in process A; write live PID | Success |
| 2 | Artificially age directory mtime beyond old 180s if needed | — |
| 3 | Process B calls acquire | **False** (no steal) |
| 4 | A releases | B can acquire |

**Pass:** R2.

### T3 — Dead PID can be reclaimed

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Create lock dir with `holder.pid` = nonexistent PID | — |
| 2 | Set mtime older than stale threshold | — |
| 3 | Acquire | **True** |

**Pass:** R3.

### T4 — Release on timeout path

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Simulate `_run_wake_once` timeout (mock subprocess) under drain | Lock absent after drain finishes |
| 2 | Or integration: force short timeout env | Lock cleared; next message can wake |

**Pass:** R4.

### T5 — No production lock left after test suite

| Step | Action | Expected |
| --- | --- | --- |
| 1 | After tests, check production lock path only if suite never used it | No leftover test locks in prod dir |

---

## Exit criteria

T1–T4 pass; evidence attached to CHANGELOG or PR notes.

## Execution record (2026-07-10, skeptic-honest)

Tests: test_imp_batch_helpers (live PID no-steal, dead reclaim) + integration lock_single_flight; DEFAULT_WAKE_LOCK_STALE_S > DEFAULT_WAKE_TIMEOUT_S; heartbeat in _run_wake_once.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

