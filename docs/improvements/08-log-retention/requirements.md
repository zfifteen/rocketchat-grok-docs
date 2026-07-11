# Requirements: Log and artifact retention

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-08 |
| **Priority** | Medium–high |
| **Phase** | B |
| **Status** | Done (2026-07-10) |
| **Paths** | `~/logs/rocketchat-dm-wake/`, `~/logs/ngrok-rocketchat/` |

---

## Problem

Unbounded growth of `wake-prompt-*.txt`, `wake-run-*.log`, `call-media/`, STT caches. Prompts contain principal message text (privacy + disk).

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Configurable retention: max age and/or max count for wake-prompt, wake-run, call-media, audio cache. |
| R2 | Default policy documented (e.g. 7 days prompts, 14 days logs, 3 days call-media). |
| R3 | Prune job: launchd interval **or** prune-on-start in operator — pick one, document. |
| R4 | Optional `RC_KEEP_WAKE_PROMPTS=0` deletes prompt files after successful wake. |
| R5 | Never delete `media-post-ledger.json` automatically without size-cap strategy (ledger is correctness-critical). |
| R6 | Prune must not touch files newer than active wake (skip locked/in-use if detectable). |

---

## Acceptance criteria

- [x] After prune, artifact counts drop under policy.
- [x] Ledger file remains.
- [x] Dry-run mode lists candidates without delete.

## Implementation notes (2026-07-10)

prune_log_artifacts + scripts/prune_logs.py + prune-on-start
