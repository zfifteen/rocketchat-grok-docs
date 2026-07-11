# Test plan: Extract integration code to a project

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-16-TP |
| **Requirements** | [IMP-16](./requirements.md) |

---

## Test cases

### T1 — Unit suite in new tree

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Run integration + usability tests from new repo | All pass |

**Pass:** R1.

### T2 — Install cutover

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Follow migration runbook | launchd points at new scripts |
| 2 | DM smoke: Thinking… → answer | Works |
| 3 | Channel smoke | cwd still IdeaProjects mapping |

**Pass:** R2–R5, acceptance.

### T3 — Secrets isolation

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Confirm secrets still only under agency/secrets | Not in app git |
| 2 | `git status` in app repo | No .env with passwords |

**Pass:** R2, R3.

### T4 — Docs consistency

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Update filesystem map + INDEX status | Paths match reality |

**Pass:** R4, acceptance.

---

## Exit criteria

T1–T4 after cutover window.

## Execution record (2026-07-10, skeptic-honest)

Won't do — live cutover deferred; portable surface is rc_config + install-launchd.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

