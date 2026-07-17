## Summary

Recommended improvements so Rocket.Chat multi-agent wakes stop looking like generic failures when the real cause is **restricted tool approval / cancelled headless turns** and **thin FINAL_ERR UX**.

Principal is happy with the RC integration overall; pain is wake/response errors with lost detail.

## Diagnosis (2026-07-16)

| Backend | Restricted | Failure mode |
| --- | --- | --- |
| **Grok** | `--permission-mode auto` | Historical `acceptEdits` → `stopReason=Cancelled` + empty reply (fixed). |
| **Hermes** | no `--yolo` | Channel tools can deny; incomplete work if model does not write a partial reply. |
| **Agy** | `--dangerously-skip-permissions` | Less denial-driven; empty/timeout other classes. |

Channels stay restricted when `RC_WAKE_ADMIN_DMS_ONLY=1`.

Operator success test is basically: **non-empty reply file**. Empty → salvage → else short FINAL_ERR (`stopReason`, `rc`, `approval_mode`, log basename) **without denied tool names**. Full denials live in wake logs under `~/logs/…`.

## Docs package (this repo)

- [`docs/improvements/22-wake-failure-visibility/README.md`](docs/improvements/22-wake-failure-visibility/README.md)
- [`docs/improvements/22-wake-failure-visibility/requirements.md`](docs/improvements/22-wake-failure-visibility/requirements.md) — R1–R12
- [`docs/improvements/22-wake-failure-visibility/test-plan.md`](docs/improvements/22-wake-failure-visibility/test-plan.md)
- Indexed in [`docs/improvements/INDEX.md`](docs/improvements/INDEX.md) as **IMP-22**

## Priority recommendations

### P0

1. **Parse wake logs for tool denials** (`BLOCKED` / User denied / permission strings) and append up to 3 lines into FINAL_ERR (`extract_tool_denials` pure helper + tests).
2. Keep stopReason / rc / approval_mode / log basename; redact secrets.
3. Hermes: document restricted channel policy; prompt hardening to name denied tools; explore mid-tier flag if Hermes has Grok-`auto` analogue.

### P1

4. FINAL_ERR **error-first** (optional thought tail via env).
5. Optional footer on FINAL_OK when denials occurred mid-run.
6. Ops doc: single permission matrix per backend × mode.

### P2

7. Elevate hint on Cancelled channel wakes (`!mode` / DM admin).
8. Stronger wake/mid correlation in FINAL_ERR.
9. Do not regress Agy skip-permissions (empty-reply spam).

## Non-goals

- Default channel YOLO for all bots  
- Pasting full logs into chat  
- Discord migration  
- Full multi-agent thrash package (see improvement 21)

## Implementation home

Runtime (not always in this git tree): `~/.grok/agency/ops/rocketchat/wake/`

- `wake_telemetry.format_final_err` / `choose_final_body`
- `rc_operator_agent` finalize + empty-reply retry
- `wake_lib` approval CLI flags + Hermes inject

## Acceptance (high level)

- [ ] Fixture denial log → FINAL_ERR names the tool  
- [ ] No secrets in bubble  
- [ ] Restricted channels remain default  
- [ ] Agy headless reply-file path still works  
- [ ] Pure tests for extract + format  

## Context

- Principal + hermes thread in #rocketchat-grok-docs (2026-07-16)  
- Related: [improvement 21 operator interaction bugs](docs/improvements/21-operator-interaction-bugs-2026-07-15/)
