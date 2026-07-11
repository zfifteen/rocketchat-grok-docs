# Test plan: Single configuration surface + startup validation

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-03-TP |
| **Requirements** | [IMP-03](./requirements.md) |

---

## Test cases

### T1 — Schema completeness

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Diff schema vs live operator needs (paths, URLs, bins) | All production reads covered |
| 2 | Example file parses | No required secret values in example |

**Pass:** R1, R2, R6.

### T2 — Override paths

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Point `RC_LOG_DIR` / agency / secrets to temp dirs | Operator uses temp paths only |
| 2 | Confirm no writes under real `~/logs/rocketchat-dm-wake` during test | Isolation held |

**Pass:** R2, R3.

### T3 — Missing secrets

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Start loader/operator with missing secrets path | Non-zero exit; message names path; no traceback secrets |

**Pass:** R4, R5.

### T4 — RC unreachable

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `RC_BASE=http://127.0.0.1:1` | Startup validation fails clearly |

**Pass:** R4, R5.

### T5 — Shared loader

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Import loader from operator and call bot (and media) | Same module/function |
| 2 | Unit test both call load_config | Identical key set |

**Pass:** R3.

---

## Exit criteria

T1–T5 pass; docs index links to example config path.

## Execution record (2026-07-10, skeptic-honest)

Tests: imp03_config_wired_and_examples (load_rc_config + main wires apply_runtime_config). Artifacts: config.example, .env.example. Smoke: apply_config_smoke.log.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

