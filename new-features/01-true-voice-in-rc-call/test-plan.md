# Test plan: True voice-in-RC Call (media-plane rewrite)

| Field | Value |
| --- | --- |
| **ID** | NF-TP-01 |
| **Feature** | True voice-in-RC Call — media-plane rewrite |
| **Spec** | [`./spec.md`](./spec.md) (NF-SPEC-01) |
| **Implementation plan** | [`./implementation-plan.md`](./implementation-plan.md) (NF-IP-01) |
| **Research** | [`./research.md`](./research.md) |
| **Related** | [`../../docs/preflight-voice-test-protocol.md`](../../docs/preflight-voice-test-protocol.md), Path C `call/rc_call_bot.py`, `voice_room/` |
| **Type** | Unit + integration + dual-peer preflight + principal phone manual |
| **Status** | Test-planning documentation only · **Last reviewed:** 2026-07-10 |
| **Flags under test** | `RC_CALL_MEDIA_BACKEND`, `RC_VOICE_MAX_DURATION_S`, `RC_VOICE_IDLE_TIMEOUT_S` |

---

## 1. Scope and traceability

### 1.1 In scope

Verification that a future LiveKit (or approved SFU) + Grok Voice Agent path:

- Is entered via Rocket.Chat **Call** on DM `grok`
- Joins the **same** media room as the principal
- Delivers duplex audio with cleanup, locks, and no secret leakage
- Does **not** regress text wake (Thinking… / reply file)

### 1.2 Out of scope (this plan’s execution)

- Implementing the media plane
- Continuous multi-hour load testing as proof of **plan** completeness
- Multi-party human conferences

### 1.3 Requirement traceability map

| Spec IDs | Covered by cases |
| --- | --- |
| FR-V1–V3, AC-V1.1–V1.2 | TP-V-01, TP-V-02, TP-V-M1 |
| FR-V4–V5 | TP-V-03, TP-V-04 |
| FR-V6–V7 | TP-V-05, TP-V-06, **E-V-*** |
| FR-V8–V12, AC-V1.4–V1.6 | TP-V-07, TP-V-08, TP-V-09 |
| FR-V9, AC-V1.5 | TP-V-10 |
| NFR-V1–V4 | TP-V-02, TP-V-11, E-V-idle |
| SR-V1–V3 | TP-V-12, E-V-nonprincipal |

---

## 2. Test strategy and layers

| Layer | What it proves | When runnable |
| --- | --- | --- |
| **L0 Unit** | URL/token helpers, lock acquire/release, spawn argv, timeout config | Always (CI) |
| **L1 Integration** | Operator spawn hook → worker process lifecycle (mocked SFU/Realtime) | CI with mocks |
| **L2 Preflight dual-peer** | Two participants in LiveKit room; remote track presence / RMS | Lab Mac; adapted from existing preflight |
| **L3 Principal phone (manual)** | Real RC Call UX on iOS + audible duplex | Principal-gated; Mac awake |
| **L4 Regression** | Text wake usability contracts still pass | Always |

**Pass rule:** A phase (V0–V4 per spec) is “done” only when all cases tagged for that phase pass or are explicitly waived with OD reference.

---

## 3. Preconditions

### Common

- Spec NF-SPEC-01 adopted for implementation branch
- Secrets available in test env (never committed): xAI + LiveKit (or mock servers)
- Operator can log as `grok`; principal account available for L3
- Docker RC 8.6 up for L1+ involving RC APIs

### Phase-specific

| Phase | Extra preconditions |
| --- | --- |
| V0 | Browser-joinable LiveKit room; agent worker binary |
| V1 | Custom VideoConf provider installed; Call button points at LiveKit URL |
| V2+ | Hangup hooks, idle/max duration config |

---

## 4. Concrete test cases

### TP-V-01 — Provider URL generation (unit)

| | |
| --- | --- |
| **Phase** | V1 |
| **Preconditions** | Provider module / pure function under test |
| **Steps** | 1) Call `generateUrl`/`customizeUrl` with sample `callId` and principal user. 2) Inspect URL and token claims. |
| **Expected** | URL targets configured LiveKit host; room name derived from `callId`; token identity/scopes present; no raw API secret in URL query beyond JWT. |
| **Pass** | FR-V11, SR-V2 |

### TP-V-02 — Greeting latency (preflight / manual)

| | |
| --- | --- |
| **Phase** | V1 |
| **Preconditions** | Two peers or principal+agent in room; timer from media-connect event |
| **Steps** | Connect both sides; measure time to first non-silence outbound agent audio (remote RMS or principal report). |
| **Expected** | ≤ **3 s** on healthy network (NFR-V1 / AC-V1.1). |
| **Pass** | AC-V1.1; record measured value |

### TP-V-03 — Speech-to-speech brain (not CLI cascade)

| | |
| --- | --- |
| **Phase** | V1–V2 |
| **Preconditions** | Instrumented worker (log line for backend type) |
| **Steps** | Complete one spoken turn; inspect logs/process tree. |
| **Expected** | No per-turn full Grok CLI spawn as primary audio brain; Realtime/Voice Agent session present. Whisper+CLI+`say` not used as primary path. |
| **Pass** | FR-V4 |

### TP-V-04 — Barge-in / VAD

| | |
| --- | --- |
| **Phase** | V2 |
| **Preconditions** | Agent mid-utterance |
| **Steps** | Principal speaks over agent; observe agent stop/interrupt and respond. |
| **Expected** | Barge-in without waiting for full CLI process exit. |
| **Pass** | FR-V5 |
| **Note** | Manual if automated VAD harness unavailable; mark OD if model lacks barge-in config |

### TP-V-05 — Hangup cleanup

| | |
| --- | --- |
| **Phase** | V2 |
| **Preconditions** | Active call; known worker PID |
| **Steps** | Principal hangs up in RC; wait ≤ 15 s; check process list and lock files. |
| **Expected** | Worker exited; call lock released; no zombie Playwright/agent (FR-V6). |
| **Pass** | AC-V1.3 (first half) |

### TP-V-06 — Immediate re-call

| | |
| --- | --- |
| **Phase** | V2 |
| **Steps** | After TP-V-05, start second Call within 60 s. |
| **Expected** | New worker joins; greeting again; no stuck “ring forever.” |
| **Pass** | AC-V1.3 |

### TP-V-07 — Single-flight lock (double spawn)

| | |
| --- | --- |
| **Phase** | V1 |
| **Steps** | Force two spawn signals for same `callId` (duplicate event). |
| **Expected** | Only one worker for `callId`; second spawn no-ops or attaches; lock semantics hold (FR-V7). |
| **Pass** | Unit/integration with fake events |

### TP-V-08 — Sparse status, no transcript flood

| | |
| --- | --- |
| **Phase** | V1–V2 |
| **Steps** | Full short call with default transcript config. |
| **Expected** | At most sparse status lines (connecting/failed/ended); no per-turn full transcript posts (FR-V8). |
| **Pass** | Count `grok` messages in DM during call |

### TP-V-09 — Secrets not in RC history

| | |
| --- | --- |
| **Phase** | V1 |
| **Steps** | After test call, search DM history for LiveKit API key patterns / xAI key prefixes. |
| **Expected** | Zero matches (FR-V12, AC-V1.6). |
| **Pass** | Automated string scan of history export |

### TP-V-10 — Text wake regression

| | |
| --- | --- |
| **Phase** | Any after operator change |
| **Steps** | Send principal text DM; observe Thinking… → final reply file path. |
| **Expected** | Unchanged contract; usability tests pass (FR-V9, AC-V1.5). |
| **Pass** | L4 suite + one live smoke |

### TP-V-11 — Max duration / idle timeout

| | |
| --- | --- |
| **Phase** | V2 |
| **Steps** | A) Set short max duration (e.g. 30 s) and stay connected. B) Set short idle and silence both sides. |
| **Expected** | Worker ends with logged reason `max_duration` / `idle_timeout` (NFR-V4). |
| **Pass** | Logs + process exit |

### TP-V-12 — Principal-only spawn

| | |
| --- | --- |
| **Phase** | V1 |
| **Steps** | Simulate call event not involving principal (if multi-user ever present) or non-principal room. |
| **Expected** | Production worker **not** spawned (SR-V1). |
| **Pass** | Integration mock |

### TP-V-13 — Forced media failure visibility

| | |
| --- | --- |
| **Phase** | V1 |
| **Steps** | Break LiveKit URL or revoke token; principal places Call. |
| **Expected** | Chat status or clear failure path; no infinite ring (AC-V1.4). |
| **Pass** | Manual + log |

### TP-V-14 — Backend flag lab path

| | |
| --- | --- |
| **Phase** | V4 |
| **Steps** | Set `RC_CALL_MEDIA_BACKEND=playwright` vs `livekit`. |
| **Expected** | Documented backend selected; production default livekit after cutover. |
| **Pass** | Config inspection |

---

## 5. Edge cases and negative / failure cases

| ID | Edge / failure | Steps | Expected |
| --- | --- | --- | --- |
| **E-V-01** | Network drop mid-call | Disable Wi‑Fi 10 s then restore | Worker recovers or clean-exits with status; no orphan lock |
| **E-V-02** | Cellular ↔ Wi‑Fi roam | Switch network during call | Reconnect or clean fail; no secret leak |
| **E-V-03** | Operator restart mid-call | Kickstart operator launchd during active call | Documented behavior: leave call or reattach; no double workers |
| **E-V-04** | Mac sleep / wake | Sleep Mac during call | Call fails visibly; on wake no zombie lock blocking next call |
| **E-V-05** | Concurrent text wake during call | Principal texts while in call | Text path still works; no deadlock with call lock (or documented serialization) |
| **E-V-06** | Invalid/expired LiveKit token | Mint expired JWT | Join fails; status; exit non-zero |
| **E-V-07** | Missing XAI_API_KEY | Unset key | Fail closed at start; status; no hang |
| **E-V-08** | Duplicate videoconf events storm | Fire 10 joins for same callId | Still one worker |
| **E-V-09** | Principal never joins media | Ring/join signal without principal track | Idle timeout ends worker; no infinite greeting loop |
| **E-V-10** | Agent-only room (principal left) | Principal leaves; agent remains | Cleanup ≤ 15 s |
| **E-V-11** | Very long utterance | Principal speaks 60 s continuously | VAD segments or max buffer; no OOM crash |
| **E-V-12** | Empty / near-silent “speech” | Noise floor only | No endless false turns |
| **E-V-13** | Clock skew on JWT | System time ±10 min | Documented fail or leeway; no silent hang |
| **E-V-14** | Playwright backend on production flag mistake | livekit intended but playwright forced | Lab only; metrics show wrong backend |
| **E-V-15** | Secret in worker env printed to chat | Force error path that might dump env | Must not post secrets (scan) |
| **E-V-16** | TURN failure on strict NAT | Simulate no relay | Clear failure; not “connected but mute” without status |
| **E-V-idle** | Idle timeout boundary | Silence for TTL−1 s then speak | Call continues; at TTL+ε ends |
| **E-V-nonprincipal** | Non-principal message during call setup | Bot/self messages | No extra spawns |
| **E-V-legacy-pathc** | Old voice_room URL still configured | Call uses mesh lab only when flag says so | Production path not accidentally Path C |

---

## 6. Pass / fail and exit criteria

### Phase exit

| Phase | Exit when |
| --- | --- |
| V0 | Dual-peer browser audio works; TP-V-02 style latency recorded |
| V1 | AC-V1.1–V1.6 + TP-V-01,07–10,12–13 pass |
| V2 | TP-V-04–06,11 + E-V-01,05,09,10 pass |
| V3 | Tool handoff cases (add when V3 implemented) |
| V4 | TP-V-14 + runbook deprecates Playwright production |

### Suite pass rule

- **Fail** any case that leaves zombie workers, infinite ring, or secrets in RC.  
- **Waive** only with written OD id and residual risk.

### Evidence to retain

- Log excerpts with `callId`, PIDs  
- Latency measurement for TP-V-02  
- History scan output for TP-V-09  
- Preflight dual-peer report path

---

## 7. Open / blocked checks

| Item | Blocker | Label |
| --- | --- | --- |
| Mobile iframe vs browser-open of LiveKit | OD-V1 / phone prototype | Manual L3 |
| Exact cost metering | Live pricing | Ops note, not gate |
| Full MOS scoring | Tooling | Optional quality lab |

---

## 8. References

- NF-SPEC-01 acceptance AC-V1.1–V1.6  
- Research failure classes F1–F7  
- `docs/preflight-voice-test-protocol.md`  
- Runtime: `rc_operator_agent` videoconf spawn, `call/rc_call_bot.py` (legacy)
