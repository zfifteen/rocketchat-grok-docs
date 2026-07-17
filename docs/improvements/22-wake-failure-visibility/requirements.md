# Requirements: Wake failure visibility & restricted-tool diagnostics

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-22 |
| **Priority** | High |
| **Phase** | A / B (safety + ops truth) |
| **Status** | Proposed |
| **Related** | IMP-01 (approval), IMP-09 (turn limits), improvement 21 (B3–B5 interaction), NF-SPEC-02 FINAL_ERR |

---

## Problem

1. **Restricted approval** on channel wakes blocks or cancels some tool use depending on backend.
2. When the reply file is empty, the principal sees a **short FINAL_ERR** (stopReason, rc, approval_mode, log name) without **which tool was denied** or the raw BLOCKED text.
3. When the agent still writes a vague reply, mid-turn denials never appear in the bubble.
4. Different backends have different permission flags, so failures feel random across grok / hermes / agy.

### Current backend map (runtime, 2026-07-16)

| Backend | Restricted | Admin | Headless notes |
| --- | --- | --- | --- |
| Grok | `--permission-mode auto` | `--always-approve` | `acceptEdits` historically caused `stopReason=Cancelled` + empty reply (fixed → `auto`) |
| Hermes | no `--yolo` | `--yolo` | Channel restricted: tools may deny; inject says answer + say what failed |
| Agy | `--dangerously-skip-permissions` | same (unless force accept-edits) | Reply-file writes must not hang on TTY approval |

Channels force restricted when `RC_WAKE_ADMIN_DMS_ONLY=1` even if env is admin.

### Operator finalize path

`choose_final_body` (`wake_telemetry.py`):

1. Non-empty reply file → FINAL_OK  
2. Salvage CLI/thought text → FINAL_OK (no denial footnote)  
3. Else `format_final_err` → stopReason / rc / approval_mode / hint / log basename  

Empty-reply auto-retry once on clean Cancelled (B5). Second failure still thin.

---

## Goals

1. Principal can tell **why** a wake failed from the **same activity bubble** (no log spelunking for the common case).
2. Restricted mode stays the channel default; we do **not** require global YOLO.
3. Logs remain the full forensic trail; bubbles get a **safe, short** extract.
4. Behavior is testable with pure fixtures (no live secrets).

---

## Ranked recommended improvements

### P0 — Surface denied tools into FINAL_ERR (R1–R4)

| ID | Requirement |
| --- | --- |
| **R1** | After a wake with empty (or salvage-only) reply file, parse wake log/stdout for permission/tool denials (e.g. `BLOCKED`, `User denied`, `permission`, Hermes/Grok/Agy-specific deny strings). |
| **R2** | Append up to **N=3** distinct denial one-liners to FINAL_ERR (tool name + short reason), redacting secrets/paths under home secrets dirs. |
| **R3** | Keep existing fields: stopReason, rc, approval_mode, log basename, human one-liner. |
| **R4** | Pure function `extract_tool_denials(log_text) -> list[str]` in wake_lib or wake_telemetry + unit tests with fixture logs. |

**Acceptance:** Given a fixture log with a denied `write_file` / `terminal`, FINAL_ERR body includes that tool name without pasting env tokens.

### P0 — Hermes restricted clarity (R5–R6)

| ID | Requirement |
| --- | --- |
| **R5** | Document in inject + ops runbook: channel Hermes = restricted (no yolo); elevate via DM admin / `!mode` for broad tools. |
| **R6** | Investigate Hermes flag parity with Grok `auto` (if any mid-tier exists). If none, keep no-yolo but **require** agent to list denied tools in reply when any tool was refused (prompt hardening). |

**Acceptance:** Restricted Hermes channel wake that hits a denial either writes a useful partial reply naming the tool, or FINAL_ERR includes denial extract (R1).

### P1 — FINAL_ERR always error-first with optional thought tail (R7)

| ID | Requirement |
| --- | --- |
| **R7** | FINAL_ERR composition: structured error block first; optional truncated *Thoughts* tail only if `RC_FINAL_ERR_THOUGHTS=tail` (align phase-chrome plan). Never leave `…` as final. |

**Acceptance:** Long thought stream + empty reply → bubble leads with stopReason/denials, not buried under stream text.

### P1 — Non-empty reply with failed tools (R8)

| ID | Requirement |
| --- | --- |
| **R8** | When reply file is non-empty **and** denial lines were parsed, optionally append a short footer `Tools blocked: …` (env gate `RC_WAKE_DENIAL_FOOTER=1`, default on for FINAL_OK only when denials present). |

**Acceptance:** Agent writes “done-ish” prose but write was denied → principal still sees blocked tool footer.

### P1 — Per-backend permission matrix in ops docs (R9)

| ID | Requirement |
| --- | --- |
| **R9** | Single table in `ROCKETCHAT.md` / this IMP: flags per backend × restricted/admin, plus known failure modes (Cancelled, empty reply, yolo missing). |

**Acceptance:** New operator can predict channel vs DM behavior without reading source.

### P2 — Elevation UX (R10)

| ID | Requirement |
| --- | --- |
| **R10** | When FINAL_ERR stopReason is Cancelled/permission-like on a channel restricted wake, hint line includes concrete elevate path (`!mode` / DM admin) without dumping secrets. |

### P2 — Correlate log without path dump (R11)

| ID | Requirement |
| --- | --- |
| **R11** | FINAL_ERR already has log basename; add `wake_id` / mid short hash if not present so principal can say “find wake-run-… matching mid=…” in one message to an agent. |

### P2 — Do not weaken Agy skip-permissions accidentally (R12)

| ID | Requirement |
| --- | --- |
| **R12** | Changes to Agy argv must keep headless reply-file write working; any re-introduction of accept-edits requires TTY or will regress empty FINAL_ERR spam. |

---

## Explicit non-goals

| ID | Non-goal |
| --- | --- |
| N1 | Default channel `--yolo` / `--always-approve` for all bots. |
| N2 | Pasting full wake logs into Rocket.Chat. |
| N3 | Discord migration (see channel discussion 2026-07-16). |
| N4 | Fixing all multi-agent thrash (tracked under improvement 21). |

---

## Implementation sketch (runtime)

Primary touch points (not in this docs repo’s live code; live under agency ops):

- `wake_telemetry.format_final_err` / `choose_final_body`
- `rc_operator_agent` finalize path after `wake_*` returns
- `wake_lib.hermes_approval_cli_flags` / inject templates
- Optional: stream thought salvage already present — do not let it skip denial footer

Docs touch:

- This IMP folder
- `docs/improvements/INDEX.md`
- Optional pointer from improvement 21 README

---

## Priority order for implementers

1. R1–R4 denial extract + FINAL_ERR (biggest UX win)  
2. R7 error-first  
3. R5–R6 Hermes docs/prompt  
4. R8 denial footer on partial success  
5. R9–R11 docs/UX polish  
6. R12 regression guard for Agy  

---

## Source analysis references

- Principal diagnosis: tool approval → lost error detail (2026-07-16 #rocketchat-grok-docs)  
- Hermes analysis (same thread): backend permission matrix + FINAL_ERR thinness  
- Code: `wake_lib.approval_mode_cli_flags`, `hermes_approval_cli_flags`, `build_agy_wake_argv`  
- Code: `wake_telemetry.choose_final_body`, `format_final_err`  
- Historical: acceptEdits Cancelled incident comment in `approval_mode_cli_flags`  
