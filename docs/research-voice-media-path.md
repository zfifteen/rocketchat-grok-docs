# Research: Viable technical paths for reliable Grok voice **in** Rocket.Chat

**Status:** Research complete (documentation only — no runtime changes)  
**Date:** 2026-07-10  
**Updated:** 2026-07-10 — hard requirement clarified: voice must work **inside Rocket.Chat call UX**  
**Audience:** Implementation session that owns code/config later  
**Companion docs:** [implementation-plan-voice-calls.md](implementation-plan-voice-calls.md), [message-flow.md](message-flow.md) Path C status  

---

## 0. Hard requirement (non-negotiable)

> **The entire point is voice calls with Grok working in Rocket.Chat.**

That means the principal’s primary experience is:

1. Open Rocket.Chat (mobile or desktop).  
2. Open the DM with **`grok`**.  
3. Use Rocket.Chat’s **Call** (or native Team Voice call) affordance.  
4. Stay in that call flow and have a **two-way spoken** conversation with Grok.  
5. Hear Grok; be heard; hang up in RC.

### What counts as “in Rocket.Chat”

| Counts | Does **not** count as meeting the hard requirement |
| --- | --- |
| VideoConf **Call** button on DM with `grok`, principal stays in RC call UI / in-app conference | Dialing a separate PSTN number as the only voice path |
| Rocket.Chat **Team Voice** call to user `grok` that answers with speech | “Call me” that only rings your cell outside RC |
| Same Call entry, but backend media is LiveKit/self-hosted Jitsi/Grok WebRTC **joined via RC provider** | Standalone Grok phone agent with RC only getting a transcript afterward |
| RC opens the provider room the way it does for Jitsi today (in-app / same call lifecycle) | Primary UX is a pasted link that leaves RC for a different product |

**Implication:** Standalone Twilio/xAI phone lines and “RC as transcript console only” may be useful **lab proofs** of Grok audio quality. They are **not** the product goal and must not be the final architecture unless they are subordinated to a true RC Call path.

**Still allowed:** Change media stack **under** the Call button (drop public meet.jit.si, drop Playwright, swap provider). The **entry UX** must remain Rocket.Chat calling Grok.

---

## 1. Problem statement

**Goal:** Principal places a **voice call to Grok inside Rocket.Chat** and gets a reliable, two-way spoken conversation.

**Not a goal:** Preserve Jitsi, Playwright, public meet.jit.si, macOS `say`, or Whisper specifically.  
**Not a goal:** Replace RC Call with a separate phone product.

**Success (principal-centric):**

1. Principal initiates with Rocket.Chat **Call** (or Team Voice) on DM `grok`.  
2. Principal **hears** Grok within a few seconds of connect.  
3. Principal speaks; Grok answers with natural turn-taking.  
4. Failure modes are visible (chat status + logs), not silent.  
5. Works on **mobile RC** (primary client).  
6. Hangup ends the RC call cleanly.

**Current Path C result:** Call signaling partially works; **media does not** (principal never heard audio). Treat as failed acceptance, not a polish problem.

---

## 2. What Rocket.Chat can own (call surfaces)

Rocket.Chat can participate in voice in **three different roles**. Confusing them is how Path C happened — and how “phone agent elsewhere” fails the hard requirement.

| Role | What RC does | Who owns media | Meets hard requirement? |
| --- | --- | --- | --- |
| **A. Conference host (VideoConf)** | **Call** button → marketplace / custom provider URL | External conference stack (Jitsi, BBB, … or **custom**) | **Yes**, if principal uses Call and hears Grok in that call |
| **B. Team Voice (native WebRTC / SIP)** | Native voice call signaling to user `grok` | P2P WebRTC or FreeSWITCH/SIP media | **Yes**, if `grok` is a real answering endpoint |
| **C. Control plane only** | Text, presence, transcripts, external dial | Separate voice system | **No** as sole solution (violates hard requirement) |

Our deployment today:

- Server: Rocket.Chat **8.6.0**  
- Call button: **VideoConf + Jitsi app** (`VideoConf_Default_Provider=jitsi`)  
- Bot answer: **Path C** — Playwright Chromium → public **meet.jit.si** → virtual mic / remote capture → Whisper → Grok CLI → `say`  

That is **Role A + browser automation as a fake human participant**. Right **entry**, wrong **media/bot** design.

---

## 3. Why Path C failed (technical root cause class)

### 3.1 Architecture of the broken path

```
Principal phone (RC app)
        │ signaling (VideoConf)
        ▼
Rocket.Chat 8.6  ──join API──►  user "grok" marked in call
        │
        │ URL: meet.jit.si/Agency{callId}...
        ▼
Playwright Chromium (headless)
  • getUserMedia overridden → Web Audio MediaStreamDestination (virtual mic)
  • TTS: say → wav → decodeAudioData → connect to dest
  • STT: hook RTCPeerConnection track / <audio> → MediaRecorder → Whisper
  • Brain: full Grok CLI process per turn
        │
        ▼
Principal speakers / mic   ←—— WebRTC media (must work both ways)
```

### 3.2 Failure classes (evidence-backed)

| ID | Layer | Failure | Evidence |
| --- | --- | --- | --- |
| **F1** | Outbound media | Local TTS “plays” without reaching principal | `played greeting dur=1.6s` + principal silence |
| **F2** | Inbound media | No usable speech segments | `skip short utterance 0.60s`; tiny `call-media/chunk-*` |
| **F3** | Measurement | Success metric is **local** decode duration, not remote MOS/receipt | `play_wav_in_page` returns AudioBuffer.duration only |
| **F4** | Stack depth | ≥6 independent media hops; any break → silent call | Design of Path C |
| **F5** | Latency brain | Even if media worked: Whisper + full CLI + say is multi-second | Path C README admits higher latency than native Grok voice |
| **F6** | Product surface | Public meet.jit.si + DOM inject is not an agent platform | No first-class bot API; depends on fragile JS hooks |
| **F7** | **Lobby / moderator** | Public meet.jit.si holds participants until a moderator starts the meeting; bot has no JWT moderator | Preflight screenshots 2026-07-11: both peers “Asking to join… no moderators”; `jitsi_auth_token=false`, empty app id/secret |

**Interpretation:** The challenge is **media path integration** (WebRTC conference + browser automation + public Jitsi lobby policy), not “Grok cannot do voice.” Preflight T2 proved **F7** alone is enough to guarantee silence even when local TTS “plays.” xAI’s Voice Agent stack proves speech-to-speech works when media is first-class.

### 3.3 Why “just fix Jitsi” is a weak primary plan

Even a perfect headed debug that makes greeting audible still leaves:

- Public meet.jit.si policy/DOM churn  
- Mobile client quirks for audio-only peers  
- Headless vs headed Chromium media differences  
- High STT/CLI/TTS latency  
- No barge-in, no server VAD, no telephony codec path  

**Research recommendation:** Do not invest further engineering in Path C as the **production** media plane. Optional: keep as a lab curiosity after a real path works.

---

## 4. Rocket.Chat voice/media surfaces (what is actually available)

### 4.1 Video Conference (what we use today)

Official model: marketplace **providers** (Jitsi, BBB, Pexip, Google Meet).  
RC starts a call, generates a provider URL, clients join that third-party room.

Implications:

- RC is **not** the media SFU for VideoConf.  
- A bot must either (1) join as a **client of that provider**, or (2) ignore the provider and use something else.  
- Jitsi has no stable “agent SDK” in our stack; we used a full browser.  
- Self-hosted Jitsi helps **ops control**, not the fundamental “bot is a fake browser user” problem (unless you use `lib-jitsi-meet` or a proper XMPP/Colibri client — still large).

### 4.2 Rocket.Chat Voice (native Team Voice)

Documented separately from VideoConf:

- **Standard WebRTC:** RC signals; **P2P media between user browsers**; STUN/TURN for NAT.  
- **SIP integration:** Drachtio + SIP provider (FreeSWITCH verified); WebRTC↔SIP bridge for PSTN/PBX.  
- Requires **premium plan + Voice add-on** (docs mark Enterprise/premium).  
- Designed for **human** workspace calling, not AI agents.  
- Mobile voice is a first-class RC product goal (e.g. 8.4+ messaging), but still human client endpoints.

Implications for us:

- Enabling Team Voice does **not** give a documented “attach Grok as media endpoint” API.  
- A reliable bot would need either:
  - a **SIP user agent** that registers as Grok’s extension and bridges RTP ↔ Grok Voice, or  
  - a **custom WebRTC client** implementing RC’s call signaling (undocumented surface, high reverse-engineering cost).  
- Heavy ops (Drachtio, FreeSWITCH, TURN) for a single principal↔agent pair is disproportionate **unless** we already need enterprise telephony inside RC.

### 4.3 What we already have adjacent

| Asset | Relevance |
| --- | --- |
| Operator WebSocket + DM session continuity | Excellent **control plane** for start/status/transcript |
| Twilio ops (`ops/twilio/`, `secrets/twilio.env`) | Partial SMS; **reusable** for SIP/PSTN if we choose telephony |
| ngrok public HTTPS | Good for webhooks / web voice clients |
| Path A voice notes | Reliable **async** voice → text; not live duplex |
| Grok CLI agency cwd | Good for **tools/actions** after or beside voice; bad as real-time audio brain |

---

## 5. First-class Grok voice (what production systems use)

### 5.1 Grok Voice Agent API (realtime WebSocket)

Authoritative surface: `wss://api.x.ai/v1/realtime?model=grok-voice-latest`

Capabilities that Path C reimplemented poorly:

| Capability | Grok Voice API | Path C |
| --- | --- | --- |
| Speech-to-speech | Native | Whisper + CLI + `say` |
| Server VAD / barge-in | `turn_detection.server_vad` | Homegrown RMS / silence timers |
| Audio codecs | PCM / G.711 μ-law / A-law | WebM/opus via MediaRecorder |
| Tools / MCP | First-class in session | Only via full CLI tools |
| Telephony | SIP bridge + Twilio examples | None |
| Latency design | Streaming audio deltas | Full turn then TTS |

Cookbook paths called out by xAI docs:

- WebSocket agent (browser/server)  
- **WebRTC agent**  
- **Telephony agent (Twilio)**  
- SIP: register number → webhook `realtime.call.incoming` → join `wss://api.x.ai/v1/realtime?call_id=…`

Pricing (as of xAI Voice Agent Builder announcement, Jul 2026): ~**$0.05/min audio** + ~**$0.01/min** telephony on free provisioned numbers (verify live pricing before commit).

### 5.2 LiveKit + xAI plugin

LiveKit Agents ships an **xAI RealtimeModel** plugin (`livekit-agents[xai]`).  
This is a production pattern: SFU + agent worker + Grok realtime, with phone numbers available in LiveKit’s ecosystem.

Useful if we want:

- A **web join URL** that always works for mobile browsers  
- Room recording, participants, scaling later  
- Cleaner media than DIY WebRTC  

### 5.3 Voice Agent Builder (no-code)

Console path: telephony, knowledge, tools, MCP, logs.  
Good for **proving audio quality** and phone reachability **before** wiring RC.  
Not a substitute for RC integration — use as **media brain**, then attach control plane.

---

## 6. Option space (evaluated)

Scoring: **Reliability** (principal hears/talks), **RC coupling** (feels “in Rocket.Chat”), **Latency**, **Ops cost**, **Tooling/agency**, **Mobile**.  
Scale 1–5 (higher better). Research judgment, not measured benchmarks.

### Option 0 — Path C: Playwright + public Jitsi + STT/CLI/TTS  
**Status:** Failed in field.

| Rel | RC | Lat | Ops | Tools | Mobile |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 4 | 1 | 2 | 3 | 2 |

**Verdict:** Do not choose for production.

---

### Option 1 — **Recommended primary:** RC **Call** (VideoConf) + **agent-capable SFU** + Grok Voice  
**Hard-requirement compliant.** Keep Rocket.Chat Call as the only principal entry; replace the broken bot media path.

```
Principal: RC app → Call on DM grok
        │ VideoConf start / ring / join (unchanged UX)
        ▼
Rocket.Chat 8.6
        │ provider app generates room URL + callId
        ▼
Media room (LiveKit preferred, or self-hosted Jitsi with real client API)
        │ principal client joins as today (RC embeds / opens provider)
        │
        ▼
Grok media worker joins SAME room as a first-class participant
  • LiveKit Agents + xai.realtime.RealtimeModel  OR
  • lib-jitsi-meet / Jitsi client API (not Playwright DOM)  OR
  • custom WebRTC peer in the provider room
        │
        ▼
Audio: principal ↔ room ↔ Grok Voice (speech-to-speech)
```

**How this differs from Path C (critical):**

| Path C (failed) | Option 1 (target) |
| --- | --- |
| Fake human in browser via Playwright | **Server/agent SDK** participant |
| Virtual mic inject + remote MediaRecorder hacks | Native publish/subscribe tracks |
| Whisper + Grok CLI + `say` | **Grok Voice Agent API** (or LiveKit xAI plugin) |
| Public meet.jit.si DOM | Controlled room (LiveKit or self-hosted Jitsi) |

**RC Apps-Engine path (documented by Rocket.Chat):**  
Implement a custom **VideoConf provider** (`IVideoConfProvider`: `generateUrl`, join lifecycle) the way Jitsi/BBB apps do ([developer docs](https://developer.rocket.chat/docs/video-conferencing-apps)). Point `VideoConf_Default_Provider` at that app. Principal still hits **Call**.

**Why this is the right primary:**

- Satisfies hard requirement: **Call Grok in Rocket.Chat**.  
- Uses production agent media patterns (LiveKit + xAI is published).  
- Does not depend on Chromium automation.  
- Can keep operator `t=videoconf` spawn hook — it starts the **agent worker**, not a browser.

**Tradeoffs / work:**

- Build or host media room (LiveKit Cloud or self-host).  
- Small Apps-Engine provider **or** reconfigure Jitsi domain to self-host and fix bot join method.  
- Mobile must support the provider the same way it supports Jitsi today (prove in R1).

**Sub-variants (same Option 1):**

| 1a | LiveKit room + LiveKit Agent (xAI RealtimeModel) + RC VideoConf provider app | Best reliability / agent story |
| 1b | Self-hosted Jitsi + **lib-jitsi-meet** (or equivalent) bot + Grok Voice audio bridge | Keeps Jitsi brand; still drops Playwright |
| 1c | Custom thin WebRTC room page + RC provider | More DIY than LiveKit |

---

### Option 2 — RC **Team Voice** call to user `grok` (native WebRTC / SIP)  
**Hard-requirement compliant** if the product Call used is Team Voice, not VideoConf.

```
Principal: Team Voice call → user grok
        │ RC signaling (WebRTC or via Drachtio/SIP)
        ▼
Grok answering endpoint
  • SIP UA registered as grok’s extension → Grok Voice (pcmu)  OR
  • Custom WebRTC client that completes RC’s P2P answer (high reverse-engineering risk)
```

| Rel | In-RC Call UX | Lat | Ops | Tools | Mobile |
| --- | ---: | ---: | ---: | ---: | ---: |
| 3–4 | 5 | 4 | 1–2 | 4 | 4 |

**Verdict:** Correct for “native RC voice,” but:

- Docs require **premium + Voice add-on** for Team Voice / SIP.  
- No public “bot answers Team Voice” API — SIP UA is the honest path.  
- FreeSWITCH + Drachtio + TURN is real ops cost.  

**Choose only if** Team Voice is already licensed / preferred over VideoConf Call. Otherwise Option 1 is faster on community VideoConf.

---

### Option 3 — Fix Path C in place (Playwright + public/self-hosted Jitsi + STT/CLI/TTS)  
**Hard-requirement compliant in intent; weak on reliability.**

| Rel | In-RC Call UX | Lat | Ops | Tools | Mobile |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1–2 | 5 | 1 | 2 | 3 | 2 |

**Verdict:** Same entry UX you already tried. May become “hears greeting” with headed debug; unlikely to become **smooth** production. Lab only unless time-boxed and then abandoned.

---

### Option 4 — Self-hosted Jitsi only (no agent SDK, still browser bot)  
Slightly better ops control than meet.jit.si; **does not** fix the bot architecture class. Not sufficient alone.

---

### Option 5 — Standalone Grok phone / Twilio / “Call me” outside RC Call  
**Fails hard requirement** as primary product.

Allowed uses:

- **R0 lab:** Prove Grok Voice audio quality in 30 minutes.  
- **Secondary** convenience line after in-RC Call works.  

Must never be documented as “done” for this goal.

---

### Option 6 — DM deep link only (no Call button)  
**Fails hard requirement** as primary. Useful intermediate demo only.

---

## 7. Recommended technical path (decision)

### Primary recommendation: **Option 1a — Rocket.Chat Call → agent-capable room → Grok Voice**

| Layer | Choice |
| --- | --- |
| **Principal UX** | Rocket.Chat **Call** on DM with `grok` (VideoConf lifecycle) |
| **RC integration** | Keep/extend `videoconf` operator hook; prefer custom or reconfigured **VideoConf provider** |
| **Media room** | **LiveKit** (or equivalent SFU with first-class agent join) |
| **Bot join** | LiveKit **Agent worker** (SDK), **not** Playwright |
| **Brain + voice** | **Grok Voice Agent API** via LiveKit xAI plugin or direct realtime bridge into published audio tracks |
| **Path C** | Demote to lab / forensic only |

### Why this meets the hard requirement *and* reliability

| Requirement | How met |
| --- | --- |
| Voice calls **in Rocket.Chat** | Principal still uses RC Call on DM `grok` |
| Reliable hear/speak | SFU + agent SDK + Grok speech-to-speech (not CLI+say) |
| Mobile | Same class of client path as today’s Jitsi Call (must be verified) |
| Not married to broken stack | Drops Playwright / public meet.jit.si / Whisper bottleneck |
| Operator reuse | Existing `t=videoconf` → spawn worker still applies |

### Explicit non-recommendations (for the *product* goal)

- Shipping a **separate phone number** as the only “Grok voice.”  
- Treating RC as transcript console only.  
- Investing mainline effort in Playwright unmute races.  
- Using full **Grok CLI** as the realtime audio brain.

### Lab-only (allowed, not “done”)

- xAI SIP / Twilio → Grok Voice to validate voices and latency.  
- Headed Path C once, to classify F1/F2.

---

## 8. Target architecture (reference design)

### 8.1 Logical components (hard-requirement compliant)

```
┌─────────────────────────────────────────────────────────────┐
│ Principal: Rocket.Chat mobile/desktop                       │
│   DM with grok → Call                                       │
└────────────────────────────┬────────────────────────────────┘
                             │ VideoConf signaling + open room
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Rocket.Chat 8.6                                             │
│  • VideoConf provider (custom LiveKit app or fixed Jitsi)   │
│  • Operator: t=videoconf → spawn Grok media worker          │
│  • chat status + post-call transcript (optional)            │
└───────────────┬─────────────────────────────┬───────────────┘
                │ join as principal           │ join as agent
                ▼                             ▼
┌──────────────────────────────┐   ┌──────────────────────────┐
│ Media room (LiveKit SFU)     │◄──│ Grok media worker        │
│  principal audio track in    │   │  LiveKit Agent +         │
│  grok audio track out        │   │  Grok Voice Realtime     │
└──────────────────────────────┘   └──────────────────────────┘
```

**Invariant:** Principal never leaves “I called Grok in Rocket.Chat.”  
**Invariant:** Grok never joins via Playwright DOM automation.

### 8.2 Session continuity model

| Session | Owner | Purpose |
| --- | --- | --- |
| **RC text session** | Operator + Grok CLI `--resume` | Deep agency work, code, long tools |
| **Voice realtime session** | Grok Voice / LiveKit agent | Low-latency talk inside the Call |

**Bridge patterns (MVP):** voice agent instructions = agency voice persona; on hangup, optional transcript into DM + optional CLI wake. Do not block realtime audio on Grok CLI.

### 8.3 Minimum viable “reliable call” (MVP definition)

1. Principal presses **Call** on DM `grok` in Rocket.Chat (mobile).  
2. Call connects; principal **hears** Grok greeting within **~3 s** of media up.  
3. Principal says a fixed phrase; Grok replies **out loud** correctly.  
4. Hangup from RC ends the agent session; no zombie Chromium.  
5. **3/3** consecutive mobile calls pass.  
6. No requirement for a separate phone number.

Playwright + Whisper + `say` + full CLI **not** required for MVP (and not recommended).

---

## 9. Phased delivery (research-only roadmap; no code now)

Every phase must preserve **Call in Rocket.Chat** as the test harness unless marked LAB.

| Phase | Outcome | In-RC Call? |
| --- | --- | --- |
| **R0** | Decision freeze: hard requirement = RC Call; brain = Grok Voice; bot = agent SDK | Policy |
| **R1 LAB** | Standalone Grok Voice / LiveKit agent works in browser (proves audio) | No (lab) |
| **R2** | LiveKit (or SFU) room: principal + agent both hear each other | Not yet via RC Call |
| **R3** | RC VideoConf provider (or Jitsi reconfig) opens that room on **Call** | **Yes — first hard-requirement pass** |
| **R4** | Operator spawns agent on `videoconf`; auto-join; greeting; hangup sync | **Yes** |
| **R5** | Mobile 3/3 acceptance; latency + failure status messages | **Yes** |
| **R6** | Tools/MCP / post-call transcript into DM session | **Yes** |
| **R7 optional** | Secondary PSTN line (does not replace R3–R5) | Extra |

**Path C headed debug:** LAB only, not a phase gate for “done.”

---

## 10. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| “Not the green Call button” feels incomplete | Document UX honestly; later custom app button or slash command |
| Canada / free number limits | BYO Twilio (already in ops adjacency) |
| Voice session ≠ CLI agency memory | Explicit bridge pattern; don’t pretend they’re one process |
| Cost per minute | Cap max call length; log usage; short greetings |
| Premium RC Voice temptation | Only if enterprise SIP already required; not for MVP |
| Other session changing RC code | This doc is the media strategy; implement only when that session is free |
| Security of webhooks | Verify xAI/Twilio signatures; keep secrets in `agency/secrets` |

---

## 11. Open questions for the implementation session

1. Prefer **inbound number** (principal dials Grok) vs **outbound click-to-call** (Grok dials principal) for v1?  
2. Is **PSTN** required for v1, or is **mobile browser WebRTC** enough?  
3. Must voice share **live** memory with the current Grok CLI DM session, or is post-call transcript enough?  
4. Is LiveKit acceptable as a dependency, or prefer pure xAI WebRTC/SIP only?  
5. Keep VideoConf Jitsi enabled for **human** conferences while Grok uses a different entry?

---

## 12. References (fetched / observed)

### Local deployment

| Item | Path / fact |
| --- | --- |
| RC image | `rocket.chat:8.6.0` |
| VideoConf | Jitsi default; DM/channel/group/team enabled; mobile ringing on |
| Path C code | `~/.grok/agency/ops/rocketchat/call/rc_call_bot.py` |
| Operator hook | `handle_videoconf_call` / `spawn_call_bot` |
| Failure logs | `~/logs/rocketchat-dm-wake/call-bot.log` (greeting local, short utterances) |
| Twilio adjacency | `~/.grok/agency/ops/twilio/` |

### External (primary)

- [Rocket.Chat Voice via Standard WebRTC](https://docs.rocket.chat/docs/configure-voice-via-standard-webrtc) — P2P; server is signaling only  
- [Rocket.Chat Voice via SIP](https://docs.rocket.chat/docs/configure-voice-via-sip-integration) — Drachtio + FreeSWITCH; premium/add-on  
- [Conference Call / providers](https://docs.rocket.chat/docs/rocketchat-conference-call) — Jitsi et al. are external media  
- [Jitsi app](https://docs.rocket.chat/docs/jitsi-app) — domain/prefix configuration  
- [xAI Voice Agent API](https://docs.x.ai/developers/model-capabilities/audio/voice-agent) — realtime WS, VAD, tools, PCM/G.711  
- [xAI SIP phone calls](https://docs.x.ai/developers/model-capabilities/audio/voice-agent/sip) — `call_id` join, Twilio trunk example  
- [Voice Agent Builder launch](https://x.ai/news/grok-voice-agent-builder) — telephony + tools product framing  
- [LiveKit xAI plugin](https://docs.livekit.io/agents/models/realtime/plugins/xai/) — RealtimeModel agent worker  

### Prior local analysis

- [implementation-plan-voice-calls.md](implementation-plan-voice-calls.md) — Path C fix plan; still useful for **why Path C failed**, superseded here for **production media choice**

---

## 13. Bottom line

1. **Hard requirement:** Voice calls with Grok must work **in Rocket.Chat** (Call / native Team Voice on DM `grok`) — not as a side phone product.  
2. **Hard technical problem:** Media/bot integration under that Call path — Path C used the right *entry* (RC Call) and the wrong *bot media design* (Playwright + Jitsi DOM + CLI TTS).  
3. **Viable path that respects both:**  
   **RC Call → agent-capable room (LiveKit preferred) → Grok Voice Agent as a real participant.**  
   Same Call button; replace the media/bot stack.  
4. **Standalone SIP/Twilio Grok lines** are lab/secondary only; they do **not** complete this goal.  
5. **Path C** = failed prototype; useful for forensics, not the production target.  
6. Next implementation focus (when allowed): **R2–R4** — SFU room + RC Call provider + agent auto-join — measured only by **mobile RC Call** acceptance.

---

*End of research document. No runtime systems were modified for this write-up.*
