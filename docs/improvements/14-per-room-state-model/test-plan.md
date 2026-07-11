# Test plan: Per-room state model cleanup

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-14-TP |
| **Requirements** | [IMP-14](./requirements.md) |

---

## Test cases

### T1 — Migrate fixtures

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Load sample v1 state (3 rooms) | v2 structure; sessions/cwds preserved |
| 2 | `processed_ids` length unchanged | R3 |

**Pass:** R1, R2, R4.

### T2 — Idempotent migrate

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Load v2 again | No double-nesting / data loss |

**Pass:** R2.

### T3 — Operator smoke

| Step | Action | Expected |
| --- | --- | --- |
| 1 | With migrated state, send test DM | No re-wake of old ids; new mid processed |

**Pass:** acceptance.

---

## Exit criteria

T1–T2 unit; T3 optional live.

## Execution record (2026-07-10, skeptic-honest)

Test: test_imp_batch_helpers migrate_state_to_v2; load_state/save_state always version=2 (integration state_load_save_roundtrip).

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

