# Test plan: Cap blast radius of phone-driven Grok

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-01-TP |
| **Requirements** | [IMP-01](./requirements.md) |
| **Type** | Unit + config inspection + optional live smoke |

---

## Preconditions

- Checkout of operator code under `~/.grok/agency/ops/rocketchat/` (or extracted project after IMP-16).
- Ability to run `python3 …/tests/test_rc_integration.py` and usability contracts.
- No need for production launchd changes during unit tests.

---

## Test cases

### T1 — Default argv is restricted

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Unset `RC_WAKE_APPROVAL_MODE` (or set `restricted`) | — |
| 2 | Call `build_wake_argv` (or wrapper) as production does | Argv **does not** contain `--always-approve` |
| 3 | Log line for a simulated wake | Contains `approval_mode=restricted` (or equivalent) |

**Pass:** R1–R3, N2.

### T2 — Admin mode restores full approval

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Set mode to `admin` | — |
| 2 | Build argv | Contains `--always-approve` **or** documented admin flag set |
| 3 | Invalid | `approval_mode=admin` |

**Pass:** R4, N1.

### T3 — Channel vs DM policy (if implemented)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Restricted global + channel room | No always-approve |
| 2 | Admin global + channel room | Per R5: either still restricted (if channels locked) or admin — match requirements |
| 3 | Admin + DM | Admin argv |

**Pass:** R5.

### T4 — Regression: wake safety tests still pass

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Run integration + usability argv tests | All pass |
| 2 | Confirm no reintroduction of `--disallowed-tools Agent` | `wake_argv_is_safe` true |

**Pass:** N3.

### T5 — Prompt documents mode (manual)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Read generated wake prompt or template | States restricted vs admin capabilities |
| 2 | Confirm secrets path guidance still compliant with IMP-07 if done | No “load rocketchat.env for fun” |

**Pass:** R6.

### T6 — Optional live smoke (principal-gated)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | With restricted mode live, DM: “create a file /tmp/rc-blast-test” | Tool blocked or denied; Thinking… explains limit **or** no unrestricted write outside policy |
| 2 | Do **not** leave admin mode on after test | launchd env restored to restricted |

**Pass:** end-to-end intent. Skip if CLI cannot express restriction yet — document gap.

---

## Evidence to record

- Command outputs / pytest names  
- Sample argv lists for both modes  
- Date and who ran the plan  

---

## Exit criteria

All of T1–T4 pass; T5 reviewed; T6 optional. Requirements acceptance checkboxes ticked.

---

## Execution record (2026-07-10, skeptic-honest)

Tests: approval_modes_imp01 + integration argv (restricted default / admin opt-in). Operator launchd RC_WAKE_APPROVAL_MODE=restricted.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

