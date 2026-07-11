# Requirements: Pinned venv dependencies (no runtime pip)

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-13 |
| **Priority** | Medium |
| **Phase** | C |
| **Status** | Done (2026-07-10) |
| **Primary code** | `rc_operator_agent.py` import block; launchd `PYTHON_BIN` |
| **Related** | [IMP-11](../11-launchd-templates/), [IMP-16](../16-extract-code-project/) |

---

## Problem

On missing import, operator runs `pip install websocket-client -q` under framework Python — supply-chain and offline risk; mutates global env from KeepAlive.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | `requirements.txt` (and optional lock) listing runtime deps (`websocket-client`, call-bot deps if any). |
| R2 | Documented venv path (e.g. `ops/rocketchat/.venv` or `~/.grok/agency/ops/rocketchat/.venv`). |
| R3 | `run_operator_agent.sh` / launchd use venv `python`. |
| R4 | No `pip install` in production import path; missing dep → clear error exit. |
| R5 | `setup-venv.sh` creates/updates venv idempotently. |

---

## Acceptance criteria

- [x] Operator starts offline if venv already built.
- [x] Grep shows no runtime pip install in operator/call entrypoints.
- [x] Tests run under same venv.

## Implementation notes (2026-07-10)

requirements.txt + setup-venv.sh; no runtime pip install
