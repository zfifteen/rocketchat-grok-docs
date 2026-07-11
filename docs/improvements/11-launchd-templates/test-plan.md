# Test plan: Generate launchd from templates

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-11-TP |
| **Requirements** | [IMP-11](./requirements.md) |

---

## Test cases

### T1 — Render dry-run

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `install-launchd.sh --dry-run` | Prints plist bodies; paths under `$HOME`; no secrets |

**Pass:** R2, R6.

### T2 — Install + load operator

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Install operator | File in LaunchAgents |
| 2 | `launchctl print gui/$UID/…operator` | running |
| 3 | Tail operator log | Connect / no crash loop |

**Pass:** R2, R3, acceptance.

### T3 — Poll disabled

| Step | Action | Expected |
| --- | --- | --- |
| 1 | After install | Poll not loaded **or** Disabled key true |

**Pass:** R4.

### T4 — Idempotent

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Run install twice | No duplicate labels; service still one instance |

**Pass:** R3.

---

## Exit criteria

T1–T4 pass on principal Mac (careful with production).

## Execution record (2026-07-10, skeptic-honest)

Test: imp11_templates_exist; install-launchd.sh render_from_template for operator AND ngrok templates/*.plist.tmpl.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

