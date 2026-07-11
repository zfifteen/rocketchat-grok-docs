# Requirements: Cache REST auth tokens

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-05 |
| **Priority** | High |
| **Phase** | B |
| **Status** | Done (2026-07-10) |
| **Primary code** | `wake/rc_operator_agent.py` (`_operator_auth`, `http_api`, post/update/download) |
| **Related** | [IMP-12](../12-operator-health-watchdog/) |

---

## Problem

`_operator_auth()` calls `/api/v1/login` on each post/update/download helper use. Unnecessary latency and auth churn during wakes.

---

## Goals

1. One login per operator session (until expiry/401).
2. Automatic re-login on auth failure once, then retry request.
3. No credentials in logs.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Process-level cache for `(authToken, userId)` after successful login. |
| R2 | REST helpers use cached token unless missing. |
| R3 | On HTTP 401 (or RC auth error), clear cache, login once, retry original call once. |
| R4 | WebSocket login may share the same token source or stay separate if DDP requires it — document choice; REST path must still be cached. |
| R5 | Concurrent wakes must not stampede login (mutex around login). |

---

## Acceptance criteria

- [x] A single Thinking… → update cycle performs **at most one** login when cache warm (excluding WS connect).
- [x] Forced token invalidation triggers exactly one re-login + successful retry in tests.
- [x] Logs never print password or full token.

## Implementation notes (2026-07-10)

operator _operator_auth cache + 401 retry; auth_login_count in health


## Skeptic fix (2026-07-10)

`imp05_auth_cache_and_401_retry` drives shipped `_operator_auth` (cache) and `_rest_with_auth_retry` (401 refresh) with mocked login/HTTP.
