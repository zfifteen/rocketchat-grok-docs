# Technical Specification: True voice-in-RC Call (media-plane rewrite)

| Field | Value |
| --- | --- |
| **Spec ID** | NF-SPEC-01 |
| **Version** | 1.1 |
| **Status** | Specification (implementation out of scope for this document package) |
| **Date** | 2026-07-10 · **Last reviewed:** 2026-07-10 |
| **Prior research** | [`./research.md`](./research.md) |
| **Test plan** | [`./test-plan.md`](./test-plan.md) (NF-TP-01) |
| **Implementation plan** | [`./implementation-plan.md`](./implementation-plan.md) (NF-IP-01) |
| **Related** | [`../../docs/research-voice-media-path.md`](../../docs/research-voice-media-path.md), Path C runtime under `~/.grok/agency/ops/rocketchat/call/` |
| **Owner surface** | Rocket.Chat Call (VideoConf) + media worker + Grok Voice Agent |

---

## 1. Problem and context

### 1.1 Problem statement

The principal requires a **two-way spoken conversation with Grok initiated from Rocket.Chat’s Call button** on the mobile app (DM with user `grok`). The current production-adjacent path (Path C: operator spawn → `rc_call_bot.py` Playwright join → cascaded Whisper + Grok CLI + TTS into a conference URL) does not meet reliability, latency, or maintainability bar for a first-class product feature. Prior research classified Path C as a failed media-plane design even where local “play” metrics appear green.

### 1.2 Context (live stack)

| Element | Current fact |
| --- | --- |
| Server | Rocket.Chat **8.6.0** (`agency-rocketchat` Docker) |
| Call entry | VideoConf enabled; default provider historically Jitsi; domain may retarget to local `voice_room` `:8090` |
| Control plane | `rc_operator_agent.py` detects videoconf events and spawns call child |
| Bot media | Chromium/Playwright as fake participant; virtual mic / MediaRecorder hooks |
| Speech brain | Full headless Grok CLI per turn — not speech-to-speech Realtime |
| Hard product rule | Entry UX **must** remain Rocket.Chat Call (not a standalone phone app as sole path) |

### 1.3 Spec purpose

This document is an **implementable engineering contract** for replacing the media plane while preserving Call UX. It freezes goals, requirements, architecture, interfaces, acceptance criteria, and open decisions. It does not implement runtime code.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
| --- | --- |
| G1 | Principal places a Call to `grok` in Rocket.Chat and hears Grok within a few seconds of media connect. |
| G2 | Principal speaks; Grok answers with natural turn-taking (server VAD / barge-in capable). |
| G3 | Hangup in RC cleanly ends the agent worker; no zombie Playwright/agent processes. |
| G4 | Failures are visible (chat status and/or audible cue), never silent “connected but mute.” |
| G5 | Text wake path (Thinking… → reply file → `chat.update`) remains fully functional. |
| G6 | Media participant is a **first-class SFU/agent client**, not a browser automation fake user. |

### 2.2 Non-goals

| ID | Non-goal |
| --- | --- |
| NG1 | Replacing text channels, Path A voice notes, or agency continuity. |
| NG2 | Multi-party human conference product (many humans + Grok as default). |
| NG3 | Full Grok CLI tool surface inside the Realtime voice session on day one. |
| NG4 | Making standalone Twilio/PSTN the only voice path (lab OK; not product sole path). |
| NG5 | Continuing to invest in Path C Playwright as the production media plane. |
| NG6 | Implementing this feature in the present documentation goal. |

---

## 3. Normative requirements

Requirements use **shall** (mandatory), **should** (strong default), **may** (optional).

### 3.1 Functional requirements

| ID | Requirement |
| --- | --- |
| **FR-V1** | The system **shall** retain Rocket.Chat **Call** (VideoConf) on the principal↔`grok` DM as the primary initiation surface for spoken sessions. |
| **FR-V2** | On Call start/join for a room involving principal and `grok`, the system **shall** ensure an agent media worker joins the **same** media room the principal joins. |
| **FR-V3** | The agent media worker **shall** publish outbound audio (Grok speech) and subscribe to the principal’s inbound audio track(s). |
| **FR-V4** | Speech turn-taking **shall** use a speech-to-speech stack based on **Grok Voice Agent API** (or LiveKit xAI Realtime plugin wrapping the same capability), not Whisper + full Grok CLI + `say` as the primary path. |
| **FR-V5** | The system **shall** support server-side or equivalent VAD such that barge-in is possible without waiting for a full CLI process exit. |
| **FR-V6** | On RC call hangup / leave / timeout, the system **shall** terminate the agent worker and release locks within **15 seconds**. |
| **FR-V7** | The system **shall** prevent concurrent double-spawn of media workers for the same `callId` (reuse/adapt existing call-bot lock semantics). |
| **FR-V8** | The system **shall** post at most sparse status messages to the DM (e.g. connecting / failed / ended); it **shall not** spam turn-by-turn full transcripts unless configured (see OD-V4). |
| **FR-V9** | Path A voice notes and text wakes **shall** continue to work with no intentional regression. |
| **FR-V10** | Production ops documentation **shall** designate Playwright Path C as non-production once V1 acceptance is met. |
| **FR-V11** | VideoConf URL generation **shall** be performed by a documented provider path: either a custom Apps-Engine `IVideoConfProvider` or an equivalent admin-configured provider that emits LiveKit (or approved SFU) join URLs with per-user tokens. |
| **FR-V12** | Secrets for xAI and LiveKit **shall** live only in local secret files / process env (mode restricted); they **shall not** appear in RC messages or wake prompts. |

### 3.2 Non-functional requirements

| ID | Requirement |
| --- | --- |
| **NFR-V1** | Time from media connect to first audible Grok speech **should** be ≤ **3 seconds** on a healthy network (success signal from research). |
| **NFR-V2** | End-to-end conversational latency **should** be competitive with native Grok Voice (not multi-second STT→CLI→TTS cascades). |
| **NFR-V3** | Mobile Rocket.Chat on iOS **shall** be a first-class test target for V1 acceptance. |
| **NFR-V4** | Calls **shall** enforce a configurable max duration and idle timeout (defaults: e.g. 30 min max / 2 min idle — exact values open OD-V5). |
| **NFR-V5** | Agent worker **shall** be restartable via launchd or operator-supervised spawn with KeepAlive-compatible failure isolation. |
| **NFR-V6** | Observability **shall** include structured logs with `callId`, join time, disconnect reason, and minute counters. |
| **NFR-V7** | Design **should** prefer LiveKit Cloud or a TURN-capable SFU for cellular NAT; pure host-only mesh without TURN is not acceptable for production cellular. |

### 3.3 Security and trust requirements

| ID | Requirement |
| --- | --- |
| **SR-V1** | Only principal-initiated calls to `grok` **shall** spawn the production agent worker (same principal-only trust model as text). |
| **SR-V2** | LiveKit (or SFU) tokens **shall** be short-lived and scoped to the call room identity `grok` / principal as appropriate. |
| **SR-V3** | Voice-session tools (if any in V3) **shall** default to a reduced tool set; elevation for heavy CLI work **shall** hand off to the text wake path under existing approval modes. |

---

## 4. Architecture and design decisions

### 4.1 Selected architecture (from research Option B)

```
Principal phone — RC Call button
        │ VideoConf start / join (RC 8.6)
        ▼
Rocket.Chat
        │ IVideoConfProvider.generateUrl / customizeUrl
        │   → LiveKit room URL + JWT (room named from callId)
        ▼
LiveKit SFU (cloud or self-host + TURN)
        │ principal client joins via RC Call UX
        │
        ▼
Agent worker (LiveKit Agents + xai.realtime.RealtimeModel
              OR direct wss://api.x.ai/v1/realtime)
  identity: grok
  publish: TTS/audio out
  subscribe: principal mic
        │
        ▼
Optional: sparse DM status via operator REST
Optional V3: tool calls or enqueue text wake → agency cwd
```

### 4.2 Decision record

| Decision | Choice | Rationale | Rejected |
| --- | --- | --- | --- |
| D1 Media plane | LiveKit SFU + first-class agent participant | Published xAI + LiveKit pattern; not browser puppet | Path C Playwright production |
| D2 Speech brain | Grok Voice Agent / Realtime | Native S2S, VAD, barge-in | Whisper + CLI + `say` primary |
| D3 RC entry | Keep VideoConf Call + custom provider | Hard requirement: voice **in** RC Call | Twilio-only product |
| D4 Control spawn | Operator continues to spawn worker on videoconf event | Reuses `rc_operator_agent` hook | Separate always-on conference bot without RC signal |
| D5 Team Voice / SIP | Not primary for v1 | Ops-heavy; undocumented agent endpoint | Primary SIP UA |
| D6 voice_room mesh | Lab/historical after V1 | Lobby-free preflight only | Production SFU replacement |

### 4.3 Component inventory (target)

| Component | Responsibility | Likely location |
| --- | --- | --- |
| VideoConf provider app | `IVideoConfProvider` URL/token generation | New Apps-Engine app package |
| Operator spawn hook | Map call event → worker argv; lock; status | `wake/rc_operator_agent.py` (modify later) |
| Agent worker | Join LiveKit; Realtime session; cleanup | New under `ops/rocketchat/call/` (or `voice_agent/`) |
| Secrets | `XAI_API_KEY`, LiveKit API key/secret | `~/.grok/agency/secrets/` |
| Runbook | Call path ops | `ops/ROCKETCHAT.md` update at implement time |
| Preflight | Dual-peer audio gate adapted to LiveKit | Extend preflight protocol |

### 4.4 Call lifecycle (normative sequence)

1. Principal initiates Call on DM `grok`.  
2. RC creates videoconf; provider returns LiveKit URL for `callId`.  
3. Operator observes call (existing videoconf detection path).  
4. Operator acquires call lock for `callId`; spawns agent worker with `callId`, room name, token material (or token mint endpoint).  
5. Worker joins SFU as `grok`; principal joins via RC client.  
6. Worker starts Realtime session; plays short greeting (configurable).  
7. Duplex conversation until hangup, max duration, or idle timeout.  
8. Worker leaves SFU; operator releases lock; optional single status message.  
9. On failure at any step after spawn: worker exits non-zero; operator logs; principal-visible status **shall** be attempted.

---

## 5. Integration contracts (live stack)

### 5.1 Must integrate with

| Interface | Contract |
| --- | --- |
| `rc_operator_agent` videoconf handler | Spawn target changes from Playwright bot to agent worker; logging fields preserved (`callId`, room id) |
| RC REST `video-conference.join/info/leave` | Worker or operator may still use join semantics as needed for callee registration; exact split is implementation detail but join registration **shall** stop infinite ring where applicable |
| `NO_DUPLICATE_POSTS` | Voice **shall not** create duplicate answer bubbles; sparse status only |
| Text wake | Unaffected; separate code path |
| launchd | New or adapted KeepAlive for long-lived LiveKit/token services if self-hosted; worker may remain on-demand spawn |
| Secrets hygiene (IMP-07) | No secret material in prompts or RC posts |

### 5.2 Explicit deprecation contract

| Item | After V1 acceptance |
| --- | --- |
| `rc_call_bot.py` Playwright path | Marked deprecated for production; may remain behind `RC_CALL_MEDIA_BACKEND=playwright` for lab |
| `voice_room` production use | Not required for production Call; may remain for offline demos |
| meet.jit.si public lobby path | Not production |

### 5.3 External primary interfaces

| System | Interface |
| --- | --- |
| Rocket.Chat Apps-Engine | `IVideoConfProvider` (`generateUrl`, `customizeUrl`, `isFullyConfigured`) — [developer docs](https://developer.rocket.chat/docs/video-conferencing-apps) |
| xAI | `wss://api.x.ai/v1/realtime?model=grok-voice-latest` — [Voice Agent API](https://docs.x.ai/developers/model-capabilities/audio/voice-agent) |
| LiveKit | Agents framework + [xAI Realtime plugin](https://docs.livekit.io/agents/models/realtime/plugins/xai/) |

---

## 6. Interfaces and control surfaces

### 6.1 Principal-facing

| Surface | Spec |
| --- | --- |
| RC Call button | Primary start |
| RC hangup | Primary stop |
| Optional DM status lines | Connecting / failed / ended only unless transcript mode enabled |

### 6.2 Operator / env configuration (implement-time)

| Variable (proposed) | Purpose | Default (proposed) |
| --- | --- | --- |
| `RC_CALL_MEDIA_BACKEND` | `livekit` \| `playwright` (lab) | **`playwright` until V4 cutover**, then **`livekit`** (NF-IP-01) |
| `RC_LIVEKIT_URL` | SFU WebSocket URL | required for livekit |
| `RC_LIVEKIT_API_KEY` / `SECRET` | Token mint | secrets file |
| `RC_VOICE_MAX_DURATION_S` | Hard stop | TBD OD-V5 |
| `RC_VOICE_IDLE_TIMEOUT_S` | Idle stop | TBD OD-V5 |
| `RC_VOICE_GREETING` | First utterance | short fixed string |
| `XAI_API_KEY` | Voice Agent | secrets file |

### 6.3 Worker CLI contract (proposed)

```text
voice_agent_worker --call-id <id> --room-id <rid> --room-name <name> [--livekit-url ...]
```

Exit codes: `0` clean hangup; non-zero failure classes logged.

---

## 7. Phased delivery and acceptance criteria

### 7.1 Phases

| Phase | Scope | Exit criteria |
| --- | --- | --- |
| **V0** | LiveKit + Realtime agent joinable from mobile browser (no RC) | Two-way audio verified |
| **V1** | Provider URL + principal Call + agent auto-join + greeting | Principal hears Grok **inside RC Call** on phone |
| **V2** | VAD/barge-in, hangup cleanup, status, locks, max/idle timeouts | Natural turns; clean leave; no zombies |
| **V3** | Reduced tools + handoff to text wake for heavy work | Spoken “fix X” can escalate safely |
| **V4** | Deprecate Playwright production path; runbook update | Ops docs point to LiveKit path only |

### 7.2 Acceptance criteria (V1 gate)

- [ ] AC-V1.1: From phone RC app, Call `grok`; media connects; **audible** greeting ≤ 3s of media connect on healthy path.  
- [ ] AC-V1.2: Principal speaks a short phrase; receives coherent spoken reply without typing.  
- [ ] AC-V1.3: Hangup ends worker; second Call within 60s succeeds.  
- [ ] AC-V1.4: Forced media failure produces chat status or clear log + no infinite ring.  
- [ ] AC-V1.5: Text DM wake still posts Thinking… and finalizes reply file path.  
- [ ] AC-V1.6: No xAI/LiveKit secrets in RC message history during test call.  

### 7.3 Validation strategy (implement-time)

| Layer | Method |
| --- | --- |
| Unit | Token mint, lock acquire/release, URL generation pure functions |
| Integration | Dual-peer preflight against LiveKit room (RMS / track presence) |
| Manual | Principal phone Call T5 protocol adapted from existing preflight doc |
| Regression | Existing RC usability contracts for text path |

---

## 8. Risks, dependencies, and mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Mobile RC cannot embed custom provider | High | Early phone prototype; browser-open fallback documented |
| TURN/NAT on cellular | High | LiveKit Cloud or dedicated TURN |
| Cost per audio minute | Medium | Max duration; idle timeout; metering logs |
| Dual brain context drift (Voice vs CLI) | Medium | Explicit handoff; room session pin for text only |
| Apps-Engine version skew on 8.6 | Medium | Pin app API; private app install test |
| Path C confusion post-ship | Low | Runbook deprecation; feature flag |

### Dependencies

- xAI API access with Voice Agent entitlement  
- LiveKit project (cloud) or self-hosted SFU + TURN  
- Ability to install private VideoConf app on this RC 8.6 workspace  
- Operator process change window (launchd kickstart)

---

## 9. Open decisions

| ID | Decision | Default if forced |
| --- | --- | --- |
| **OD-V1** | LiveKit Cloud vs self-host on Mac | Cloud for V1 cellular reliability |
| **OD-V2** | Direct xAI Realtime WS vs LiveKit plugin only | LiveKit plugin for SFU lifecycle |
| **OD-V3** | Voice tool sandbox vs agency cwd tools | Reduced tools until V3 |
| **OD-V4** | Transcript in DM: none / summary / full | Summary optional; default none |
| **OD-V5** | Exact max/idle timeout values | 1800s max / 120s idle (proposal) |
| **OD-V6** | Retire `voice_room` after V4 or keep lab | Keep lab, remove from Call path |

---

## 10. Traceability

| Spec element | Research anchor |
| --- | --- |
| Architecture Option B | Research §3 Option B / §7 recommended |
| Hard requirement Call-in-RC | Research §1.1; `docs/research-voice-media-path.md` §0 |
| Path C failure classes | Research §1.3; prior F1–F7 |
| Phases V0–V4 | Research §7 |
| Stack components | `docs/architecture.md`, `call/rc_call_bot.py`, `voice_room/` |

---

## 11. Document control

- **Normative for implementation** when a future implementer goal adopts NF-SPEC-01.  
- **Research remains** at `research.md` in this bundle for rationale and option space.  
- Conflicts: if implementation discovers RC 8.6 provider constraints, update this spec version and log OD resolution — do not silently reintroduce Playwright as production without a new decision record.
