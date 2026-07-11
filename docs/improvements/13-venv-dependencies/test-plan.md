# Test plan: Pinned venv dependencies

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-13-TP |
| **Requirements** | [IMP-13](./requirements.md) |

---

## Test cases

### T1 — setup-venv

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Run setup script | `.venv` exists; websocket import works |

**Pass:** R1, R2, R5.

### T2 — No runtime pip

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Grep operator/call for `pip install` | None in production paths |
| 2 | Remove dep from venv; start operator | Hard fail message, no install |

**Pass:** R4.

### T3 — launchd python

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `run_operator_agent.sh` shebang/PYTHON_BIN | Points at venv |
| 2 | Service running | `sys.executable` is venv (log once) |

**Pass:** R3.

---

## Exit criteria

T1–T3 pass.

## Execution record (2026-07-10, skeptic-honest)

Artifacts: requirements.txt, setup-venv.sh, .venv; operator no runtime pip install (source). venv_setup.log.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

