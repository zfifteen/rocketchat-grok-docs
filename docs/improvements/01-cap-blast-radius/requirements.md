# Requirements: Cap blast radius of phone-driven Grok

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-01 |
| **Priority** | Critical |
| **Phase** | A — safety |
| **Status** | Done (2026-07-10) |
| **Primary code** | `wake/wake_lib.py` (`build_wake_argv`), `wake/rc_operator_agent.py`, `call/rc_call_bot.py`, launchd env |
| **Related** | [IMP-07](../07-secrets-prompt-hygiene/requirements.md), [IMP-03](../03-single-config-surface/requirements.md) |

---

## Problem

Every operator wake uses `--always-approve`. From Rocket.Chat (including public ngrok), principal messages can drive unrestricted tool execution under:

- DM cwd: `~/.grok/agency`
- Channel cwd: `~/IdeaProjects/<slug>`

There is no config distinction between “answer a question” and “modify system state.”

---

## Goals

1. Default wakes must **not** grant blanket tool approval.
2. Approval policy must be **configurable** (env or single config surface).
3. At least two profiles: **restricted** (default) and **admin** (opt-in).
4. Call-bot path must follow the same policy (or a documented exception).
5. Behavior must be testable without a live phone.

---

## Non-goals

- Replacing Grok CLI auth or API keys.
- Full multi-user RBAC inside Rocket.Chat.
- Removing tools entirely from channel work.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | `build_wake_argv` (or successor) must accept an explicit approval mode: `restricted` \| `admin` (names may vary; two modes minimum). |
| R2 | Default mode for production launchd must be **restricted** unless principal opts into admin. |
| R3 | Restricted mode must not pass `--always-approve`. If CLI requires an alternative flag set, document it; tools that need approval must fail closed or use a safe allowlist. |
| R4 | Admin mode may pass `--always-approve` only when `RC_WAKE_APPROVAL_MODE=admin` (or equivalent) is set on the operator process. |
| R5 | Optional: admin mode only for DMs; channels always restricted (recommended default if dual policy is implemented). |
| R6 | `reply_prompt.txt` must describe what the agent is allowed to do under the active mode. |
| R7 | Call bot must not silently use a more privileged mode than the operator without documentation. |

---

## Non-functional requirements

| ID | Requirement |
| --- | --- |
| N1 | Changing mode must not require editing Python; env/config only. |
| N2 | Mode must appear in operator log on each wake (`approval_mode=…`). |
| N3 | Existing usability tests that assert argv shape must be updated, not deleted. |

---

## Acceptance criteria

- [x] Production default wake argv lacks `--always-approve`.
- [x] Setting admin mode restores `--always-approve` (or documented equivalent).
- [x] Unit tests cover both modes ([test plan](./test-plan.md)).
- [x] Ops docs state the default and how to elevate.

## Implementation notes (2026-07-10)

- `wake_lib.resolve_approval_mode` / `approval_mode_cli_flags` / `build_wake_argv(approval_mode=…)`
- Operator, poll, and call bot pass effective mode; logs include `approval_mode=…`
- Restricted CLI: `--permission-mode acceptEdits` (not `--always-approve`)
- Admin CLI: `--always-approve`; default `RC_WAKE_ADMIN_DMS_ONLY=1`
- Tests: `test_approval_modes_imp01` + integration argv assertions
- launchd: `RC_WAKE_APPROVAL_MODE=restricted`

---

## Dependencies / risks

- Grok CLI may lack a fine-grained allowlist; restricted mode may need “no shell” or “ask” flags — validate against installed CLI.
- Over-restriction may break legitimate agency work in DMs; admin escape hatch required.
