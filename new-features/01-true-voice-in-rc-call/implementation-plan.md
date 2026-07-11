# Implementation plan: True voice-in-RC Call (media-plane rewrite)

| Field | Value |
| --- | --- |
| **ID** | NF-IP-01 |
| **Feature** | True voice-in-RC Call — media-plane rewrite |
| **Spec** | [NF-SPEC-01](./spec.md) (**source of truth for flags & shalls**) |
| **Test plan** | [NF-TP-01](./test-plan.md) (**source of truth for validation gates**) |
| **Research** | [research.md](./research.md) |
| **Runtime home** | `~/.grok/agency/ops/rocketchat/` (`call/`, `wake/rc_operator_agent.py`, optional Apps-Engine app) |
| **Status** | Implementation-planning documentation only · **Last reviewed:** 2026-07-10 |

---

## 1. Overview and goals

### 1.1 Problem

Path C (`rc_call_bot.py` Playwright + cascaded Whisper/CLI/TTS) does not meet production duplex reliability. The product goal is spoken Grok **inside Rocket.Chat Call**, not a separate phone app.

### 1.2 Primary objective

Ship a **feature-flagged** LiveKit (or approved SFU) + Grok Voice Agent media path such that principal Call → agent joins same room → duplex audio → clean hangup, with Playwright retained only as lab backend, text wake unaffected.

### 1.3 Success metrics (production)

| Metric | Target |
| --- | --- |
| Greeting latency after media connect | ≤ 3 s (healthy path) |
| Zombie workers after hangup | 0 within 15 s |
| Text wake regression | Usability contracts green |
| Secrets in RC history during call tests | 0 |
| Default production backend after cutover | `livekit` |

### 1.4 Document chain

Research → NF-SPEC-01 → NF-TP-01 → **this plan**.

---

## 2. Assumptions and prerequisites

| Assumption | Evidence / action |
| --- | --- |
| RC 8.6 VideoConf Call remains entry UX | Live stack today |
| Operator already spawns on videoconf events | `rc_operator_agent.py` |
| xAI Voice Agent + LiveKit access available | Provision before V0 |
| Private VideoConf app installable | OD-V1 if blocked |
| Mac awake + Docker + ngrok for phone tests | Existing ops |

**Do not start V1** until V0 dual-peer audio is green (fail closed on media quality).

---

## 3. Target architecture (execution summary)

```
RC Call → IVideoConfProvider (LiveKit URL+JWT)
       → operator spawn voice_agent_worker(callId)
       → LiveKit Agents + xai.realtime / Realtime WS
       → sparse DM status; hangup → lock release
```

**Flag:** `RC_CALL_MEDIA_BACKEND=livekit|playwright` (default `playwright` until cutover; then `livekit`).

---

## 4. Phased work breakdown

Effort is **engineering-days** for one experienced owner familiar with this Mac stack (ranges, not calendar promises).

### Phase V0 — Lab media only (no RC)  
**Effort:** 3–5 d  
**Goal:** Prove duplex audio with LiveKit + Grok Voice outside RC.

| # | Task | Deliverables | Validation (NF-TP) |
| --- | --- | --- | --- |
| V0.1 | LiveKit project (cloud preferred) + secrets skeleton | `secrets/` keys documented (not committed); env template | Config present |
| V0.2 | Minimal agent worker join room + Realtime | New module e.g. `call/voice_agent_worker.py` (or `voice_agent/`) | TP-V-03 brain type |
| V0.3 | Dual-peer preflight (browser principal + worker) | Script/report under logs or docs tools | TP-V-02 latency record |
| V0.4 | Greeting + one spoken turn | Logs with room/call ids | Manual L2 |

**Exit:** Two-way audio works; measured greeting latency recorded.  
**Rollback:** Delete lab secrets usage; no production flag change.

---

### Phase V1 — RC Call entry + auto-join  
**Effort:** 5–8 d  
**Depends on:** V0 exit

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| V1.1 | Apps-Engine `IVideoConfProvider` (or admin URL template) | App package / provider config | TP-V-01 URL/token |
| V1.2 | Point workspace Call provider at LiveKit generator | RC admin settings change procedure in runbook draft | Call URL is LiveKit |
| V1.3 | Operator spawn switch on `RC_CALL_MEDIA_BACKEND` | Patch `rc_operator_agent.py` videoconf handler; keep Playwright path | TP-V-14 |
| V1.4 | Reuse/adapt call lock for `callId` single-flight | Lock helpers + tests | TP-V-07, E-V-08 |
| V1.5 | Sparse status messages (connecting/failed) | REST post as grok; no flood | TP-V-08 |
| V1.6 | Phone Call smoke | Principal Call on iOS | AC-V1.1–V1.2, TP-V-02 |
| V1.7 | Secrets scan of DM history after test | Script or manual | TP-V-09, AC-V1.6 |
| V1.8 | Text wake smoke | DM “ping” | TP-V-10, AC-V1.5 |

**Exit:** AC-V1.1–V1.6 from NF-SPEC-01.  
**Flag default:** still `playwright` in production launchd until V4; enable `livekit` only on test launchd override or secondary plist during soak.

---

### Phase V2 — Production hardening  
**Effort:** 4–6 d  
**Depends on:** V1 exit

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| V2.1 | Hangup / leave hooks; cleanup ≤ 15 s | Worker lifecycle + operator join | TP-V-05, TP-V-06 |
| V2.2 | Max duration + idle timeout env | `RC_VOICE_MAX_DURATION_S`, `RC_VOICE_IDLE_TIMEOUT_S` | TP-V-11, E-V-idle |
| V2.3 | Barge-in / server VAD config | Realtime session settings | TP-V-04 |
| V2.4 | Failure status on token/media errors | Clear chat/log | TP-V-13, E-V-06/07 |
| V2.5 | Edge suite: network drop, re-call, agent-only room | Lab scripts + notes | E-V-01,09,10 |
| V2.6 | Observability: structured logs callId, minutes | Log schema | NFR-V6 |

**Exit:** V2 cases in NF-TP-01 green; no zombie workers in soak (e.g. 10 calls).

---

### Phase V3 — Tools / handoff (optional product)  
**Effort:** 3–5 d  
**Depends on:** V2

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| V3.1 | Reduced tool set on Voice Agent | Config allowlist | SR-V3 |
| V3.2 | Handoff to text wake for heavy work | Enqueue wake in agency/channel cwd | Manual + no double posts |
| V3.3 | Document dual-brain policy | Ops + reply_prompt note | Review |

**Exit:** Spoken “look at STATE” or similar can escalate without full CLI-as-audio-brain.

---

### Phase V4 — Cutover and deprecation  
**Effort:** 2–3 d  
**Depends on:** V2 minimum; V3 optional

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| V4.1 | Default `RC_CALL_MEDIA_BACKEND=livekit` on operator launchd | Plist + kickstart procedure | TP-V-14 |
| V4.2 | Update `ops/ROCKETCHAT.md` + architecture Path C/D | Docs | Review |
| V4.3 | Mark Playwright path lab-only | Code comments + flag | E-V-legacy-pathc |
| V4.4 | Decide voice_room fate (lab keep vs stop Call routing) | OD-V6 resolution note | — |

**Exit:** Production Calls use LiveKit path; runbook no longer presents Path C as primary.

---

## 5. File and integration map (implement-time)

| Area | Likely paths | Change type |
| --- | --- | --- |
| New worker | `ops/rocketchat/call/voice_agent_worker.py` (or `voice_agent/`) | Add |
| Spawn wrapper | `call/run_voice_agent.sh` | Add |
| Operator | `wake/rc_operator_agent.py` videoconf branch | Modify |
| Locks | existing call-bot lock patterns | Reuse/extend |
| Provider app | new Apps-Engine project (separate tree) | Add |
| Secrets | `~/.grok/agency/secrets/` + README | Add keys (not git) |
| launchd | optional worker template; operator env flag | Modify |
| Tests | `ops/rocketchat/tests/` + preflight | Add |
| Docs | `ROCKETCHAT.md`, `docs/architecture.md` | Modify |

**Do not** break: `NO_DUPLICATE_POSTS`, text `_process_pending_item`, restricted wake flags.

---

## 6. Dependencies and sequencing with other features

| Dependency | Relationship |
| --- | --- |
| NF-IP-02 streaming | Independent; text path must stay green during voice work |
| NF-IP-03 control plane | Optional later `/call status`; not blocking V1 |
| Docker/RC up | Hard prerequisite for V1+ |
| LiveKit Cloud vs self-host | OD-V1 — **decide before V1.1** |

**Recommended org sequencing vs other features:** Ship **NF-IP-02 T0** (structured FINAL_ERR) and **NF-IP-03 P0** first if bandwidth is limited — they reduce phone pain faster with less external dependency. Voice V0 can run in parallel as a spike.

---

## 7. Rollout, feature flags, rollback

### Flags

| Flag | Values | Default pre-cutover | Default post-V4 |
| --- | --- | --- | --- |
| `RC_CALL_MEDIA_BACKEND` | `livekit` \| `playwright` | `playwright` | `livekit` |
| `RC_VOICE_MAX_DURATION_S` | int | e.g. 1800 | same |
| `RC_VOICE_IDLE_TIMEOUT_S` | int | e.g. 120 | same |

### Cutover steps

1. Soak `livekit` on operator with env override (not default) for N days / M successful Calls.  
2. Flip launchd default to `livekit`.  
3. `launchctl kickstart -k …rocketchat-operator`.  
4. One principal Call smoke + text DM smoke.  
5. Update runbook.

### Rollback

1. Set `RC_CALL_MEDIA_BACKEND=playwright` (or previous).  
2. Kickstart operator.  
3. If provider URL broken, re-enable prior Jitsi/voice_room provider settings from backup notes.  
4. Kill stray workers by lock/PID files.

**Rollback RTO target:** &lt; 10 minutes for flag flip.

---

## 8. Validation mapping (NF-TP-01)

| Phase | Must pass before promoting |
| --- | --- |
| V0 | TP-V-02 (lab), TP-V-03 |
| V1 | AC-V1.1–V1.6, TP-V-01,07–10,12–13 |
| V2 | TP-V-04–06,11 + key E-V-* |
| V4 | TP-V-14 + docs |

Always: text usability contracts + no secrets in history.

---

## 9. Risks and ops impact

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Mobile RC cannot embed LiveKit | High | Early phone prototype; browser-open fallback |
| API cost | Medium | Max/idle timeouts; metering logs |
| Operator spawn bugs break text | High | Flag isolation; regression TP-V-10 first every PR |
| Secret leakage | Critical | Env-only; history scan in CI-ish script |
| Dual brain confusion | Medium | V3 handoff docs |
| Path C confusion | Low | V4 runbook |

**Ops impact:** New secrets rotation; possible LiveKit billing; Call debugging shifts from Playwright logs to worker + LiveKit dashboard.

---

## 10. Suggested PR / change stack

| PR order | Scope | Independent review? |
| --- | --- | --- |
| PR1 | Worker skeleton + unit tests (no operator default change) | Yes |
| PR2 | Operator backend flag + lock (default playwright) | Yes |
| PR3 | Provider app + runbook draft | Yes |
| PR4 | V2 timeouts/cleanup | Yes |
| PR5 | Default flip + deprecation docs | After soak |

---

## 11. Effort summary

| Phase | Effort (eng-days) |
| --- | --- |
| V0 | 3–5 |
| V1 | 5–8 |
| V2 | 4–6 |
| V3 | 3–5 (optional) |
| V4 | 2–3 |
| **Total (V0–V2+V4)** | **~14–22** |
| **With V3** | **~17–27** |

---

## 12. Open decisions to resolve before/during build

| ID | Decision | Blocker for |
| --- | --- | --- |
| OD-V1 | Cloud vs self-host LiveKit | V1.1 |
| OD-V2 | Plugin vs direct Realtime WS | V0.2 |
| OD-V4 | Transcript policy | V1.5 |
| OD-V5 | Exact timeout numbers | V2.2 |
| OD-V6 | voice_room retention | V4.4 |

---

## 13. References

- NF-SPEC-01 architecture Option B, FR-V*, AC-V1.*  
- NF-TP-01 TP-V-* / E-V-*  
- Runtime: `call/rc_call_bot.py`, `voice_room/`, operator videoconf spawn  
- `docs/research-voice-media-path.md`, `docs/preflight-voice-test-protocol.md`  
- External: xAI Voice Agent, LiveKit Agents xAI plugin, RC `IVideoConfProvider`  
