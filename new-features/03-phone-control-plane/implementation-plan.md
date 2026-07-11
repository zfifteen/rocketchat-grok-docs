# Implementation plan: Phone control plane (slash commands, approval cards, mission control)

| Field | Value |
| --- | --- |
| **ID** | NF-IP-03 |
| **Feature** | Phone control plane — slash commands, approval cards, mission control |
| **Spec** | [NF-SPEC-03](./spec.md) (**source of truth for flags & shalls**, incl. FR-C0 master switch) |
| **Test plan** | [NF-TP-03](./test-plan.md) (**source of truth for validation gates**, incl. TP-C-00) |
| **Research** | [research.md](./research.md) |
| **Runtime home** | `~/.grok/agency/ops/rocketchat/wake/` (operator message path, `state.json`, `wake_lib` approval helpers) |
| **Status** | Implementation-planning documentation only · **Last reviewed:** 2026-07-10 |

---

## 1. Overview and goals

### 1.1 Problem

Phone-driven Grok lacks deterministic ops controls: session reset, health, and safe one-shot admin elevation require Mac/env edits. Freeform “/new” interpretation is unreliable.

### 1.2 Primary objective

Insert a **principal-only command interceptor** before the Thinking… wake path so `/status`, `/new`, `/admin once`, `/cancel`, etc. execute in-process, with room-scoped elevation tokens audited and non-command wakes unchanged.

### 1.3 Success metrics

| Metric | Target |
| --- | --- |
| `/status` latency | &lt; 2 s healthy |
| Unknown `/foo` spawns Grok CLI | Never |
| `/admin once` + yes → next wake admin only | Pass AC-C4 |
| Non-command “hello” | Unchanged Thinking… path |
| Path traversal pin | Rejected |
| Usability contracts | Green |

---

## 2. Assumptions

| Assumption | Note |
| --- | --- |
| Principal-only filter remains | Do not broaden trust |
| `resolve_approval_mode` + `approval_mode_cli_flags` stay source of base mode | Elevation is overlay |
| Operator owns message enqueue path | Single place to intercept |
| Apps-Engine not required for v1 | C1 operator-native |
| NF-IP-02 T0 improves `/status` stopReason | Soft dependency |

---

## 3. Design execution summary

```
on principal message:
  if is_command(text):
    dispatch → reply as grok (postMessage short)
    mark processed; return
  if pending_confirm and text in {yes,no}:
    handle confirm; return
  else:
    existing _enqueue / Thinking… / wake
      effective_mode = elevation or resolve_approval_mode
```

**New modules (suggested):**

| Module | Responsibility |
| --- | --- |
| `wake/rc_commands.py` | parse, dispatch, help text |
| `wake/rc_elevation.py` | FSM, persist, consume, audit log helpers |
| `wake/rc_cwd_policy.py` | allowlist realpath pin checks |

Or single `wake/control_plane.py` if preferred — keep pure functions unit-testable without RC network.

---

## 4. Phased work breakdown

### Phase P0 — Read-only + session/cwd commands  
**Effort:** 2–3 d  
**Risk:** Low if routing tests first

| # | Task | Deliverables | Validation (NF-TP-03) |
| --- | --- | --- | --- |
| P0.1 | `parse_command(text, prefixes)` pure | Table-driven unit tests | TP-C-03 |
| P0.2 | Interceptor hook in principal handler **before** enqueue | `rc_operator_agent.py` | TP-C-01, TP-C-02, TP-C-18 |
| P0.3 | `/help`, `/status`, `/health`, `/mode` | Card builders using health.json + state pins | TP-C-04,07,08,21 |
| P0.4 | `/new`, `/session show|reset` | Clear session pin | TP-C-05, E-C-22 |
| P0.5 | `/cwd`, `/cwd pin`, `/cwd clear` + allowlist | realpath policy | TP-C-06, E-C-01–04 |
| P0.6 | Contract: unknown command no `wake_grok` | Mock | AC-C3 |
| P0.7 | Docs: command list in ROCKETCHAT.md | Runbook | Review |

**Exit:** P0 commands work live; no CLI for `/status`.  
**Rollback:** Feature flag `RC_CONTROL_PLANE=0` disables interceptor.

---

### Phase P1 — Elevation (admin once / TTL)  
**Effort:** 2–4 d  
**Depends on:** P0

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| P1.1 | Elevation state schema in `state.json` | Load/save atomic | FR-C22, TP-C-23 |
| P1.2 | `/admin once|on|off` + pending confirm | FSM | TP-C-12–16,20 |
| P1.3 | Confirm window `yes`/`no` exact match | Fake clock tests | TP-C-14, E-C-11–12 |
| P1.4 | `effective_approval_mode(room)` overlay in drain wake | Wire to `wake_grok` | TP-C-12,15, AC-C4 |
| P1.5 | Audit log lines grant/deny/consume/expire | operator-agent.log | TP-C-17, AC-C8 |
| P1.6 | Room isolation tests A vs B | Unit | E-C-13 |
| P1.7 | Help + `/mode` show elevation | UX | TP-C-21 |

**Exit:** One elevated wake then restricted; deny/timeout work.  
**Rollback:** Clear elevation keys; `RC_CONTROL_PLANE` off; or disable admin commands only via `RC_ELEVATION=0`.

---

### Phase P2 — Cancel / retry / explicit wake  
**Effort:** 2–3 d  
**Depends on:** P0 (P1 optional but useful)

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| P2.1 | Track wake child PID per room | During `_run_wake_once` | Ownership |
| P2.2 | `/cancel` SIGTERM owned child + lock clear | Safe kill | TP-C-09, E-C-08–09 |
| P2.3 | `last_content_by_room` buffer (cap size) | State | TP-C-10, E-C-06–07 |
| P2.4 | `/retry`, `/wake`, `/ask` | Enqueue content path | TP-C-10,11, E-C-23 |
| P2.5 | Elevation consume on `/wake` explicit | Same as content | E-C-23 |

**Exit:** Runaway wake stoppable from phone; retry works.  
**Rollback:** Disable cancel/retry commands if PID tracking unstable.

---

### Phase P3 — Polish / telemetry alignment  
**Effort:** 1–2 d  
**Depends on:** P0; NF-IP-02 T0/T3 preferred

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| P3.1 | `/status` includes last_stop_reason from health | Card fields | Cross NF-TP-02 |
| P3.2 | Optional `RC_STATUS_PIN=1` single pin + chat.update | Pin id in state | FR-C24 |
| P3.3 | Help rate limit | Counter | E-C-15 |
| P3.4 | Optional `/ops` cross-room (if time) | DM-only | OD-C6 |

---

### Phase P4 — Apps-Engine (optional)  
**Effort:** 4–7 d  
**Depends on:** P1 stable

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| P4.1 | Slashcommand app skeleton for RC 8.6 | Private app | Install smoke |
| P4.2 | Buttons for admin approve/deny | UI kit | Manual mobile |
| P4.3 | Webhook/local bridge to operator | Auth localhost only | Security review |

**Not required for production “control plane v1.”**

---

## 5. File and integration map

| File | Phases | Change |
| --- | --- | --- |
| `wake/rc_operator_agent.py` | P0–P2 | Intercept; PID track; effective mode |
| `wake/wake_lib.py` | P1 | Maybe export elevation-aware resolve helper |
| `wake/state.json` (runtime) | P0–P2 | New keys (not in git) |
| New pure modules | P0–P1 | Commands, elevation, cwd policy |
| `wake/reply_prompt.txt` | P0 | Note slash commands exist; don’t freeform /admin |
| launchd env | P0 | Optional `RC_CONTROL_PLANE=1` |
| `tests/test_usability_contracts.py` | P0–P2 | Routing + elevation argv |
| `ops/ROCKETCHAT.md` | P0–P2 | Command reference |
| `NO_DUPLICATE_POSTS.md` | P0 | Command replies are separate intentional posts (not answer duplicates) |

**Critical integration points:**

1. Intercept **after** principal filter, **before** Thinking…  
2. Commands mark `processed_ids` so they never re-wake  
3. Elevation consumed exactly once on next wake that runs `wake_grok`  
4. `/cancel` must not kill unrelated PIDs (SR-C4)

---

## 6. Dependencies and sequencing

| Dependency | Note |
| --- | --- |
| NF-IP-02 T0 | Better stopReason on status — implement first if possible |
| NF-IP-01 | Call commands later (P4+/separate) |
| IMP-01 | Elevation overlays restricted default — do not remove restricted |

**Org recommendation:** **NF-IP-02 T0 → NF-IP-03 P0 → P1 → NF-IP-02 T1 → NF-IP-03 P2**. Voice (NF-IP-01) parallel track.

---

## 7. Rollout, flags, rollback

### Flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `RC_CONTROL_PLANE` | `1` after soak, `0` during first PR optional | Master switch |
| `RC_ELEVATION` | `1` | Disable admin cmds if needed |
| `RC_CMD_PREFIXES` | `/,!` | Prefixes |
| `RC_ADMIN_CONFIRM_S` | `60` | Confirm TTL |
| `RC_ADMIN_TTL_S` | `900` | `/admin on` |
| `RC_STATUS_PIN` | `0` | Sticky pin |

### Cutover

1. Deploy P0 with `RC_CONTROL_PLANE=1` on operator.  
2. Principal exercises `/status` `/new` `/help` from phone.  
3. Deploy P1; test `/admin once` carefully on non-prod room if available.  
4. Deploy P2 cancel only after PID tracking verified in logs.  
5. Document commands in runbook.

### Rollback

1. `RC_CONTROL_PLANE=0` + kickstart → full legacy wake behavior.  
2. Or clear `room_elevation` / `pending_confirm` in state.json if stuck elevated.  
3. Git revert if interceptor bugs.

**RTO:** &lt; 5 minutes for flag disable.

---

## 8. Validation mapping (NF-TP-03)

| Phase | Gate |
| --- | --- |
| P0 | TP-C-01–08,18; E-C-01–04 |
| P1 | TP-C-12–17,20–23; E-C-10–14 |
| P2 | TP-C-09–11; E-C-08–09 |
| Always | TP-C-19 usability |

Security hard fails: shell injection, foreign PID kill, non-principal elevation, unknown command wake.

---

## 9. Risks and ops impact

| Risk | Mitigation |
| --- | --- |
| Interceptor breaks all wakes | Flag off; extensive routing tests first |
| Accidental long-lived admin | Prefer once; TTL; `/mode` visibility |
| yes/no vs content collision | Exact match only when pending |
| Cancel wrong process | PID ownership file |
| state.json growth | Cap last_content size; prune elevation |
| Help spam | Rate limit |

**Ops impact:** Principal self-serve ops; fewer launchd edits; audit log volume up slightly.

---

## 10. Suggested PR stack

| PR | Scope |
| --- | --- |
| PR1 | Parse + interceptor skeleton + `/help` `/status` `/health` (flag default on in dev) |
| PR2 | `/new` `/cwd` allowlist + tests |
| PR3 | Elevation FSM + effective mode wire |
| PR4 | `/cancel` `/retry` `/wake` + PID tracking |
| PR5 | Runbook + pin optional |

---

## 11. Effort summary

| Phase | Eng-days |
| --- | --- |
| P0 | 2–3 |
| P1 | 2–4 |
| P2 | 2–3 |
| P3 | 1–2 |
| P4 optional | 4–7 |
| **v1 total (P0–P2)** | **~6–10** |
| **With P3** | **~7–12** |

---

## 12. Open decisions

| ID | Decision | Default |
| --- | --- | --- |
| OD-C1 | Lazy session after `/new` | Lazy clear pin |
| OD-C2 | Apps-Engine timing | After P2 |
| OD-C4 | Retry buffer size | 1 msg, 8k chars |
| OD-C5 | Admin passphrase | Not required |
| Confirm soft match | Exact `yes`/`no` only | Spec default |

---

## 13. References

- NF-SPEC-03 command table, elevation FSM, AC-C*  
- NF-TP-03 TP-C-* / E-C-*  
- `wake_lib.resolve_approval_mode`, `approval_mode_cli_flags`  
- `rc_operator_agent` enqueue/drain path  
- `health.json`, `scripts/rc_health_check.sh`  
- IMP-01 blast radius docs  
