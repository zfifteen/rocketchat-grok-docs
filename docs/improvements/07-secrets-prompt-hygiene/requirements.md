# Requirements: Secrets out of model prompt

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-07 |
| **Priority** | High |
| **Phase** | A — safety |
| **Status** | Done (2026-07-10) |
| **Primary code** | `wake/reply_prompt.txt`, `wake/rc_operator_agent.py` (`build_prompt`) |
| **Related** | [IMP-01](../01-cap-blast-radius/), [IMP-05](../05-cache-rest-auth/) |

---

## Problem

`reply_prompt.txt` tells the model it may load `~/.grok/agency/secrets/rocketchat.env` for extra history. That invites passwords into model context and tool reads.

---

## Goals

1. Wake prompts never instruct reading secrets files.
2. Optional room history is fetched by the **operator process** and injected as plain text snippets.
3. Explicit ban on dumping env/secrets into reply file (keep/strengthen).

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Remove or rewrite prompt lines that mention secrets file paths. |
| R2 | Prompt must say: do not open secrets, `.env`, or password stores. |
| R3 | If history is needed, operator prefetches N messages via REST (cached auth) and includes truncated text in `{{CONTEXT}}`. |
| R4 | Injected history must not include auth tokens or password fields. |
| R5 | Media helper path may still use secrets **out of process** (Python script), not via model reading the file. |

---

## Acceptance criteria

- [x] `grep -i secret reply_prompt.txt` shows only “do not dump secrets” style bans, not load paths.
- [x] Unit test: built prompt contains no `rocketchat.env` path.
- [x] Optional: operator injects history block when `RC_INJECT_HISTORY=1`.

## Implementation notes (2026-07-10)

reply_prompt no longer instructs loading rocketchat.env
