# Test plan: Channel auto-create policy

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-19-TP |
| **Requirements** | [IMP-19](./requirements.md) |

---

## Test cases

### T1 — Unit resolve with create off

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `create_if_missing=False` / env false; unknown channel | No new dir under temp IdeaProjects |
| 2 | Reason code documented | R2, R5 |

**Pass:** R1, R2.

### T2 — Map still works

| Step | Action | Expected |
| --- | --- | --- |
| 1 | channel_projects entry | Resolves to mapped path |

**Pass:** R3.

### T3 — DM

| Step | Action | Expected |
| --- | --- | --- |
| 1 | room type d | Agency path |

**Pass:** R4.

### T4 — Opt-in create

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Auto-create true | Dir created with README as today |

**Pass:** R1.

---

## Exit criteria

T1–T3 required; T4 if flag exists.

## Execution record (2026-07-10, skeptic-honest)

Test: test_imp_batch_helpers auto_create default false + resolve no_create without mkdir.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

