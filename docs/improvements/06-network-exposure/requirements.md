# Requirements: Network exposure (bind / 2FA / LAN)

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-06 |
| **Priority** | High |
| **Phase** | D |
| **Status** | Done (2026-07-10) |
| **Primary code** | `docker-compose.yml`, RC admin settings, `ROCKETCHAT.md` |
| **Related** | [IMP-15](../15-compose-secrets-dry/) |

---

## Problem

- Ports: `3000:3000` → all interfaces.
- `Accounts_TwoFactorAuthentication_Enabled: false`.
- LAN URL in secrets is plain HTTP.
- Phone path uses ngrok HTTPS (good) but LAN remains an unauthenticated-network risk if someone has passwords.

---

## Goals

1. Default: RC reachable on host only via localhost (ngrok still works).
2. Document explicit opt-in for LAN bind.
3. Strengthen principal authentication (2FA or equivalent).

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Default compose publish `127.0.0.1:3000:3000` (or equivalent loopback-only). |
| R2 | Optional compose profile or override for LAN bind; documented risk. |
| R3 | ngrok tunnel to `127.0.0.1:3000` continues to work. |
| R4 | Principal account: enable 2FA **or** document why not + compensating control (network isolation only). |
| R5 | Ops runbook states: public = ngrok HTTPS; local = localhost; LAN = optional HTTP. |
| R6 | Bot user may remain password-based until IMP-20 tokens; document residual risk. |

---

## Acceptance criteria

- [x] From another LAN host, port 3000 closed under default compose.
- [x] From Mac localhost and via ngrok public URL, login works.
- [x] Docs updated.

## Implementation notes (2026-07-10)

ports 127.0.0.1:3000; RC_PORT_BIND override; 2FA remains off with loopback+ngrok compensating control


## Partial / compensating

Principal 2FA not enrolled in this session; network exposure reduced via 127.0.0.1 bind + ngrok HTTPS only.
