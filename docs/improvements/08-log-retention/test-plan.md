# Test plan: Log and artifact retention

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-08-TP |
| **Requirements** | [IMP-08](./requirements.md) |

---

## Test cases

### T1 — Dry-run prune in temp dir

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Seed temp log dir with old/new files | — |
| 2 | Run prune `--dry-run` | Lists only old files |
| 3 | Run prune for real | Old gone; new kept; ledger kept |

**Pass:** R1, R5, R6, acceptance.

### T2 — KEEP_WAKE_PROMPTS=0

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Simulate wake with flag | Prompt removed after success |
| 2 | Failed wake | Prompt retained for debug (if required — document either way) |

**Pass:** R4.

### T3 — Production smoke (careful)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Dry-run against real log dir | Sane candidate count |
| 2 | Only apply after principal OK if deleting real data | — |

---

## Exit criteria

T1 required; T2 if feature built; T3 optional.

## Execution record (2026-07-10, skeptic-honest)

Test: test_imp_batch_helpers prune_log_artifacts dry/real; scripts/prune_logs.py; operator prune-on-start.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

