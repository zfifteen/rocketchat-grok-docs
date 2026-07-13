# Implementation plan: Lead–Peer Full Collab

| Field | Value |
| --- | --- |
| **ID** | **NF-IP-10** |
| **Spec** | [NF-SPEC-10](./spec.md) (**source of truth for shalls**) |
| **Test plan** | [test-plan.md](./test-plan.md) (**NF-TP-10** — authoritative case list; per-GOAL gates in §2.3) |
| **Prior** | [NF-SPEC-04](../04-agy-rocketchat-collab/spec.md), [NF-SPEC-09](../09-agy-collab-enablement/spec.md), partial `rc_collab.py` |
| **Runtime home** | `~/.grok/agency/ops/rocketchat/wake/` |
| **Status** | Implementation planning · **Created:** 2026-07-12 |
| **Optimized for** | Rocket.Chat control plane **`!goal`** (see §2) |

---

## 1. Overview

### 1.1 Objective

Implement room mode **`lead_peer_full`** per NF-SPEC-10: purpose-created channel, untagged principal → Grok lead intake, AGY full peer with peer bar, dual REST identity, serial wakes, hop budget, `!collab` ops.

### 1.2 Success (program done)

All of:

- [ ] AC-1…AC-12 in NF-SPEC-10 §13 pass (unit + one live smoke).  
- [ ] Master flag default **off**; non-collab rooms unchanged.  
- [ ] `!collab doctor` green on principal Mac for `#grok-agy-collab`.  
- [ ] NO DUPLICATE POSTS + IMP-01 restricted still hold.

### 1.3 Why fine-grained goals

Wakes have turn limits and context drift. Each **GOAL-XX** is:

- **One objective** (paste into `!goal …`)  
- **≤ ~1–2 focused wakes** of real work when possible  
- **Measurable exit** (test or smoke)  
- **Explicit next** goal id  

Do **not** set a mega-goal “implement all of NF-SPEC-10.” Advance the ladder one GOAL at a time.

---

## 2. How to execute via `!goal`

### 2.1 Control plane (RC)

| Step | Command / action |
| --- | --- |
| Set current unit | `!goal NF-IP-10 GOAL-03: <paste objective from §4>` |
| Check pin | `!goal` or `!goal status` |
| Pause multi-day work | `!goal pause` |
| Resume | `!goal resume` |
| Clear when unit done | `!goal clear` then set next GOAL |
| Steer mid-unit | Untagged note or `@grok` with “stay on GOAL-03; do not start GOAL-04” |

Use **`!` not `/`** (Rocket.Chat steals `/goal`).

### 2.2 Where to run goals

| Room | Use |
| --- | --- |
| **DM principal↔grok** | Default for implementation (agency cwd `~/.grok/agency` or pin `ops/rocketchat`) |
| **`#grok-agy-collab`** | Only for **live smoke goals** (GOAL-20+) after code exists |

Pin cwd for code goals:

```text
!cwd pin /Users/velocityworks/.grok/agency
```

(or IdeaProjects docs-only if the goal is docs-only).

### 2.3 Operator discipline (every GOAL)

1. Read NF-SPEC-10 section cited in the goal.  
2. Implement **only** that goal’s scope (no drive-by refactors).  
3. Run the goal’s **Verify** commands.  
4. Reply with: **DONE GOAL-XX** \| evidence (test output / paths) \| **NEXT: GOAL-YY**.  
5. Principal (or operator) clears/sets next `!goal`.

### 2.4 Goal status file (optional but recommended)

Append progress to:

`~/logs/rocketchat-dm-wake/nf-ip-10-progress.md`

or agency note — one line per GOAL: `GOAL-03 PASS 2026-07-12 tests:…`

Not required for correctness; helps multi-session resume.

---

## 3. Dependency graph

```text
GOAL-00  docs/index pointers (optional)
    │
GOAL-01  pure classifier + types (rc_collab)
    │
GOAL-02  epoch open/amend/done helpers
    │
GOAL-03  peer bar + substantive heuristics
    │
GOAL-04  footer parse/strip
    │
GOAL-05  unit tests GOAL-01…04
    │
GOAL-06  dual RcClient + agy secrets load
    │
GOAL-07  post/update as agy smoke (API only)
    │
GOAL-08  WakeJob + grok path uses collab inject hook
    │
GOAL-09  agy backend wake (CLI + lock + conversation pin)
    │
GOAL-10  operator: allow bot authors + wire classifier
    │
GOAL-11  lead intake (untagged → grok) gated master+armed
    │
GOAL-12  handoff hops + budget stop
    │
GOAL-13  peer bar blocks Done (runtime)
    │
GOAL-14  !collab status/pause/resume/budget/on/off/complete/new
    │
GOAL-15  !collab doctor
    │
GOAL-16  lead + peer inject templates installed/wired
    │
GOAL-17  room profile for #grok-agy-collab
    │
GOAL-18  integration tests (mocked REST/CLI)
    │
GOAL-19  usability / no-dup regression
    │
GOAL-20  live smoke: untagged intake
    │
GOAL-21  live smoke: handoff + peer bar
    │
GOAL-22  ROCKETCHAT.md + progress closeout
```

**Parallelism:** GOAL-00 docs anytime. GOAL-16 inject text can draft in parallel after GOAL-01. Do **not** parallelize GOAL-10 with GOAL-11 on live operator without tests.

---

## 4. Goal ladder (copy-paste objectives)

Each block:

- **ID**  
- **`!goal` objective** (paste as-is or with minor path edits)  
- **Scope / out of scope**  
- **Files**  
- **Verify**  
- **Next**

---

### GOAL-00 — Index only (optional)

**`!goal` objective:**

```text
NF-IP-10 GOAL-00: Ensure NF-SPEC-10 and NF-IP-10 are linked from new-features index and feature 10 README (docs only; no runtime).
```

| | |
| --- | --- |
| **Scope** | Docs links only |
| **Out** | Any Python |
| **Files** | `rocketchat-grok-docs/new-features/**` |
| **Verify** | Links resolve; README lists NF-IP-10 |
| **Next** | GOAL-01 |

---

### GOAL-01 — Classifier pure functions

**`!goal` objective:**

```text
NF-IP-10 GOAL-01: In rc_collab.py implement lead_peer_full classifier pure functions per NF-SPEC-10 §7: CollabAction types; untagged principal → LeadIntake; principal untagged + active epoch → LeadSteer; grok@agy → Handoff; agy@grok → Handoff; self-mention Ignore; both mentions Reject. No network. Unit-testable without RC.
```

| | |
| --- | --- |
| **Scope** | Pure classify API + helpers |
| **Out** | Operator wiring, REST, CLI |
| **Files** | `wake/rc_collab.py`, tests under `ops/rocketchat/tests/` |
| **Verify** | `python3 -m pytest … -k collab_classif` or new test module exit 0 |
| **Next** | GOAL-02 |

---

### GOAL-02 — Epoch state helpers

**`!goal` objective:**

```text
NF-IP-10 GOAL-02: Implement epoch helpers in rc_collab.py / state accessors: open_epoch, amend_goal, pause/resume, can_close stub, hop_increment, budget_exhausted. Persist shape per NF-SPEC-10 §6. Pure + state dict only; no RC I/O.
```

| | |
| --- | --- |
| **Scope** | Epoch CRUD on `state` dict |
| **Out** | Peer bar logic (GOAL-03), operator |
| **Files** | `rc_collab.py`, maybe `wake_lib` state helpers |
| **Verify** | Unit tests: open → amend same id → hop → pause |
| **Next** | GOAL-03 |

---

### GOAL-03 — Peer bar + substantive heuristic

**`!goal` objective:**

```text
NF-IP-10 GOAL-03: Implement peer_bar can_close and is_substantive_peer_body per NF-SPEC-10 §8. LGTM-only must not count. Trivial bypass via profile regex. Unit tests only; no operator wiring yet.
```

| | |
| --- | --- |
| **Scope** | `can_close`, substantive detection |
| **Out** | Runtime Done enforcement (GOAL-13) |
| **Files** | `rc_collab.py`, tests |
| **Verify** | Tests: LGTM false; long structured true; trivial bypass |
| **Next** | GOAL-04 |

---

### GOAL-04 — Footer parse/strip

**`!goal` objective:**

```text
NF-IP-10 GOAL-04: Implement parse_rc_collab_footer and strip_footer per NF-SPEC-10 §10.4. Invalid footer must not raise. Handoff in footer alone must not imply enqueue (document in docstring). Unit tests.
```

| | |
| --- | --- |
| **Scope** | Parse/strip only |
| **Out** | Inject text, operator |
| **Files** | `rc_collab.py`, tests |
| **Verify** | Round-trip parse; strip leaves clean body |
| **Next** | GOAL-05 |

---

### GOAL-05 — Unit suite gate for pure core

**`!goal` objective:**

```text
NF-IP-10 GOAL-05: Consolidate unit tests for classifier, epoch, peer bar, footer into ops/rocketchat/tests (extend test_nf04 or new test_nf10_lead_peer.py). All pure tests green. No live RC.
```

| | |
| --- | --- |
| **Scope** | Test packaging + green CI-local |
| **Out** | Implementation features |
| **Verify** | `pytest …/tests/test_nf10*.py` or named module exit 0 |
| **Next** | GOAL-06 |

---

### GOAL-06 — Dual RcClient + secrets

**`!goal` objective:**

```text
NF-IP-10 GOAL-06: Add dual-identity REST client support (grok + agy) loading ROCKETCHAT_AGY_* from secrets path without printing secrets. Cache tokens like existing REST auth cache pattern. No wakes yet—login+auth cache only. Unit or dry-run with mocks preferred.
```

| | |
| --- | --- |
| **Scope** | Auth clients for two users |
| **Out** | Message post in rooms (GOAL-07) |
| **Files** | `rc_operator_agent.py` and/or small `rc_client.py` |
| **Secrets** | Extend `rocketchat.env` **example only** in docs/config.example — do not commit real secrets |
| **Verify** | Mock login both identities; no secret in logs |
| **Next** | GOAL-07 |

---

### GOAL-07 — Post/update as agy (API smoke)

**`!goal` objective:**

```text
NF-IP-10 GOAL-07: Using dual client, post a short probe message as agy to a private test room or DM-safe target and chat.update it (Thinking→text). Principal confirms bubble shows agy. No Grok CLI. Tear down or leave labeled PROBE.
```

| | |
| --- | --- |
| **Scope** | REST post/update as agy |
| **Out** | Collab classifier live |
| **Verify** | Human sees `agy` author on probe bubble |
| **Next** | GOAL-08 |
| **Risk** | Needs real `agy` RC user — create if missing before this goal |

---

### GOAL-08 — Grok wake collab inject hook

**`!goal` objective:**

```text
NF-IP-10 GOAL-08: When room mode lead_peer_full and target=grok, prepend lead collab inject + epoch block to wake prompt (dynamic L3). No behavior change for non-collab rooms. Restricted mode unchanged. Unit or fixture test that inject appears in composed prompt.
```

| | |
| --- | --- |
| **Scope** | Inject assembly for grok collab wakes |
| **Out** | AGY backend |
| **Files** | `rc_operator_agent.py`, inject md path |
| **Verify** | Non-collab prompt unchanged; collab prompt contains “LEAD” / epoch fields |
| **Next** | GOAL-09 |

---

### GOAL-09 — AGY backend wake path

**`!goal` objective:**

```text
NF-IP-10 GOAL-09: Implement target=agy wake: Thinking as agy → global agy CLI lock → local agy/helper spawn with conversation pin → reply file → chat.update as agy → persist agy_conversation_id. Timeouts via RC_AGY_WAKE_TIMEOUT_S. Failure → FINAL_ERR on same bubble. No lead intake routing yet (invoke via test harness or temporary debug path).
```

| | |
| --- | --- |
| **Scope** | Full agy backend mirror |
| **Out** | Production classifier enqueue |
| **Verify** | Harness or one forced wake produces agy bubble with non-empty body |
| **Next** | GOAL-10 |

---

### GOAL-10 — Wire classifier into operator

**`!goal` objective:**

```text
NF-IP-10 GOAL-10: Wire lead_peer_full classifier into message handling: master flag + room armed required; allow authors principal|grok|agy in collab rooms; enqueue WakeJob by target; mark mids processed; serial room lock. Default master off → zero behavior change elsewhere.
```

| | |
| --- | --- |
| **Scope** | Operator integration |
| **Out** | Peer bar Done enforcement (GOAL-13) polish |
| **Verify** | Unit/integration: disarmed → ignore; master off → ignore |
| **Next** | GOAL-11 |

---

### GOAL-11 — Lead intake live path

**`!goal` objective:**

```text
NF-IP-10 GOAL-11: Principal untagged message in armed lead_peer_full room opens epoch and enqueues grok lead intake only. AGY must not wake. Open epoch card optional short post as grok. Unit test + dry log proof.
```

| | |
| --- | --- |
| **Scope** | LeadIntake path |
| **Out** | Full peer bar productization |
| **Verify** | Classifier + enqueue target=grok; no agy |
| **Next** | GOAL-12 |

---

### GOAL-12 — Handoff hops + budget stop

**`!goal` objective:**

```text
NF-IP-10 GOAL-12: On grok message with @agy enqueue agy handoff and hop++. On agy @grok enqueue grok. At budget exhaust post stop card, pause epoch, no enqueue. Self-wake ignored. Unit tests for hop/budget.
```

| | |
| --- | --- |
| **Scope** | Handoff + budget |
| **Out** | Peer bar Done |
| **Verify** | Budget 1 → second handoff stopped |
| **Next** | GOAL-13 |

---

### GOAL-13 — Runtime peer bar on Done

**`!goal` objective:**

```text
NF-IP-10 GOAL-13: When lead footer/heuristic claims done, call can_close; if fail, refuse epoch done and emit short protocol notice; if pass, mark epoch done. Wire substantive peer turn increments on agy finalize. Unit tests for false Done.
```

| | |
| --- | --- |
| **Scope** | Done gate |
| **Out** | Control plane commands |
| **Verify** | Solo done rejected; after substantive+adversarial flags pass |
| **Next** | GOAL-14 |

---

### GOAL-14 — `!collab` control commands

**`!goal` objective:**

```text
NF-IP-10 GOAL-14: Implement principal-only !collab status|pause|resume|budget|on|off|complete|new in rc_commands per NF-SPEC-10 §11. No research wake. Prefer ! help text. Unit tests for parse/dispatch.
```

| | |
| --- | --- |
| **Scope** | Control plane |
| **Out** | doctor (GOAL-15) |
| **Verify** | `!collab status` shape; pause blocks handoff in unit FSM |
| **Next** | GOAL-15 |

---

### GOAL-15 — `!collab doctor`

**`!goal` objective:**

```text
NF-IP-10 GOAL-15: Implement !collab doctor: master flag, room armed, both users in room, agy binary path, cwd exists, dual auth probe—no secrets printed. One bubble report.
```

| | |
| --- | --- |
| **Scope** | Doctor command |
| **Out** | Live full scenario |
| **Verify** | Doctor returns structured ok/fail lines without tokens |
| **Next** | GOAL-16 |

---

### GOAL-16 — Lead + peer inject templates

**`!goal` objective:**

```text
NF-IP-10 GOAL-16: Install/wire L2 lead and peer inject templates (update 04 profiles or wake/*.md) with full-peer language per NF-SPEC-10 §10. Grok collab wakes load lead template; agy loads peer. No nested agy CLI instruction.
```

| | |
| --- | --- |
| **Scope** | Prompt/profile files + load paths |
| **Out** | Room map |
| **Verify** | File exists; load function returns non-empty; contains “full peer” / “LEAD” |
| **Next** | GOAL-17 |

---

### GOAL-17 — Room profile `#grok-agy-collab`

**`!goal` objective:**

```text
NF-IP-10 GOAL-17: Add durable room profile mode=lead_peer_full for the collab channel (channel_projects.json and/or state), cwd pin, hop_budget, peer_bar defaults per NF-SPEC-10 §5. Document room id mapping. Master remains off until live smoke.
```

| | |
| --- | --- |
| **Scope** | Config/profile only |
| **Out** | Enabling master in production without tests |
| **Verify** | Profile loads for room id; doctor sees mode |
| **Next** | GOAL-18 |

---

### GOAL-18 — Integration tests (mocked)

**`!goal` objective:**

```text
NF-IP-10 GOAL-18: Add integration tests with mocked REST and mocked CLI for: lead intake enqueue, handoff to agy, budget stop, peer bar block done. No live network required.
```

| | |
| --- | --- |
| **Scope** | Mocked integration |
| **Out** | Live smoke |
| **Verify** | pytest module exit 0 |
| **Next** | GOAL-19 |

---

### GOAL-19 — Regression gate

**`!goal` objective:**

```text
NF-IP-10 GOAL-19: Run usability contracts + existing collab/unit suites; fix regressions only. Confirm non-collab DM path still principal→grok only. Restricted default unchanged.
```

| | |
| --- | --- |
| **Scope** | Regression |
| **Verify** | `test_usability_contracts` + nf10 tests green |
| **Next** | GOAL-20 |

---

### GOAL-20 — Live smoke: untagged intake

**`!goal` objective:**

```text
NF-IP-10 GOAL-20: LIVE (principal): Enable master for test; arm #grok-agy-collab; post untagged "Build me a simple TODO app" (or PROBE goal). Confirm Grok Thinking intake only; epoch open in status. Then disable or leave paused. Document results in nf-ip-10-progress.
```

| | |
| --- | --- |
| **Scope** | Live AC-1, AC-2 |
| **Verify** | Human: one grok Thinking path; no agy first |
| **Next** | GOAL-21 |

---

### GOAL-21 — Live smoke: handoff + peer bar

**`!goal` objective:**

```text
NF-IP-10 GOAL-21: LIVE: From lead, force or allow @agy package handoff; confirm agy bubble; return @grok; attempt premature Done without peer bar fails; complete path or !collab complete. Capture AC-3…7 evidence in progress note.
```

| | |
| --- | --- |
| **Scope** | Live AC-3…7 subset |
| **Verify** | Dual identities visible; peer bar notice once |
| **Next** | GOAL-22 |

---

### GOAL-22 — Ops closeout

**`!goal` objective:**

```text
NF-IP-10 GOAL-22: Update ~/.grok/agency/ops/ROCKETCHAT.md collab section: lead_peer_full, !collab, !goal ladder pointer to NF-IP-10, doctor, master flag default off. Mark GOAL ladder complete in progress note. No new features.
```

| | |
| --- | --- |
| **Scope** | Docs/ops only |
| **Verify** | ROCKETCHAT.md contains lead_peer_full + link to NF-IP-10 |
| **Next** | *(program complete)* |

---

## 5. One-screen “current goal” cheat sheet

When resuming after sleep, principal sets:

```text
!cwd pin /Users/velocityworks/.grok/agency
!goal NF-IP-10 GOAL-XX: <paste objective from ladder>
```

Operator (Grok) works **only** GOAL-XX until DONE line.

**Suggested first code goal after secrets/user exist:**

```text
!goal NF-IP-10 GOAL-01: In rc_collab.py implement lead_peer_full classifier pure functions per NF-SPEC-10 §7: CollabAction types; untagged principal → LeadIntake; principal untagged + active epoch → LeadSteer; grok@agy → Handoff; agy@grok → Handoff; self-mention Ignore; both mentions Reject. No network. Unit-testable without RC.
```

---

## 6. Flags and defaults (implement as you go)

| Flag / key | Default | When |
| --- | --- | --- |
| `RC_AGY_COLLAB` / master | `0` | GOAL-10+ |
| `RC_AGY_USER` | `agy` | GOAL-06 |
| `RC_AGY_WAKE_TIMEOUT_S` | `1200` | GOAL-09 |
| `RC_AGY_HOP_BUDGET_EPOCH` | `30` | GOAL-12 / profile |
| Room `mode` | `lead_peer_full` | GOAL-17 |
| `peer_bar.min_substantive_peer_turns` | `1` | GOAL-03/13 |
| `require_adversarial_before_done` | `true` | GOAL-03/13 |

---

## 7. Rollback

| Situation | Action |
| --- | --- |
| Any prod incident | `RC_AGY_COLLAB=0` + kickstart operator |
| Room noise | `!collab off` or `!collab pause` |
| Bad epoch | `!collab new` or `!collab complete` |
| Code rollback | git revert wake modules; keep secrets |

---

## 8. Risks (execution)

| Risk | Mitigation in ladder |
| --- | --- |
| Mega-PR | One GOAL per pin |
| Live smoke too early | GOAL-20 only after 18–19 |
| Missing `agy` user | Blocker before GOAL-07 — create RC user first |
| Turn limit mid-feature | Prefer pure tests first (01–05); raise max turns already 100 |
| Nested scope creep | Each goal **Out of scope** line |

---

## 9. Principal pre-flight (before GOAL-07)

- [ ] RC user `agy` exists, password/token in secrets (not git)  
- [ ] `agy` joined to `#grok-agy-collab`  
- [ ] Local `agy` CLI works interactively once  
- [ ] Operator launchd healthy  
- [ ] Know `!goal` / `!collab` use `!` prefix  

---

## 10. Mapping to NF-SPEC-10 acceptance

| AC | Primary GOAL |
| --- | --- |
| AC-1, AC-2 | GOAL-11, GOAL-20 |
| AC-3, AC-4 | GOAL-12, GOAL-21 |
| AC-5, AC-6 | GOAL-13, GOAL-21 |
| AC-7, AC-8 | GOAL-12, GOAL-14 |
| AC-9 | GOAL-02 + restart check in GOAL-20 notes |
| AC-10 | GOAL-16 |
| AC-11 | GOAL-19 |
| AC-12 | GOAL-10, GOAL-19 |

---

## 11. Document control

| Version | Date | Notes |
| --- | --- | --- |
| 1.0 | 2026-07-12 | Fine-grained ladder GOAL-00…22 optimized for `!goal` |

**Normative requirements remain in [NF-SPEC-10](./spec.md).** This plan only sequences work.
