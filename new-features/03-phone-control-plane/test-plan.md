# Test plan: Phone control plane (slash commands, approval cards, mission control)

| Field | Value |
| --- | --- |
| **ID** | NF-TP-03 |
| **Feature** | Phone control plane — slash commands, approval cards, room mission control |
| **Spec** | [`./spec.md`](./spec.md) (NF-SPEC-03) |
| **Implementation plan** | [`./implementation-plan.md`](./implementation-plan.md) (NF-IP-03) |
| **Research** | [`./research.md`](./research.md) |
| **Related** | IMP-01 approval modes, `wake_lib.resolve_approval_mode`, `state.json` pins, `health.json` |
| **Type** | Unit (parse/FSM/allowlist) + contract routing + optional live RC command probes |
| **Status** | Test-planning documentation only · **Last reviewed:** 2026-07-11 (`/model` `/effort` `/goal`) |
| **Flags under test** | `RC_CONTROL_PLANE`, `RC_ELEVATION`, `RC_CMD_PREFIXES`, `RC_ADMIN_CONFIRM_S`, `RC_ADMIN_TTL_S`, `RC_STATUS_PIN` |

---

## 1. Scope and traceability

### 1.1 In scope

- Principal-only command vs content routing  
- v1 command set behavior (help/status/health/new/cwd/mode/**model/effort/goal**/admin/cancel/retry/wake/ask)  
- Room pins for model/effort/goal applied on next wake argv / prompt  
- TUI-only commands do not research-wake (taxonomy Class D/E)
- Elevation arming: confirm, once consume, TTL, deny, audit  
- Path allowlist for `/cwd pin`  
- Non-command wake path unchanged  
- Mission card field presence  

### 1.2 Out of scope

- Implementing interceptor in operator (this package)  
- Apps-Engine buttons as v1 requirement  
- Multi-user RBAC  

### 1.3 Requirement map

| Spec | Cases |
| --- | --- |
| FR-C1–C4, AC-C3 | TP-C-01, TP-C-02, E-C-nonprincipal |
| FR-C5–C7 | TP-C-03, TP-C-04 |
| FR-C8, AC-C2 | TP-C-05 |
| FR-C9, AC-C6 | TP-C-06, E-C-path* |
| FR-C10–C11, AC-C1 | TP-C-07, TP-C-08 |
| FR-C12–C14 | TP-C-09, TP-C-10, TP-C-11 |
| FR-C15–C22, AC-C4–C5, AC-C8 | TP-C-12 … TP-C-17 |
| FR-C23–C25 | TP-C-07 |
| AC-C7, AC-C9 | TP-C-18, TP-C-19 |

---

## 2. Test strategy and layers

| Layer | Proves |
| --- | --- |
| **L0 Unit** | `parse_command`, path allowlist, elevation FSM, confirm timeout |
| **L1 Contract** | Mock principal messages → assert wake_spawned true/false + argv mode |
| **L2 State persistence** | Elevation survives operator process restart (reload state.json) |
| **L3 Live opt-in** | Real RC `/status` latency; no wake-run log |
| **L4 Regression** | Usability contracts for normal “hello” wakes |

---

## 3. Preconditions

- Test harness can inject principal messages into operator handle path (or pure dispatcher under test)  
- Temp `state.json` / health.json fixtures  
- Fake clock for confirm TTL and admin TTL  
- Existing directory under `~/IdeaProjects/...` for successful pin tests  

---

## 4. Concrete test cases

### TP-C-00 — Master flag disables control plane

| | |
| --- | --- |
| **Phase** | P0 |
| **Preconditions** | `RC_CONTROL_PLANE=0` |
| **Steps** | Principal sends `/status` and `/new`. |
| **Expected** | Both treated as **content** wakes (Thinking… path); no command short-circuit (FR-C0). |
| **Pass** | wake_spawned=true for both; no special status card |

### TP-C-01 — Non-principal ignored

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Message from username ≠ principal: `/status` and `hello`. |
| **Expected** | No command reply; no wake (FR-C1). |
| **Pass** | Filter assertions |

### TP-C-02 — Unknown command no wake

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Principal `/foo_bar_unknown`. |
| **Expected** | Short help/error from grok; **no** Grok CLI process; no wake-run log (FR-C4, AC-C3). |
| **Pass** | wake_spawned=false |

### TP-C-03 — Parse grammar

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Table-drive: `/status`, `/STATUS`, `  /cwd pin /x  `, `!status`, `/wake hi there`, not-command `hello`, `/`. |
| **Expected** | Correct cmd/args; `!` alias works; `/` alone unknown; content not command (FR-C5–C6). |
| **Pass** | Parser unit table |

### TP-C-04 — `/help` lists v1 commands (first-class)

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | A) `/help`. B) `!help` if `!` in `RC_CMD_PREFIXES`. C) `/HELP` (case). |
| **Expected** | Reply from `grok` lists v1 set with one-line semantics each; includes at least help, status, health, new, cwd, mode, **model, effort, goal**, admin, cancel, retry (FR-C7, FR-C7a). No Thinking… research wake; no `wake-run-*.log` (FR-C3). Latency &lt;2s healthy (NFR-C1, AC-C0). |
| **Pass** | Substring checks + no CLI spawn |

### TP-C-04b — `/help` topic + elevation-off

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | A) `/help admin`. B) `/help notacommand`. C) With `RC_ELEVATION=0`, send `/help`. |
| **Expected** | A) Short usage for admin elevation (`once`/`on`/`off` / confirm). B) Unknown topic → full list or explicit unknown + full list; no CLI wake (FR-C7b). C) Help still works when elevation disabled (FR-C7c, AC-C0b–C0c). |
| **Pass** | Body + env matrix |

### TP-C-04c — `/model` pin → argv

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | A) `/model` (show). B) `/model grok-build` (or known id). C) content `hello`. D) `/model clear`. E) content again. |
| **Expected** | A/B no CLI research wake. C argv includes `-m`/`--model` with pinned id (FR-C7d–e, AC-C0d). D clears pin. E no model flag (or env default only). |
| **Pass** | State + argv capture |

### TP-C-04d — `/effort` pin → argv

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | A) `/effort high`. B) content wake. C) `/effort notalevel`. D) `/effort clear`. |
| **Expected** | B argv includes `--reasoning-effort` or `--effort high` (FR-C7f–g, AC-C0e). C reject, no pin change. D clears. |
| **Pass** | Argv + error body |

### TP-C-04e — `/goal` pin + goal-aware wake

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | A) `/goal Ship the control plane docs`. B) `/status`. C) content `continue`. D) `/goal status`. E) `/goal clear`. |
| **Expected** | A sets pin active. B card shows goal summary (FR-C23). C wake prompt contains objective block (FR-C7i, AC-C0f). D reports status. E removes pin; later wake has no goal block. |
| **Pass** | State + prompt file / argv side effects |

### TP-C-04f — `/mode` ≠ `/model`; TUI-only no wake

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | A) `/mode`. B) `/model`. C) `/theme`. D) `/quit`. |
| **Expected** | A approval/elevation. B model pin surface. C/D unsupported or unknown→`/help`; **no** multi-turn research wake (FR-C7j–k, AC-C0g). |
| **Pass** | Body class + wake_spawned=false |

### TP-C-05 — /new clears session pin

| | |
| --- | --- |
| **Phase** | P0 |
| **Preconditions** | Room has session pin S1; optional model/effort/goal pins set |
| **Steps** | `/new`; then content wake. |
| **Expected** | Session pin cleared; next wake not `--resume S1` (new session) (FR-C8, AC-C2). Model/effort/goal pins **retained** by default (OD-C8) unless product chooses otherwise. |
| **Pass** | State + argv |

### TP-C-06 — /cwd pin allowlist

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | A) `/cwd pin` valid IdeaProjects path that exists. B) `/cwd pin /etc`. C) `/cwd pin ~/IdeaProjects/../.ssh`. |
| **Expected** | A accept; B/C reject (FR-C9, AC-C6). |
| **Pass** | State pin only for A |

### TP-C-07 — /status mission card + latency

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | `/status`; measure time; inspect body. |
| **Expected** | Card includes operator/ws, mode, session, cwd, last wake fields; **no** wake-run file created; **< 2 s** when healthy (FR-C10, FR-C23, AC-C1, NFR-C1). |
| **Pass** | Field checklist + timing |

### TP-C-08 — /health

| | |
| --- | --- |
| **Steps** | With healthy health.json; with stale health.json. |
| **Expected** | Reflects ws/freshness; should mention RC reachability if implemented (FR-C11). |
| **Pass** | Two fixture variants |

### TP-C-09 — /cancel kills owned wake

| | |
| --- | --- |
| **Phase** | P2 |
| **Preconditions** | Fake long-running wake child PID owned by operator |
| **Steps** | `/cancel` in that room. |
| **Expected** | Child terminated; lock cleared (FR-C12). |
| **Pass** | PID gone |

### TP-C-10 — /retry

| | |
| --- | --- |
| **Phase** | P2 |
| **Preconditions** | last_content_by_room set to “retry me” |
| **Steps** | `/retry` with empty buffer; then with buffer. |
| **Expected** | Empty → error no wake; with buffer → wake with that text (FR-C13). |
| **Pass** | |

### TP-C-11 — /wake and /ask

| | |
| --- | --- |
| **Steps** | `/wake do the thing`; `/ask explain X`. |
| **Expected** | Normal Thinking… wake path with given text (FR-C14). |
| **Pass** | wake_spawned=true; prompt contains text |

### TP-C-12 — /admin once confirm yes

| | |
| --- | --- |
| **Phase** | P1 |
| **Steps** | `/admin once` → bot confirm → `yes` → content “hello”. |
| **Expected** | That wake argv has `--always-approve`; elevation consumed (FR-C16–C18, AC-C4). |
| **Pass** | argv + state uses_remaining=0 |

### TP-C-13 — /admin once confirm no

| | |
| --- | --- |
| **Steps** | `/admin once` → `no` → content. |
| **Expected** | Restricted argv; no elevation (AC-C5). |
| **Pass** | |

### TP-C-14 — Confirm timeout

| | |
| --- | --- |
| **Steps** | `/admin once`; advance clock past `RC_ADMIN_CONFIRM_S`; `yes`. |
| **Expected** | yes ignored or denied; no arm (NFR-C3). |
| **Pass** | Fake clock |

### TP-C-15 — Once does not leak to second wake

| | |
| --- | --- |
| **Steps** | Arm once; wake1 admin; wake2. |
| **Expected** | wake2 restricted (FR-C18). |
| **Pass** | |

### TP-C-16 — /admin on TTL

| | |
| --- | --- |
| **Steps** | Confirm `/admin on`; wake within TTL admin; after expiry restricted. |
| **Expected** | FR-C19 |
| **Pass** | Fake clock |

### TP-C-17 — Audit log lines

| | |
| --- | --- |
| **Steps** | Grant, deny, consume, expire elevation. |
| **Expected** | Operator log contains audit events (FR-C20, AC-C8). |
| **Pass** | Log substring |

### TP-C-18 — Content path unchanged

| | |
| --- | --- |
| **Steps** | Principal `hello` (no slash). |
| **Expected** | Thinking… → wake → finalize as today (AC-C7). |
| **Pass** | |

### TP-C-19 — Usability contracts

| | |
| --- | --- |
| **Steps** | Full usability suite. |
| **Expected** | Pass (AC-C9). |
| **Pass** | Exit 0 |

### TP-C-20 — /admin off

| | |
| --- | --- |
| **Steps** | Arm TTL; `/admin off`; wake. |
| **Expected** | Restricted (FR-C / research). |
| **Pass** | |

### TP-C-21 — /mode display

| | |
| --- | --- |
| **Steps** | Restricted; then armed once; `/mode`. |
| **Expected** | Shows base + elevation state (FR-C / UX). |
| **Pass** | |

### TP-C-22 — yes/no only when pending

| | |
| --- | --- |
| **Steps** | Send `yes` with no pending confirm. |
| **Expected** | Treated as **content** wake (or ignored per spec)—must **not** arm admin. Document chosen behavior; prefer content wake. |
| **Pass** | No elevation |

### TP-C-23 — Elevation persists restart

| | |
| --- | --- |
| **Phase** | P1 / L2 |
| **Steps** | Arm once; reload state from disk; next wake. |
| **Expected** | Still armed until consumed (FR-C22). |
| **Pass** | |

---

## 5. Edge cases and negative / failure cases

| ID | Edge / failure | Expected |
| --- | --- | --- |
| **E-C-nonprincipal** | grok or other user sends `/admin once` | Ignored |
| **E-C-01** | Command injection ` /cwd pin $(rm -rf /)` | No shell; reject or safe parse |
| **E-C-02** | `/cwd pin` symlink escaping allowlist | Reject after realpath |
| **E-C-03** | `/cwd pin` nonexistent path | Reject |
| **E-C-04** | `/cwd pin` file not directory | Reject or document |
| **E-C-05** | Null bytes / control chars in args | Reject |
| **E-C-06** | Very long `/wake` text (>100k) | Cap or reject; no OOM |
| **E-C-07** | `/retry` after `/new` | Buffer policy documented (keep or clear) |
| **E-C-08** | `/cancel` with no active wake | Friendly error; no crash |
| **E-C-09** | `/cancel` PID not owned | Do not kill foreign PID (SR-C4) |
| **E-C-10** | Double `/admin once` pending | Second replaces or rejects; deterministic |
| **E-C-11** | Content message “yes” during pending | Confirms elevation (not research wake) |
| **E-C-12** | Content “yes, please fix bugs” during pending | Prefer exact `yes` only; else deny or content—document |
| **E-C-13** | Room A elevation must not affect room B | Isolation |
| **E-C-14** | Channel vs DM admin policy + elevation | Elevation still room-scoped; base resolve_approval_mode respected when none |
| **E-C-15** | Help spam loop `/help` × 50 | Rate limit (NFR-C4) |
| **E-C-16** | Mobile sends fullwidth `／status` | Unknown or normalized—document |
| **E-C-17** | Leading slash with zero-width chars | Reject unknown |
| **E-C-24** | `/model` with spaces / display name | Resolve case-insensitively when catalog available; else store raw |
| **E-C-25** | `/effort` on non-reasoning model | Pin allowed; CLI may ignore — document in `/status` if known |
| **E-C-26** | `/goal` with empty args | Show status (same as bare `/goal`) |
| **E-C-27** | Room A model pin does not affect room B | Isolation |
| **E-C-28** | `/m` alias for `/model` | Accepted if Class B aliases enabled |
| **E-C-18** | state.json corrupt | Defaults; no crash; log |
| **E-C-19** | Concurrent commands + content in same room | Serialized by room lock |
| **E-C-20** | `/status` during active wake | Shows draining/phase if available; no deadlock |
| **E-C-21** | Secrets in status card | Must not print tokens (FR-C25) |
| **E-C-22** | `/session show` when no pin | Explicit “none” |
| **E-C-23** | Admin once consumed by `/wake` | Explicit wake uses admin and consumes |
| **E-C-24** | Operator down | Commands fail closed; principal sees no false “online” if health stale |

---

## 6. Pass / fail and exit criteria

| Phase | Exit when |
| --- | --- |
| P0 | TP-C-00–08,18 + path edges E-C-01–04 |
| P1 | TP-C-12–17,20–23 + E-C-10–14 |
| P2 | TP-C-09–11 + E-C-08–09 |
| P3+ | Pin status / cross-room when specified |

**Hard fails:** non-principal elevation; shell injection; kill foreign PID; unknown command triggers research wake; elevation without confirm when confirm required.

**Evidence:** argv captures, state.json snapshots, audit log lines, timing for `/status`.

---

## 7. Open / blocked

| Item | Note |
| --- | --- |
| Exact `yes` vs soft confirm | OD / document in implement |
| Apps-Engine buttons | P4; not v1 gate |
| Call commands | After NF-SPEC-01 |

---

## 8. References

- NF-SPEC-03 command table §6.1, elevation FSM §4.3, AC-C1–C9  
- Research §3.1–3.3  
- `resolve_approval_mode`, `approval_mode_cli_flags`  
- Usability contracts for non-command wakes  
