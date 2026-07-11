# Test plan: PGS / bot auth via shared token surface

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-20-TP |
| **Requirements** | [IMP-20](./requirements.md) |

---

## Test cases

### T1 — Token REST login/use

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Configure token; no password | Operator can postMessage/update |
| 2 | Logs | No token string |

**Pass:** R1, R2, R5.

### T2 — Password fallback

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Token unset; password set | Existing behavior |

**Pass:** R1 acceptance.

### T3 — PGS notify

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Run notify against test room or dry-run | Auth succeeds with same keys |
| 2 | Idempotency still holds | No double post for same activation |

**Pass:** R3, R4 related.

### T4 — Rotation drill

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Follow runbook with new token | Old token fails; new works |

**Pass:** R4.

---

## Exit criteria

T1–T2 required for operator; T3 when PGS integrated; T4 optional.

## Execution record (2026-07-10, skeptic-honest)

Test: imp20_pgs_token_auth_path — resolve_operator_auth token path never calls rest_login; password fallback mocked once; media.login() token-only. Full live RC notify with token-only secrets not run (no PAT issued).

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

