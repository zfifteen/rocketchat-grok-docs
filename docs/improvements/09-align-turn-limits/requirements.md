# Requirements: Align Grok turn-limit defaults

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-09 |
| **Priority** | Medium |
| **Phase** | C |
| **Status** | Done (2026-07-10) |
| **Primary code** | `rc_operator_agent.py`, `wake_lib.py`, `rc_call_bot.py`, launchd plist |

---

## Problem

| Location | Default |
| --- | --- |
| Module / `RC_WAKE_MAX_TURNS` | 20 |
| `wake_grok` if env unset | 12 |
| Call bot | 8 |

Production often uses 12 without the operator knowing the module comment says 20.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Single constant `DEFAULT_WAKE_MAX_TURNS` used by argv builder and wake_grok. |
| R2 | launchd sets `RC_WAKE_MAX_TURNS` explicitly. |
| R3 | Call bot documents separate `RC_CALL_MAX_TURNS` default and rationale. |
| R4 | Ops docs state production value and cost tradeoff. |

---

## Acceptance criteria

- [x] No code path uses a different fallback than the constant when env unset.
- [x] Unit test asserts default integer.
- [x] Plist or install script contains the env key.

## Implementation notes (2026-07-10)

DEFAULT_WAKE_MAX_TURNS=12 unified; MAX_TURNS default 12
