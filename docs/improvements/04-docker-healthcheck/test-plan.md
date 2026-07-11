# Test plan: Fix Docker healthcheck

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-04-TP |
| **Requirements** | [IMP-04](./requirements.md) |

---

## Preconditions

- Docker Desktop running.
- Ability to `docker compose up -d` in `~/.grok/agency/ops/rocketchat/`.

---

## Test cases

### T1 — Healthy when up

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `docker compose up -d` | Containers start |
| 2 | Wait start_period + 2 intervals | `rocketchat` **healthy** |
| 3 | `curl -s http://127.0.0.1:3000/api/info` | HTTP 200 / JSON |

**Pass:** R1, R4.

### T2 — Unhealthy when broken

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `docker compose stop rocketchat` (or kill) | — |
| 2 | Inspect health / ps | Not healthy |
| 3 | `docker compose start rocketchat` | Returns to healthy |

**Pass:** R2.

### T3 — No curl error in health log

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `docker inspect … --format '{{json .State.Health}}'` | Latest log does **not** say curl not found |

**Pass:** R3.

### T4 — Docs

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Grep ops docs for healthcheck | Documents actual command |

**Pass:** R5.

---

## Exit criteria

T1–T3 pass on principal Mac; T4 updated.

## Execution record (2026-07-10, skeptic-honest)

Compose healthcheck uses node http (not curl). Live: docker_health_inspect.txt status=running health=healthy, port 127.0.0.1:3000. Test: imp04_docker_health_structural.

Suite: `tests/test_usability_contracts.py` + `tests/test_rc_integration.py` exit 0 (zero FAIL).
Scratch: `{SCRATCH}/rc_usability.log`, `rc_integration.log`, `docker_health_inspect.txt` where applicable.

