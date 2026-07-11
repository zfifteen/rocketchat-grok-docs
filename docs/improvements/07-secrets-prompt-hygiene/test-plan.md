# Test plan: Secrets out of model prompt

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-07-TP |
| **Requirements** | [IMP-07](./requirements.md) |

---

## Test cases

### T1 — Prompt file static scan

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Grep `reply_prompt.txt` for `rocketchat.env`, `secrets/` | No “load secrets” instruction |
| 2 | Confirm ban language present | “Do not dump secrets” remains |

**Pass:** R1, R2.

### T2 — Built prompt scan

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Call `build_prompt` with sample messages | Output has no secrets path |
| 2 | Automated test in usability suite | Permanent regression guard |

**Pass:** acceptance.

### T3 — History inject (if implemented)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Enable history inject; mock REST history | Context includes message texts only |
| 2 | Ensure no `authToken` fields in inject | R4 |

**Pass:** R3, R4.

### T4 — Media path still works

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `rc_post_media.py` dry-run or unit | Still loads secrets itself; model not required |

**Pass:** R5.

---

## Exit criteria

T1–T2 required; T3–T4 as applicable.

## Execution record (2026-07-10, skeptic-honest)

Test: test_imp_batch_helpers greps reply_prompt for no Load secrets / rocketchat.env load instruction.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

