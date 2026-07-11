# Requirements: PGS / bot auth via shared token surface

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-20 |
| **Priority** | Low |
| **Phase** | D |
| **Status** | Done (2026-07-10) |
| **Depends on** | [IMP-03](../03-single-config-surface/) helpful |
| **Related** | [Related systems — PGS](../../related-systems.md) |

---

## Problem

Operator and PGS notify both use username/password from `rocketchat.env`. Password auth is harder to rotate and broader than needed for REST posting.

---

## Goals

1. Prefer token-based auth for bot REST where RC supports it.
2. One config key set for all bot REST clients.
3. Keep password path as fallback during migration.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Config supports `ROCKETCHAT_OPERATOR_TOKEN` + user id **or** login password (password fallback). |
| R2 | Operator REST client uses token when present. |
| R3 | `pgs_hourly_rocketchat_notify.py` uses same config loader or documented env keys. |
| R4 | Rotation runbook: issue token, update secrets, restart operator, test notify `--dry-run` if available. |
| R5 | Token never logged. |

---

## Non-goals

- Changing PGS research logic.
- OAuth for principal mobile login.

---

## Acceptance criteria

- [x] Token-only auth resolves without password login (operator/media/PGS helpers); full live RC notify with issued PAT not run in-session.
- [x] With token missing, password fallback still works until deprecation date.

## Implementation notes (2026-07-10)

ROCKETCHAT_OPERATOR_TOKEN+USER_ID preferred in _operator_auth; password fallback


## Skeptic fix (2026-07-10)

Proven: token path short-circuits password `rest_login` on PGS + media.login; password fallback still works under mock. Not proven: end-to-end RC post with a real PAT (no token issued on this machine).
