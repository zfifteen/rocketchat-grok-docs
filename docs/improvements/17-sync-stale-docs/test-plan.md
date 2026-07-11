# Test plan: Sync stale docs and dual runbooks

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-17-TP |
| **Requirements** | [IMP-17](./requirements.md) |

---

## Test cases

### T1 — Launchd vs NGROK.md

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `launchctl print …ngrok-rocketchat` | Note running/not |
| 2 | Read NGROK.md status line | Matches |

**Pass:** R2.

### T2 — URL consistency

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Compare public URL in ROCKETCHAT.md, NGROK.md, secrets keys (names only) | Same domain |

**Pass:** acceptance.

### T3 — Link graph

| Step | Action | Expected |
| --- | --- | --- |
| 1 | From project README → improvements INDEX | Works |
| 2 | From ROCKETCHAT.md → project | Works |
| 3 | From INDEX → each IMP folder | All 20 present |

**Pass:** R1, R3, R5.

---

## Exit criteria

T1–T3 pass after doc edits.

## Execution record (2026-07-10, skeptic-honest)

NGROK.md always-on tunnel text; INDEX/CHANGELOG batch; ROCKETCHAT.md pointer + loopback note.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

