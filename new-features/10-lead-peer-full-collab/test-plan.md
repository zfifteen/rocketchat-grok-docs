# Test plan: Lead–Peer Full Collab (Grok lead · AGY full peer)

| Field | Value |
| --- | --- |
| **ID** | **NF-TP-10** |
| **Feature** | Purpose-created collab channel: untagged lead intake; AGY full peer; peer bar; dual identity |
| **Spec** | [spec.md](./spec.md) (**NF-SPEC-10** — source of truth for shalls) |
| **Implementation plan** | [implementation-plan.md](./implementation-plan.md) (**NF-IP-10** — GOAL ladder) |
| **Parent tests** | [NF-TP-04](../04-agy-rocketchat-collab/test-plan.md), [NF-TP-09](../09-agy-collab-enablement/test-plan.md) |
| **Related** | NF-SPEC-02/03, IMP-01, `NO_DUPLICATE_POSTS.md`, `ops/rocketchat/tests/` |
| **Type** | L0 unit · L1 contract · L2 backend mock · L3 state durability · L4 lab REST · L5 live opt-in · L6 regression |
| **Status** | Test-planning documentation only · **Created:** 2026-07-12 |
| **Flags under test** | `RC_AGY_COLLAB` (master), room `mode=lead_peer_full`, `armed`, hop budget, peer_bar fields, `RC_AGY_*` secrets/timeouts, `RC_LIVE_COLLAB=1` (live only) |

---

## 1. Scope and objectives

### 1.1 In scope

- Master flag + room armed gates for `lead_peer_full`  
- **Lead intake:** untagged principal → Grok only (never AGY)  
- **Lead steer:** untagged principal while epoch active (same epoch id)  
- Handoff routing: `grok`→`@agy`, `agy`→`@grok`  
- Self-wake filter; dual-mention reject; allowlist authors  
- Epoch open/amend/pause/resume/done lifecycle  
- Hop increment on agent→agent handoff only; budget exhaust stop card  
- Peer bar: substantive peer turns; LGTM non-count; adversarial flag; false-Done block  
- Footer parse/strip; footer alone does not enqueue  
- Dual REST identity: Thinking / `chat.update` as correct user  
- AGY backend: local CLI only, global lock, conversation UUID pin, FINAL_ERR parity  
- Lead/peer inject content contracts (full peer language; no nested agy primary)  
- `!collab` control plane (not `/`) principal-only  
- `!collab doctor` without secret leakage  
- Serial per-room wake lock  
- Non-collab / master-off / disarmed regression  
- NO DUPLICATE POSTS per identity  
- Mapping to NF-IP-10 GOAL verify blocks  

### 1.2 Out of scope

- Executing live multi-day unattended collab as a docs-package gate  
- Creating RC users or installing secrets from this package  
- Voice/Call dual-agent  
- Symmetric dual intake mode (explicitly non-goal of NF-SPEC-10)  
- MCP `agy_*` positive tests (only forbid assertions)  
- Public multi-tenant rooms  

### 1.3 Pass/fail language

| Term | Meaning |
| --- | --- |
| **Pass** | All Expected rows met; no secrets in artifacts |
| **Fail** | Any Expected violated or unsafe leakage |
| **Blocked** | Missing preconditions (no `agy` user, master cannot enable) — record, do not false-pass |
| **Skip** | Live layer without `RC_LIVE_COLLAB=1` |

---

## 2. Traceability matrices

### 2.1 NF-SPEC-10 acceptance → cases

| AC | Cases (primary) |
| --- | --- |
| **AC-1** Untagged → Grok intake + epoch | TP-10-C-01, TP-10-L-01 |
| **AC-2** Untagged does not enqueue AGY | TP-10-C-01, TP-10-U-02, TP-10-L-01 |
| **AC-3** Grok `@agy` → AGY Thinking as agy | TP-10-C-10, TP-10-B-20, TP-10-L-02 |
| **AC-4** AGY `@grok` + hop++ | TP-10-C-11, TP-10-U-20, TP-10-L-02 |
| **AC-5** Peer bar blocks Done | TP-10-U-30, TP-10-C-30, TP-10-L-03 |
| **AC-6** LGTM not substantive | TP-10-U-31, TP-10-U-32 |
| **AC-7** Budget exhaust stop | TP-10-U-21, TP-10-C-21, TP-10-L-04 |
| **AC-8** Pause / resume | TP-10-U-40, TP-10-K-02, TP-10-L-05 |
| **AC-9** Restart preserves epoch/sessions | TP-10-S-01, TP-10-S-02 |
| **AC-10** Floor mentions suffice (no nested primary) | TP-10-I-01, TP-10-B-21 |
| **AC-11** NO DUPLICATE POSTS | TP-10-B-30, TP-10-R-02 |
| **AC-12** Disarmed / master off | TP-10-C-00, TP-10-C-00b, TP-10-R-01 |

### 2.2 Spec sections → case families

| Spec § | Case prefix |
| --- | --- |
| §5 Profile / arming | TP-10-C-00*, TP-10-K-01 |
| §6 Epoch | TP-10-U-10…, TP-10-S-01 |
| §7 Classifier | TP-10-U-01…, TP-10-C-01… |
| §8 Peer bar / phases | TP-10-U-30…, TP-10-C-30 |
| §9 Wake pipeline | TP-10-B-* |
| §10 Inject / footer | TP-10-U-50…, TP-10-I-* |
| §11 Control plane | TP-10-K-* |
| §14 Security | TP-10-X-* |

### 2.3 NF-IP-10 GOAL → test gate

| GOAL | Minimum tests before marking GOAL done |
| --- | --- |
| GOAL-01 | TP-10-U-01…U-09 |
| GOAL-02 | TP-10-U-10…U-15 |
| GOAL-03 | TP-10-U-30…U-33 |
| GOAL-04 | TP-10-U-50…U-53 |
| GOAL-05 | All L0 pure suites green (batch) |
| GOAL-06–07 | TP-10-B-01, TP-10-X-01; lab TP-10-LAB-01 |
| GOAL-08–09 | TP-10-B-10…B-22 |
| GOAL-10–12 | TP-10-C-00…C-21 |
| GOAL-13 | TP-10-C-30…C-32 |
| GOAL-14–15 | TP-10-K-01…K-10 |
| GOAL-16 | TP-10-I-01…I-04 |
| GOAL-17 | TP-10-C-profile |
| GOAL-18 | Full L1+L2 suite |
| GOAL-19 | L6 regression |
| GOAL-20–21 | L5 live TP-10-L-* |
| GOAL-22 | Docs checklist only |

---

## 3. Test strategy and layers

| Layer | ID | Proves | Requires live RC? |
| --- | --- | --- | --- |
| **L0 Unit** | TP-10-U-* | Pure classifier, epoch, peer bar, footer, hop FSM | No |
| **L1 Contract** | TP-10-C-* | Message → WakeJob target/kind; gates; mid mark | No (mocks) |
| **L2 Backend mock** | TP-10-B-* | Dual auth post/update; CLI argv; lock; inject assembly | No |
| **L3 State** | TP-10-S-* | Reload state.json; session pins; hop counters | No |
| **L4 Lab REST** | TP-10-LAB-* | Real RC 8.6: post as agy; mentions[] physics | Yes (API) |
| **L5 Live** | TP-10-L-* | Full operator path; human phone/history | Yes + operator |
| **L6 Regression** | TP-10-R-* | DM principal-only; usability contracts | No / optional live DM |

### 3.1 Recommended execution order

```text
L0 → L1 → L2 → L3 → L6 (unit) → L4 lab → L5 live (opt-in)
```

Never run L5 before L0–L3 green and master default-off proven.

### 3.2 Evidence artifacts

| Artifact | Use |
| --- | --- |
| pytest stdout / JUnit | L0–L3, L6 |
| Operator log lines `collab=` | L1/L5 |
| `wake-run-*.log`, reply files | L2/L5 |
| `state.json` snapshot before/after | L3/L5 |
| RC history export / screenshots | L4/L5 |
| `~/logs/rocketchat-dm-wake/nf-ip-10-progress.md` | GOAL ladder |

---

## 4. Preconditions

### 4.1 Always (docs + unit)

- NF-SPEC-10 + NF-IP-10 present  
- `ops/rocketchat/tests/` runnable with project venv  
- Fixtures: temp state, profile `mode=lead_peer_full`, fake clock optional  

### 4.2 Lab / live (implement-time)

| Need | Notes |
| --- | --- |
| RC users | `principal`, `grok`, **`agy`** |
| Private channel | e.g. `#grok-agy-collab`, all three members |
| Secrets | `ROCKETCHAT_*` + `ROCKETCHAT_AGY_*` **not** in git |
| Master | `RC_AGY_COLLAB=0` default; set `1` only for L4/L5 |
| Local `agy` CLI | Authenticated; skill helper path |
| Operator | launchd healthy; `!` control plane  
| Live gate | `RC_LIVE_COLLAB=1` or explicit principal approval |

### 4.3 Environment matrix

| Env | L0–L3 | L4 | L5 |
| --- | --- | --- | --- |
| Master | 0 or mocked | 1 | 1 |
| Room armed | fixture | yes | yes |
| Network | none | localhost RC | localhost RC + CLIs |

---

## 5. Fixtures and harness conventions

### 5.1 Standard profile fixture

```json
{
  "mode": "lead_peer_full",
  "lead": "grok",
  "peer": "agy",
  "principal_untagged": "lead_intake",
  "agent_untagged": "ignore",
  "peer_bar": {
    "min_substantive_peer_turns": 1,
    "require_adversarial_before_done": true,
    "trivial_bypass_patterns": ["^(?i)(fix|typo|nit)\\b"]
  },
  "hop_budget": 30,
  "cwd": "/tmp/nf10-scratch",
  "armed": true
}
```

### 5.2 Message fixture shape

```python
Msg(author, text, mentions=None, mid="m1")
# mentions: list of usernames RC would put in mentions[]
```

### 5.3 Mock backends

| Mock | Assert |
| --- | --- |
| `post_message(identity, …)` | identity ∈ {grok, agy}; capture msg_id |
| `update_message(identity, msg_id, body)` | same identity as Thinking |
| `spawn_grok(argv)` | `--cwd`, inject contains LEAD when expected |
| `spawn_agy(…)` | lock held; conversation id; no parallel second spawn |

### 5.4 Naming

- **TP-10-U-** unit  
- **TP-10-C-** contract  
- **TP-10-B-** backend  
- **TP-10-S-** state  
- **TP-10-I-** inject  
- **TP-10-K-** control plane  
- **TP-10-X-** security  
- **TP-10-LAB-** lab REST  
- **TP-10-L-** live  
- **TP-10-R-** regression  

---

## 6. L0 — Unit cases (pure)

### TP-10-U-01 — Untagged principal → LeadIntake

| | |
| --- | --- |
| **Spec** | FR-C20, AC-1 |
| **Steps** | Profile armed; no epoch; `Msg(principal, "Build me a simple TODO app")` |
| **Expected** | Action `LeadIntake`; target grok; goal text exact |
| **Pass** | No peer target |

### TP-10-U-02 — Untagged never targets agy

| | |
| --- | --- |
| **Spec** | FR-C21, AC-2 |
| **Steps** | Same as U-01 |
| **Expected** | `target != agy` always |

### TP-10-U-03 — Active epoch + untagged → LeadSteer

| | |
| --- | --- |
| **Spec** | FR-E2, FR-C table #5 |
| **Steps** | Open epoch; principal posts "add dark mode" |
| **Expected** | `LeadSteer`; same `epoch.id`; not new epoch |

### TP-10-U-04 — Principal @grok only

| | |
| --- | --- |
| **Steps** | `@grok focus on tests` with mentions=[grok] |
| **Expected** | LeadSteer or LeadIntake (no epoch); target grok |

### TP-10-U-05 — Principal @agy only (DirectPeer default)

| | |
| --- | --- |
| **Spec** | OD-10-1 default allow |
| **Steps** | `@agy critique the plan` mentions=[agy] |
| **Expected** | `DirectPeer`; target agy (if OD allow); if OD reject, `Reject` with help — **document chosen OD in test name** |

### TP-10-U-06 — Principal both mentions → Reject

| | |
| --- | --- |
| **Spec** | FR-C table #8 |
| **Steps** | `@grok @agy both` |
| **Expected** | `Reject`; no dual enqueue |

### TP-10-U-07 — Grok @agy → Handoff peer

| | |
| --- | --- |
| **Spec** | FR-C table #9, AC-3 |
| **Steps** | author=grok, text with `@agy …`, mentions=[agy] |
| **Expected** | `Handoff(to=agy, from=grok)` |

### TP-10-U-08 — Agy @grok → Handoff lead

| | |
| --- | --- |
| **Spec** | FR-C table #10, AC-4 |
| **Steps** | author=agy, `@grok …` |
| **Expected** | `Handoff(to=grok, from=agy)` |

### TP-10-U-09 — Self-mention Ignore

| | |
| --- | --- |
| **Spec** | FR-C table #12 |
| **Steps** | author=agy, only `@agy`; author=grok only `@grok` |
| **Expected** | `Ignore` both |

### TP-10-U-09b — Agent untagged Ignore

| | |
| --- | --- |
| **Spec** | FR-C table #11 |
| **Steps** | author=grok or agy, no mentions, free text |
| **Expected** | `Ignore` |

### TP-10-U-09c — Non-allowlist Ignore

| | |
| --- | --- |
| **Steps** | author=randomuser |
| **Expected** | `Ignore` |

### TP-10-U-09d — Mentions[] preferred over text

| | |
| --- | --- |
| **Spec** | FR-C30 |
| **Steps** | text without @ but mentions=[agy]; author=grok |
| **Expected** | Handoff to agy |

### TP-10-U-09e — Text fallback case-insensitive

| | |
| --- | --- |
| **Spec** | FR-C31 |
| **Steps** | `@AGY please` no structured mentions |
| **Expected** | Handoff to peer |

---

### TP-10-U-10 — open_epoch fields

| | |
| --- | --- |
| **Spec** | FR-E1, §6.2 |
| **Steps** | open_epoch(goal, mid) |
| **Expected** | status=active; phase=frame_split; hop=0; peer_substantive_turns=0; adversarial_done=false |

### TP-10-U-11 — amend keeps id

| | |
| --- | --- |
| **Spec** | FR-E2 |
| **Steps** | open; amend; open again attempt |
| **Expected** | same id; amendments recorded or goal updated per impl; no second concurrent active |

### TP-10-U-12 — pause / resume

| | |
| --- | --- |
| **Spec** | FR-E3, FR-E4 |
| **Steps** | pause; classify handoff; resume; classify handoff |
| **Expected** | paused → no handoff enqueue; resume → handoff allowed |

### TP-10-U-13 — hop_increment only agent handoff

| | |
| --- | --- |
| **Spec** | FR-W20 |
| **Steps** | lead intake; lead steer; handoff; handoff |
| **Expected** | hop 0 after intake/steer; hop 1 then 2 after handoffs |

### TP-10-U-14 — budget_exhausted

| | |
| --- | --- |
| **Spec** | FR-W21, AC-7 |
| **Steps** | budget=1; one handoff ok; second handoff |
| **Expected** | second blocked; exhausted true |

### TP-10-U-15 — done status only via can_close path (unit)

| | |
| --- | --- |
| **Steps** | force mark_done without can_close in helper API |
| **Expected** | helper requires can_close or separate force_complete flag for principal override |

---

### TP-10-U-20 — hop accounting independence from principal

| | |
| --- | --- |
| **Steps** | 5 lead steers; hop remains 0 |
| **Expected** | hop==0 |

### TP-10-U-21 — budget stop sets paused

| | |
| --- | --- |
| **Steps** | exhaust budget via handoffs |
| **Expected** | epoch.status paused or equivalent; further handoff Ignore/stop |

---

### TP-10-U-30 — can_close false without substantive peer

| | |
| --- | --- |
| **Spec** | FR-B10, AC-5 |
| **Steps** | non-trivial epoch; peer_substantive_turns=0; adversarial_done=false |
| **Expected** | can_close False |

### TP-10-U-31 — LGTM body not substantive

| | |
| --- | --- |
| **Spec** | FR-B20, AC-6 |
| **Steps** | is_substantive("LGTM") / "looks good" / "ship it" |
| **Expected** | False |

### TP-10-U-32 — long structured peer body substantive

| | |
| --- | --- |
| **Steps** | multi-paragraph decision record body (or PEER_SUBSTANTIVE:1 + long body) |
| **Expected** | True |

### TP-10-U-33 — adversarial required

| | |
| --- | --- |
| **Spec** | FR-B11 |
| **Steps** | substantive≥1 but adversarial_done=false; require_adversarial true |
| **Expected** | can_close False; after adversarial_done True → can_close True |

### TP-10-U-34 — trivial bypass

| | |
| --- | --- |
| **Spec** | FR-B12 |
| **Steps** | goal "fix typo in README"; trivial true or regex match |
| **Expected** | can_close True without peer turns |

### TP-10-U-35 — principal force complete

| | |
| --- | --- |
| **Spec** | FR-B14 |
| **Steps** | force_complete override |
| **Expected** | done allowed even if bar false; audit flag set |

---

### TP-10-U-50 — parse footer happy path

| | |
| --- | --- |
| **Spec** | §10.4 |
| **Steps** | body with `---rc-collab---` block |
| **Expected** | fields epoch, role, status, handoff, ask_type parsed |

### TP-10-U-51 — strip footer

| | |
| --- | --- |
| **Spec** | OD-10-3 |
| **Steps** | strip_footer(full) |
| **Expected** | user-visible without fence; content preserved |

### TP-10-U-52 — invalid footer no throw

| | |
| --- | --- |
| **Spec** | FR-F3 |
| **Steps** | truncated/malformed fence |
| **Expected** | empty/partial parse; no exception |

### TP-10-U-53 — footer handoff without @ does not imply enqueue

| | |
| --- | --- |
| **Spec** | FR-F1 |
| **Steps** | classify message with footer handoff=agy but no mention and no @ in text |
| **Expected** | not Handoff (Ignore or lead-only rules); document |

---

## 7. L1 — Contract cases (classifier + enqueue)

### TP-10-C-00 — Master off

| | |
| --- | --- |
| **Spec** | FR-P5, AC-12 |
| **Steps** | master=0; armed profile; principal untagged + simulated grok@agy |
| **Expected** | no collab WakeJob; no agy identity post |

### TP-10-C-00b — Master on, room disarmed

| | |
| --- | --- |
| **Spec** | FR-P6, FR-P7 |
| **Steps** | master=1; armed=false; untagged + @agy |
| **Expected** | no lead_peer_full intake; no agy wake |

### TP-10-C-01 — Lead intake enqueue

| | |
| --- | --- |
| **Spec** | AC-1, AC-2 |
| **Steps** | master=1; armed; untagged goal |
| **Expected** | WakeJob(target=grok, kind=intake); epoch opened; **zero** agy jobs |

### TP-10-C-02 — Lead steer same epoch

| | |
| --- | --- |
| **Steps** | after C-01; second untagged |
| **Expected** | kind=steer; same epoch_id |

### TP-10-C-10 — Handoff to agy enqueue

| | |
| --- | --- |
| **Steps** | after intake; process grok message with @agy |
| **Expected** | WakeJob(target=agy, kind=handoff); hop==1 |

### TP-10-C-11 — Handoff to grok enqueue

| | |
| --- | --- |
| **Steps** | process agy message with @grok |
| **Expected** | WakeJob(target=grok, kind=handoff); hop==2 |

### TP-10-C-12 — Mid processed once

| | |
| --- | --- |
| **Steps** | deliver same mid twice |
| **Expected** | single WakeJob |

### TP-10-C-13 — Serial lock

| | |
| --- | --- |
| **Spec** | AR-4 |
| **Steps** | hold lock; second message arrives |
| **Expected** | queued or deferred; not parallel dual CLI |

### TP-10-C-21 — Budget exhaust contract

| | |
| --- | --- |
| **Spec** | AC-7 |
| **Steps** | budget=1; complete one handoff; second handoff message |
| **Expected** | stop card posted (mock); no second peer wake; paused |

### TP-10-C-30 — False Done contract

| | |
| --- | --- |
| **Spec** | AC-5, FR-B13 |
| **Steps** | lead finalize with status=done footer; peer_substantive_turns=0 |
| **Expected** | epoch not done; protocol notice; bar fail path |

### TP-10-C-31 — Done success after bar

| | |
| --- | --- |
| **Steps** | substantive=1; adversarial_done=true; lead done footer |
| **Expected** | epoch status=done |

### TP-10-C-32 — Substantive increment on agy finalize

| | |
| --- | --- |
| **Steps** | mock agy reply long structured body |
| **Expected** | peer_substantive_turns += 1 |

### TP-10-C-profile — Profile load for room

| | |
| --- | --- |
| **Spec** | FR-P1…P4 |
| **Steps** | load room map for fixture rid |
| **Expected** | mode=lead_peer_full; lead=grok; peer=agy |

---

## 8. L2 — Backend mock cases

### TP-10-B-01 — Dual client auth cache

| | |
| --- | --- |
| **Spec** | §4.3 |
| **Steps** | ensure_auth grok; ensure_auth agy |
| **Expected** | two caches; no cross-token use |

### TP-10-B-10 — Grok wake posts as grok

| | |
| --- | --- |
| **Steps** | run WakeJob target=grok |
| **Expected** | postMessage identity=grok Thinking; update identity=grok |

### TP-10-B-11 — Grok inject contains lead + epoch

| | |
| --- | --- |
| **Spec** | §10.2 |
| **Steps** | capture prompt file |
| **Expected** | LEAD / full peer / epoch id / peer_bar fields present |

### TP-10-B-12 — Grok inject forbids nested agy primary

| | |
| --- | --- |
| **Spec** | FR-W3, AC-10 |
| **Steps** | inspect inject |
| **Expected** | explicit forbid nest; instruct @agy handoff |

### TP-10-B-20 — Agy wake posts as agy

| | |
| --- | --- |
| **Spec** | FR-W12, AC-3 |
| **Steps** | WakeJob target=agy |
| **Expected** | Thinking + update as agy only |

### TP-10-B-21 — Agy CLI lock serializes

| | |
| --- | --- |
| **Spec** | FR-W10, AR-5 |
| **Steps** | attempt overlapping agy spawns |
| **Expected** | second waits or rejects; never parallel |

### TP-10-B-22 — Agy conversation pin

| | |
| --- | --- |
| **Spec** | FR-W11, AC-9 |
| **Steps** | first agy wake creates uuid; second reuses |
| **Expected** | state.sessions.agy_conversation_id stable |

### TP-10-B-23 — Agy FINAL_ERR same bubble

| | |
| --- | --- |
| **Spec** | FR-W14 |
| **Steps** | mock CLI fail/timeout |
| **Expected** | update same msg_id with error; no second post |

### TP-10-B-24 — Grok CLI argv restricted default

| | |
| --- | --- |
| **Spec** | FR-W2 |
| **Steps** | capture argv |
| **Expected** | permission-mode auto / no always-approve unless elevated |

### TP-10-B-30 — Single bubble per wake

| | |
| --- | --- |
| **Spec** | FR-W30, AC-11 |
| **Steps** | count postMessage for answer path |
| **Expected** | one Thinking post + updates; no second answer postMessage |

### TP-10-B-31 — Footer stripped from visible update

| | |
| --- | --- |
| **Spec** | OD-10-3 |
| **Steps** | CLI returns body+footer; finalize |
| **Expected** | visible body without `---rc-collab---` |

---

## 9. L3 — State durability

### TP-10-S-01 — Restart mid-epoch

| | |
| --- | --- |
| **Spec** | AC-9, G6 |
| **Steps** | write state with active epoch hop=2 uuid set; reload process/module; read state |
| **Expected** | same epoch id, hop, peer counters, conversation id |

### TP-10-S-02 — Processed mids survive

| | |
| --- | --- |
| **Steps** | mark mid; reload; redeliver |
| **Expected** | no re-enqueue |

### TP-10-S-03 — Pause bit survives

| | |
| --- | --- |
| **Steps** | pause; reload; classify handoff |
| **Expected** | still blocked |

---

## 10. L inject content cases

### TP-10-I-01 — Lead template full-peer language

| | |
| --- | --- |
| **Spec** | §10.2, AC-10 |
| **Steps** | load lead template |
| **Expected** | contains full peer / under-use failure / @agy package / contribution map |

### TP-10-I-02 — Peer template not intake

| | |
| --- | --- |
| **Spec** | §10.3 |
| **Steps** | load peer template |
| **Expected** | not intake; return @grok; full reasoning; no rubber-stamp |

### TP-10-I-03 — Dynamic L3 block

| | |
| --- | --- |
| **Steps** | build_inject(epoch, phase, bar) |
| **Expected** | goal, hop, budget, peer_bar numbers present |

### TP-10-I-04 — Non-collab prompt unchanged

| | |
| --- | --- |
| **Steps** | compose wake for normal DM |
| **Expected** | no lead_peer_full block |

---

## 11. L control plane (`!collab`)

### TP-10-K-01 — Principal-only arm

| | |
| --- | --- |
| **Spec** | FR-K1, NF-SPEC-09 |
| **Steps** | non-principal `!collab on`; principal `!collab on` |
| **Expected** | reject; then armed |

### TP-10-K-02 — pause / resume

| | |
| --- | --- |
| **Spec** | AC-8 |
| **Steps** | `!collab pause`; handoff blocked; `!collab resume` |
| **Expected** | as named |

### TP-10-K-03 — budget set

| | |
| --- | --- |
| **Steps** | `!collab budget 5` |
| **Expected** | remaining budget 5 |

### TP-10-K-04 — complete override

| | |
| --- | --- |
| **Spec** | FR-B14 |
| **Steps** | bar false; `!collab complete` |
| **Expected** | epoch done; logged override |

### TP-10-K-05 — new epoch command

| | |
| --- | --- |
| **Steps** | active epoch; `!collab new`; untagged |
| **Expected** | new epoch id on next intake |

### TP-10-K-06 — status shape

| | |
| --- | --- |
| **Spec** | FR-K / R16-class |
| **Steps** | `!collab status` |
| **Expected** | armed, epoch, phase, hop, budget, peer bar; **no secrets** |

### TP-10-K-07 — off restores baseline

| | |
| --- | --- |
| **Steps** | `!collab off`; untagged in room |
| **Expected** | no lead_peer_full intake |

### TP-10-K-08 — slash `/collab` not required

| | |
| --- | --- |
| **Spec** | NF-SPEC-03 RC slash steal |
| **Steps** | document that tests use `!collab` |
| **Expected** | dispatcher registers `!` prefix commands |

### TP-10-K-09 — collab command does not spawn research wake

| | |
| --- | --- |
| **Spec** | FR-K2 |
| **Steps** | `!collab status` |
| **Expected** | no grok CLI spawn |

### TP-10-K-10 — doctor

| | |
| --- | --- |
| **Spec** | FR-X5, GOAL-15 |
| **Steps** | `!collab doctor` with mocks |
| **Expected** | lines for master, armed, membership, binary, cwd, auth probe; zero tokens/passwords |

---

## 12. L security

### TP-10-X-01 — secrets never in inject

| | |
| --- | --- |
| **Spec** | FR-X1 |
| **Steps** | build inject with env containing fake password |
| **Expected** | password not substring of prompt |

### TP-10-X-02 — secrets never in RC post

| | |
| --- | --- |
| **Steps** | finalize wakes; scan posted bodies |
| **Expected** | no password/token patterns |

### TP-10-X-03 — doctor / status redaction

| | |
| --- | --- |
| **Steps** | capture command replies |
| **Expected** | no authToken / password |

### TP-10-X-04 — logs collab fields without secrets

| | |
| --- | --- |
| **Spec** | FR-X4 |
| **Steps** | inspect log line format |
| **Expected** | `collab=1 target=… hop=…` only |

---

## 13. L4 — Lab REST (real RC, no full operator required)

**Gate:** RC up; agy user exists; secrets local.

### TP-10-LAB-01 — Post and update as agy

| | |
| --- | --- |
| **Steps** | login as agy; post Thinking; chat.update |
| **Expected** | message author username=agy |

### TP-10-LAB-02 — Mention physics grok→agy

| | |
| --- | --- |
| **Spec** | FR-C32 |
| **Steps** | as grok post `@agy ping`; fetch message |
| **Expected** | mentions[] includes agy **or** text parse works on 8.6 — record which |

### TP-10-LAB-03 — Mention physics agy→grok

| | |
| --- | --- |
| **Steps** | as agy post `@grok pong` |
| **Expected** | observable mention or parse success |

### TP-10-LAB-04 — Membership

| | |
| --- | --- |
| **Steps** | list members of collab channel |
| **Expected** | principal, grok, agy present |

---

## 14. L5 — Live operator (opt-in)

**Gate:** `RC_LIVE_COLLAB=1` + principal approval; L0–L3 green; master can enable temporarily.

### TP-10-L-01 — Untagged intake smoke

| | |
| --- | --- |
| **Spec** | AC-1, AC-2, GOAL-20 |
| **Steps** | Arm room; principal posts `Build me a simple TODO app` (or PROBE variant); watch history |
| **Expected** | Grok Thinking→reply; epoch in `!collab status`; **no** agy bubble first |
| **Evidence** | screenshot/history + status paste + log line target=grok kind=intake |

### TP-10-L-02 — Handoff round-trip

| | |
| --- | --- |
| **Spec** | AC-3, AC-4, GOAL-21 |
| **Steps** | Lead posts `@agy` package (manual or model); wait agy bubble; agy `@grok` |
| **Expected** | agy Thinking as agy; then grok wake; hop increases |
| **Evidence** | two usernames; hop in status |

### TP-10-L-03 — Peer bar false Done

| | |
| --- | --- |
| **Spec** | AC-5, AC-6 |
| **Steps** | Force or induce lead Done before substantive peer (or mock in semi-live); or use low-bar room then raise |
| **Expected** | protocol notice; epoch not done |
| **Note** | If hard to induce with real models, accept L1 C-30 as primary and L-03 as best-effort |

### TP-10-L-04 — Budget stop

| | |
| --- | --- |
| **Spec** | AC-7 |
| **Steps** | `!collab budget 1`; complete one handoff; attempt second |
| **Expected** | stop card; paused |

### TP-10-L-05 — Pause / resume live

| | |
| --- | --- |
| **Spec** | AC-8 |
| **Steps** | `!collab pause` during active; peer @ ignored; `!collab resume` |
| **Expected** | as named |

### TP-10-L-06 — Doctor live

| | |
| --- | --- |
| **Steps** | `!collab doctor` |
| **Expected** | all green or actionable fails; no secrets |

### TP-10-L-07 — Disarm / master off cleanup

| | |
| --- | --- |
| **Spec** | AC-12 |
| **Steps** | `!collab off`; set master 0; kickstart if needed |
| **Expected** | room quiet; DM still works (R-01) |

### TP-10-L-08 — Full story (optional soak)

| | |
| --- | --- |
| **Steps** | Non-trivial small goal through peer deep + adversarial + done |
| **Expected** | contribution map; both agents substantive; epoch done |
| **Pass** | Soft — record transcript; not required for MVP green if L-01…L-05 pass |

---

## 15. L6 — Regression

### TP-10-R-01 — Non-collab DM principal-only

| | |
| --- | --- |
| **Spec** | AC-12, FR-P7 |
| **Steps** | DM principal message; simulate grok message in DM |
| **Expected** | principal wakes grok; bot messages do not arm collab |

### TP-10-R-02 — Usability contracts suite

| | |
| --- | --- |
| **Steps** | run `test_usability_contracts.py` (+ integration suite) |
| **Expected** | exit 0; no-dup Thinking rules intact |

### TP-10-R-03 — IMP-01 restricted default

| | |
| --- | --- |
| **Steps** | collab grok argv in channel |
| **Expected** | not always-approve unless elevated |

### TP-10-R-04 — Control plane `!goal` still works in DM

| | |
| --- | --- |
| **Steps** | `!goal status` / set in DM |
| **Expected** | unchanged NF-SPEC-03 behavior |

### TP-10-R-05 — Master default off after install

| | |
| --- | --- |
| **Steps** | fresh env without RC_AGY_COLLAB |
| **Expected** | collab path inert |

---

## 16. Negative / abuse cases

| ID | Scenario | Expected |
| --- | --- | --- |
| TP-10-N-01 | Rapid principal spam untagged | serial lock; no crash; ordered steers |
| TP-10-N-02 | Agy posts untagged "I'll take over" | Ignore; no intake |
| TP-10-N-03 | Grok @agy and @self | no self-wake; peer handoff only if peer mentioned cleanly |
| TP-10-N-04 | Empty body wake | FINAL_ERR or protocol error; bubble finalized |
| TP-10-N-05 | Agy CLI missing binary | FINAL_ERR as agy; epoch not corrupt |
| TP-10-N-06 | Secrets file unreadable for agy | doctor fail; no grok crash loops |

---

## 17. Coverage checklist (pre-release)

Print and tick:

- [ ] All TP-10-U-* implemented as pytest  
- [ ] All TP-10-C-* mocked contract tests  
- [ ] All TP-10-B-* backend mocks  
- [ ] TP-10-S-01…03  
- [ ] TP-10-K-* control plane  
- [ ] TP-10-X-* security  
- [ ] TP-10-R-01…05 regression  
- [ ] TP-10-LAB-01…04 once on real RC  
- [ ] TP-10-L-01, L-02, L-04, L-05, L-07 minimum live  
- [ ] L-03 / L-08 best-effort documented  
- [ ] NF-IP-10 GOAL-05 / 18 / 19 gates green  
- [ ] Master left **off** after live tests unless principal wants collab armed  

---

## 18. Suggested pytest module layout (implement-time)

```text
ops/rocketchat/tests/
  test_nf10_classifier.py      # U-01…
  test_nf10_epoch.py           # U-10…
  test_nf10_peer_bar.py        # U-30…
  test_nf10_footer.py          # U-50…
  test_nf10_contract.py        # C-*
  test_nf10_backend_mock.py    # B-*
  test_nf10_state.py           # S-*
  test_nf10_commands.py        # K-*
  test_nf10_security.py        # X-*
  test_nf10_regression.py      # R-* (or fold into usability)
```

Lab/live: scripts or `RC_LIVE_COLLAB=1` marked tests skipped by default.

---

## 19. Definition of done (NF-TP-10)

| Gate | Criteria |
| --- | --- |
| **Unit gate** | All L0 tests pass |
| **Contract gate** | All L1+L2+L3 pass |
| **Regression gate** | L6 pass |
| **Lab gate** | LAB-01…04 pass once |
| **Live gate** | L-01, L-02, L-04, L-05, L-07 pass; L-03 noted |
| **Spec gate** | AC-1…12 each has primary case Pass evidence |
| **Ops gate** | Master default off; doctor documented; progress note updated |

---

## 20. Document control

| Version | Date | Notes |
| --- | --- | --- |
| 1.0 | 2026-07-12 | Initial meticulous NF-TP-10 for lead_peer_full |

**Normative shalls:** [NF-SPEC-10](./spec.md).  
**Execution order of work:** [NF-IP-10](./implementation-plan.md).  
**This document:** how to prove both.
