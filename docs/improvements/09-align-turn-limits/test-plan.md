# Test plan: Align Grok turn-limit defaults

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-09-TP |
| **Requirements** | [IMP-09](./requirements.md) |

---

## Test cases

### T1 — Code default unity

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Unset env; build argv via production helpers | `--max-turns` equals constant |
| 2 | Grep for hardcoded max-turns strings | Only constant definition + tests |

**Pass:** R1.

### T2 — Env override

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `RC_WAKE_MAX_TURNS=5` | Argv uses 5 |

**Pass:** R2 related.

### T3 — Call bot separate

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Read call bot default | Documented; not forced equal to wake unless intended |

**Pass:** R3, R4.

---

## Exit criteria

T1–T2 pass; docs updated.

## Execution record (2026-07-10, skeptic-honest)

Test: test_imp_batch_helpers DEFAULT_WAKE_MAX_TURNS=12; operator MAX_TURNS default 12; launchd RC_WAKE_MAX_TURNS=12.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

