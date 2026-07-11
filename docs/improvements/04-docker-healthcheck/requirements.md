# Requirements: Fix Docker healthcheck

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-04 |
| **Priority** | High |
| **Phase** | B — ops truth |
| **Status** | Done (2026-07-10) |
| **Primary code** | `ops/rocketchat/docker-compose.yml` |
| **Evidence (pre-fix)** | Health log: `exec: "curl": executable file not found`; host `GET /api/info` succeeds |

---

## Problem

Compose healthcheck:

```yaml
test: ["CMD", "curl", "-f", "http://localhost:3000/api/info"]
```

RC image lacks `curl` → status **unhealthy**, failing streak thousands. Operators cannot trust `docker compose ps`.

---

## Goals

1. Health status reflects true HTTP readiness of RC.
2. No dependency on binaries absent from the image (unless installed deliberately).

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Healthcheck must succeed when `/api/info` returns HTTP 200 from inside or via documented equivalent. |
| R2 | Healthcheck must fail when RC process is down. |
| R3 | Prefer tools present in image (e.g. `node`, `wget`) or a Compose healthcheck that uses a sidecar/host pattern documented in ops. |
| R4 | `docker compose ps` shows `healthy` for rocketchat when API is up. |
| R5 | Ops docs (`ROCKETCHAT.md` / [operations](../../operations.md)) note the healthcheck command. |

---

## Acceptance criteria

- [x] With stack up, service status is `healthy` within start_period + retries.
- [x] Stopping rocketchat service flips health to unhealthy/exited appropriately.
- [x] No false unhealthy for missing `curl`.

## Implementation notes (2026-07-10)

node http healthcheck; compose recreated; container healthy


## Skeptic fix (2026-07-10)

docker_health_inspect.txt: health=healthy; ExitCode 0; node healthcheck.
