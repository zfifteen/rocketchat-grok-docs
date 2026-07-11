# Test plan: Cache REST auth tokens

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-05-TP |
| **Requirements** | [IMP-05](./requirements.md) |

---

## Test cases

### T1 — Unit: cache hit

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Mock `login` counter | — |
| 2 | Call post then update | `login` called **once** |

**Pass:** R1, R2.

### T2 — Unit: 401 refresh

| Step | Action | Expected |
| --- | --- | --- |
| 1 | First API returns 401; second succeeds after re-login | One re-login; caller succeeds |
| 2 | Third API | Uses new token; no extra login |

**Pass:** R3.

### T3 — Unit: login mutex

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Parallel threads request auth with empty cache | Single login invocation |

**Pass:** R5.

### T4 — Live optional

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Instrument or RC logs during one DM wake | Login count ≪ number of REST calls |

**Pass:** acceptance criterion.

---

## Exit criteria

T1–T3 pass; T4 optional.

## Execution record (2026-07-10, skeptic-honest)

Test: imp05_auth_cache_and_401_retry drives shipped _operator_auth (single login cache) and _rest_with_auth_retry (401→re-login). Evidence in rc_usability.log.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

