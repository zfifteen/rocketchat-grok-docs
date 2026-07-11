# Feature 1 — True voice-in-RC Call (media-plane rewrite)

**Status:** Research only (no runtime implementation in this document set)  
**Date:** 2026-07-10 · **Last reviewed:** 2026-07-10  
**Stack baseline:** Rocket.Chat **8.6.0** on principal Mac; operator `rc_operator_agent.py`; Path C `call/rc_call_bot.py`; lobby-free `voice_room/` on `:8090`  
**Related prior research (do not delete):** [`docs/research-voice-media-path.md`](../../docs/research-voice-media-path.md), [`docs/implementation-plan-voice-calls.md`](../../docs/implementation-plan-voice-calls.md), [`docs/preflight-voice-test-protocol.md`](../../docs/preflight-voice-test-protocol.md)  
**This document extends** that research into an implementation-oriented feature design for production media under the **same Call button**.

### Downstream documentation (normative chain)

| Layer | Document | ID |
| --- | --- | --- |
| **Spec** (shall / architecture contract) | [spec.md](./spec.md) | NF-SPEC-01 |
| **Test plan** (cases + edge cases) | [test-plan.md](./test-plan.md) | NF-TP-01 |
| **Implementation plan** (build / flags / rollback) | [implementation-plan.md](./implementation-plan.md) | NF-IP-01 |

**Canonical recommended direction (all layers agree):** Custom VideoConf provider → LiveKit SFU + Grok Voice Agent / LiveKit xAI Realtime participant; Path C Playwright remains **live lab/MVP**, not the production target (`docs/architecture.md` Path D).

---

## 1. Problem framing (against the live stack)

### 1.1 Product requirement (hard)

The principal’s intended experience:

1. Open Rocket.Chat (mobile primary).  
2. Open DM with user **`grok`**.  
3. Press Rocket.Chat **Call** (VideoConf surface already enabled).  
4. Stay in that call UX and have a **two-way spoken** conversation.  
5. Hang up in RC ends the agent cleanly.

This is **not** “paste a LiveKit link,” “call a Twilio number only,” or “voice note → text reply.” Those may be lab proofs; they fail the hard requirement if they replace Call.

### 1.2 What exists today

| Layer | Live component | Role |
| --- | --- | --- |
| Signaling | RC VideoConf + Jitsi app (`VideoConf_Default_Provider=jitsi`) | Call button, ring, `video-conference.start/join/leave/info` |
| Operator hook | `rc_operator_agent.py` watches videoconf events; spawns call bot | Control plane |
| Media target (current MVP) | Jitsi domain **retargeted** to local **`voice_room`** (`0.0.0.0:8090`, launchd) | Lobby-free WebRTC mesh room |
| Bot media | `call/rc_call_bot.py` — Playwright Chromium joins URL as `grok` | Fake browser participant |
| Speech pipeline | TTS (`say` / ffmpeg) → virtual mic inject; remote track → MediaRecorder → Whisper → **full Grok CLI** → TTS | Cascaded, high latency |
| Async voice (orthogonal) | Path A: voice note → Whisper → text wake → Thinking… bubble | Reliable; not duplex |

Authoritative ops status: `~/.grok/agency/ops/ROCKETCHAT.md` and [`docs/architecture.md`](../../docs/architecture.md) Path C / D.

### 1.3 Why the current path is not “next level”

Documented failure classes (evidence in prior research + call logs):

| ID | Failure | Effect |
| --- | --- | --- |
| F1 | Outbound TTS “plays” locally without remote MOS | Principal silence |
| F2 | Inbound STT starved / short utterances | No turns |
| F3 | Success metrics local (buffer duration), not remote | False greens |
| F4 | ≥6 media hops | Any break → silence |
| F5 | Whisper + full CLI + `say` multi-second | Not conversational |
| F6 | Browser-as-bot (Playwright) | Fragile, not an agent API |
| F7 | Public meet.jit.si lobby/moderator | Guaranteed silence without JWT moderator |

Lobby-free `voice_room` mitigates **F7** for local/LAN preflight but does **not** fix F1–F6 class design: the bot is still a **browser puppet**, not a first-class media participant with a speech-to-speech model.

**Gap statement:** Control plane (Call button, join APIs, operator spawn) is close; **media plane + brain** must be rewritten.

---

## 2. Current baseline / interfaces (precise)

### 2.1 Rocket.Chat VideoConf as control plane

Verified on this deployment:

- `GET /api/v1/video-conference.providers` → jitsi (and/or retargeted provider).  
- `POST /api/v1/video-conference.start` on principal↔grok DM.  
- Bot: `POST /api/v1/video-conference.join` as user `grok` (stops pure “Calling…” ring).  
- `GET /api/v1/video-conference.info?callId=…`, `POST …/leave`.  

Enable script: `~/.grok/agency/ops/rocketchat/enable_conference_calls.sh`.

### 2.2 Apps-Engine provider contract (primary extension point)

Rocket.Chat documents custom VideoConf apps via **`IVideoConfProvider`** (Jitsi reference implementation):

- Source docs: [Video Conferencing Apps](https://developer.rocket.chat/docs/video-conferencing-apps)  
- Reference code: [RocketChat/Apps.Jitsi](https://github.com/RocketChat/Apps.Jitsi)  
- Permissions: `video-conference-provider`, `video-conference.read/write` ([App Permission System](https://developer.rocket.chat/docs/app-permission-system))

Key methods (from official Jitsi provider walkthrough):

| Method | Purpose |
| --- | --- |
| `isFullyConfigured()` | Domain / token secrets present |
| `generateUrl(call: VideoConfData)` | Base conference URL for `callId` / room id |
| `customizeUrl(call, user, options)` | Per-user JWT, mic/cam mute flags, prejoin off |

**Implication for Feature 1:** A custom provider can emit a **LiveKit (or other SFU) URL** while principal UX remains **Call**. Operator spawn hook continues to fire on videoconf events; it starts an **agent worker** instead of Playwright.

### 2.3 Team Voice (native) — secondary, heavy

Rocket.Chat **Team Voice** (native WebRTC / SIP via Drachtio+FreeSWITCH) is a separate product surface from VideoConf:

- Designed for **human** endpoints.  
- Premium/Enterprise add-on in RC’s commercial model.  
- No documented “attach Grok as media endpoint” API.  

A SIP UA registered as `grok` could bridge RTP ↔ Grok Voice telephony — high ops cost for a single principal pair. **Not recommended as primary** unless enterprise telephony is already required.

### 2.4 Grok speech-to-speech (authoritative media brain)

| Surface | Endpoint / package | Notes |
| --- | --- | --- |
| Grok Voice Agent API | `wss://api.x.ai/v1/realtime?model=grok-voice-latest` | OpenAI Realtime–compatible; server VAD, barge-in, tool calling, PCM/G.711 |
| xAI docs | [Voice Agent API](https://docs.x.ai/developers/model-capabilities/audio/voice-agent) | Primary API surface |
| LiveKit plugin | `livekit-agents[xai]` → `xai.realtime.RealtimeModel` | [LiveKit xAI Realtime plugin](https://docs.livekit.io/agents/models/realtime/plugins/xai/) |
| LiveKit partnership write-up | [livekit.com/blog/xai-livekit-partnership…](https://livekit.com/blog/xai-livekit-partnership-grok-voice-agent-api) | Production pattern: SFU + agent worker |

**Do not** use full Grok CLI (`~/.local/bin/grok`) as the real-time audio brain. CLI is for tool-heavy text wakes (channels, agency cwd). Voice session may **invoke** tools or hand off to CLI for heavy work, but audio turn-taking must stay on Realtime/Voice Agent.

### 2.5 Local assets reusable today

| Asset | Path / label | Reuse |
| --- | --- | --- |
| Operator WS + room pins | `wake/rc_operator_agent.py`, `state.json` | Call start/status/transcript in DM |
| Call spawn | operator videoconf handler → `run_call_bot.sh` | Swap payload to LiveKit agent job |
| voice_room | `voice_room/server.py` | Lab mesh only; not production SFU |
| Twilio secrets | `secrets/twilio.env` | Optional telephony **lab**, not RC Call substitute |
| Path A Whisper | operator STT path | Keep for voice notes; not live duplex |
| Preflight harness | `docs/tools/preflight_dual_peer_jitsi_audio.py` | Pattern for dual-peer RMS gates |

---

## 3. Candidate technical approaches

Scoring is research judgment (1–5, higher better): Reliability, RC coupling, Latency, Ops cost, Tooling, Mobile.

### Option A — Keep Path C / voice_room + harden Playwright

| Rel | RC | Lat | Ops | Tools | Mobile |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 4 | 1 | 2 | 3 | 2 |

**Idea:** More headless media flags, better VAD, headed Chromium, self-hosted Jitsi.

**Trade-offs:** Still browser-as-bot; still cascaded STT/CLI/TTS; mobile quirks remain. Prior research already marks this as non-production.

**Verdict:** Lab only.

---

### Option B — Custom VideoConf provider → LiveKit room + LiveKit Agents (xAI Realtime)

| Rel | RC | Lat | Ops | Tools | Mobile |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 5 | 5 | 3 | 4 | 5 |

```
Principal phone: RC Call button
        │ VideoConf start (unchanged UX)
        ▼
Rocket.Chat 8.6
        │ IVideoConfProvider.generateUrl → LiveKit room URL (+ token)
        ▼
LiveKit SFU (cloud or self-host)
        │ principal joins via RC-embedded / in-app provider client
        │
        ▼
Agent worker (LiveKit Agents + xai.realtime.RealtimeModel)
  joins same room as participant "Grok"
  speech-to-speech; tools optional
        │
        ▼
Optional: operator posts transcript / status to DM
```

**Pros:** First-class media; barge-in; published xAI+LiveKit path; Call button preserved via provider.  
**Cons:** New services (LiveKit keys or self-host SFU); custom Apps-Engine app to maintain; cost per audio minute (verify live xAI Voice pricing before budget).  
**Verdict:** **Recommended primary.**

---

### Option C — Self-hosted Jitsi + lib-jitsi-meet (or Colibri) agent, no Playwright

| Rel | RC | Lat | Ops | Tools | Mobile |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 5 | 3 | 2 | 3 | 4 |

**Idea:** Keep Jitsi provider; agent uses real client API instead of DOM.

**Pros:** Stays in familiar Jitsi ecosystem.  
**Cons:** Still need speech brain bridge; Jitsi agent tooling thinner than LiveKit Agents; self-host ops (Prosody, JVB, TURN).  
**Verdict:** Acceptable if LiveKit is blocked; not first choice.

---

### Option D — Team Voice / SIP UA → Grok Voice telephony

| Rel | RC | Lat | Ops | Tools | Mobile |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 3–4* | 5 | 1 | 4 | 4 |

\*Only if Team Voice Call UX is the same mental model as “Call Grok in RC.”

**Pros:** First-class audio codecs; xAI SIP bridge examples exist.  
**Cons:** Premium RC features; FreeSWITCH/Drachtio; reverse-engineered or heavy SIP stack; may feel like “phone extension,” not VideoConf Call.  
**Verdict:** Secondary / enterprise track.

---

### Option E — Standalone Grok phone (Twilio) + RC transcript only

| Rel | RC | Lat | Ops | Tools | Mobile |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 1 | 5 | 3 | 4 | 5 |

**Fails hard requirement** as sole architecture. Allowed only as **lab proof of audio quality** before wiring Option B.

---

## 4. Integration points with this deployment

### 4.1 Keep

| Piece | Why |
| --- | --- |
| Principal / grok accounts | Trust model unchanged |
| Operator videoconf spawn | Swap implementation of child process |
| DM session continuity for **text** | Separate from voice Realtime session |
| Path A voice notes | Async path remains valuable |
| NO_DUPLICATE_POSTS for text | Voice should not spam chat; optional transcript messages must be deliberate |
| Mac awake + Docker RC + ngrok | Phone reachability unchanged |

### 4.2 Replace

| Today | Target |
| --- | --- |
| `rc_call_bot.py` Playwright join | LiveKit agent job / worker join |
| Whisper + Grok CLI + `say` per turn | Grok Voice Agent Realtime session |
| Jitsi public or DIY mesh as production media | LiveKit (or self-hosted SFU) as VideoConf provider URL |
| Local-only success logs | Dual-peer remote RMS / MOS gate in preflight |

### 4.3 Add

| Component | Responsibility |
| --- | --- |
| Custom RC VideoConf app (`IVideoConfProvider`) | `generateUrl` / `customizeUrl` → LiveKit room + JWT |
| LiveKit project (cloud or local) | SFU, tokens, optional recording |
| Agent worker process (launchd) | Join room on callId; RealtimeModel; hangup cleanup |
| Secrets | `XAI_API_KEY`, LiveKit API key/secret (never in reply prompts — IMP-07) |
| Chat status hooks | “Connected / listening / error” via operator `chat.postMessage` sparingly |

### 4.4 Call lifecycle (target sequence)

1. Principal hits **Call** on DM `grok`.  
2. RC creates videoconf with custom provider URL (LiveKit room named after `callId`).  
3. Operator detects call (existing stream / REST poll of video-conference events).  
4. Operator spawns **agent worker** with `callId`, `roomName`, LiveKit token for identity `grok`.  
5. Agent joins SFU; publishes audio; subscribes principal track.  
6. Realtime session: server VAD → Grok speech → outbound audio.  
7. Hangup: RC leave + agent disconnect + optional short chat status.  
8. Heavy tool work (if needed): agent tool calls **or** enqueue text wake into agency cwd (async).

---

## 5. Risks and failure modes

| Risk | Mitigation |
| --- | --- |
| Mobile RC client cannot embed LiveKit URL like Jitsi | Prototype provider app early on **phone**; fall back to in-app browser open of same room if iframe fails |
| TURN/NAT on cellular | LiveKit cloud handles TURN; self-host must deploy TURN |
| Cost runaway on long calls | Hard max call duration; idle timeout; log minutes |
| Dual brains (Voice vs CLI) diverge context | Explicit handoff protocol: voice for conversation; CLI for deep code with room pin |
| Secrets in agent env | Env files mode 600; never inject into RC messages |
| Operator double-spawns bots | Existing call-bot lock; reuse for agent worker PID |
| Path C remnants confuse ops | Document Path C as **deprecated lab**; keep preflight for mesh only |
| RC Apps-Engine version skew on 8.6 | Pin app API to 8.6; test install via private app upload |
| Audio quality ≠ tool power | Voice agent tools subset; escalate to restricted/admin CLI wake for code edits |

---

## 6. Open questions

1. Does the stock mobile RC app render a **custom** VideoConf provider URL as smoothly as Jitsi on this workspace build?  
2. Self-host LiveKit on the Mac vs LiveKit Cloud for a single principal — ops vs reliability trade?  
3. Should voice tools share `~/.grok/agency` cwd semantics or a sandboxed tool set?  
4. Transcript policy: full transcript in DM vs silence vs summary only?  
5. Exact live pricing for Grok Voice Agent minutes (re-check console before commitment).  
6. Can existing `voice_room` be retired after Option B ships, or kept for offline LAN demos?

---

## 7. Recommended direction

### Primary

**Option B:** Custom `IVideoConfProvider` → LiveKit room; LiveKit Agents + **xAI Grok Voice Realtime** as the media brain; operator spawns the agent worker on Call.

### Phased delivery

| Phase | Deliverable | Exit criteria |
| --- | --- | --- |
| **V0** | Lab: LiveKit + Realtime agent joinable from browser (no RC) | Two-way audio works on phone browser |
| **V1** | Provider app generates LiveKit URL; principal Call joins; agent auto-joins | Principal hears greeting **inside RC Call** |
| **V2** | Server VAD, barge-in, hangup cleanup, status messages | Natural turn-taking; clean leave |
| **V3** | Tool subset + optional handoff to CLI wake for code | “Fix that bug” works without leaving voice model for every token |
| **V4** | Deprecate Playwright Path C for production; retain preflight as historical | Ops runbook points only to LiveKit path |

### Success signals (principal-centric)

1. From phone, Call Grok; **hear** spoken response within ~3s of media connect.  
2. Speak a short instruction; receive coherent spoken answer without typing.  
3. Hang up; no zombie Playwright/agent processes; next Call works.  
4. Failure is **audible or visible** (chat status), not silent Thinking-equivalent.  
5. Text wake path remains unbroken (no regression on Thinking… / reply file).

### Explicit non-goals for v1

- Replacing text channels.  
- Multi-user conference with many humans.  
- Full agency CLI tool surface inside the Realtime session on day one.

---

## 8. Sources and primary interfaces

| Kind | Reference |
| --- | --- |
| In-repo architecture | `docs/architecture.md`, `docs/message-flow.md` Path C |
| Prior voice research | `docs/research-voice-media-path.md` |
| Runtime call bot | `~/.grok/agency/ops/rocketchat/call/rc_call_bot.py` |
| Voice room | `~/.grok/agency/ops/rocketchat/voice_room/server.py` |
| Ops runbook | `~/.grok/agency/ops/ROCKETCHAT.md` |
| RC VideoConf apps | https://developer.rocket.chat/docs/video-conferencing-apps |
| RC Jitsi app source | https://github.com/RocketChat/Apps.Jitsi |
| xAI Voice Agent | https://docs.x.ai/developers/model-capabilities/audio/voice-agent |
| LiveKit xAI plugin | https://docs.livekit.io/agents/models/realtime/plugins/xai/ |
| LiveKit Agents framework | https://github.com/livekit/agents |

---

## 9. Research conclusion

The leap is not “make Playwright slightly less wrong.” It is **keep Rocket.Chat Call as the product surface** and move media to a **first-class SFU participant** driven by **Grok Voice Agent / LiveKit**. That matches published xAI and LiveKit patterns, reuses the existing operator spawn hook, and satisfies the hard requirement that Path C never will.
