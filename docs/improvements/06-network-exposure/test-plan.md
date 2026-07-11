# Test plan: Network exposure (bind / 2FA / LAN)

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-06-TP |
| **Requirements** | [IMP-06](./requirements.md) |

---

## Test cases

### T1 — Loopback-only default

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `docker compose ps` / `docker port` | Bind `127.0.0.1:3000` not `0.0.0.0` |
| 2 | `curl http://127.0.0.1:3000/api/info` | Success |

**Pass:** R1.

### T2 — ngrok still works

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Public `/api/info` via ngrok domain | Success |
| 2 | Mobile app workspace URL still logs in | Success |

**Pass:** R3.

### T3 — LAN blocked by default

| Step | Action | Expected |
| --- | --- | --- |
| 1 | From another device on LAN: `http://<mac-lan-ip>:3000` | Connection refused / timeout |
| 2 | With LAN profile enabled (if testing override) | Reachable; docs warn HTTP |

**Pass:** R1, R2.

### T4 — 2FA / compensating control

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Check principal 2FA setting or written exception | Meets R4 |

**Pass:** R4, R5.

---

## Exit criteria

T1–T2 mandatory; T3–T4 completed with evidence.

## Execution record (2026-07-10, skeptic-honest)

Compose RC_PORT_BIND default 127.0.0.1; docker port shows 127.0.0.1:3000. 2FA not enrolled — compensating control only (documented).

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

