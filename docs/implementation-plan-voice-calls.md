# Implementation Plan: Rocket.Chat ↔ Grok voice calls that the principal can actually hear

**Status:** Draft — **partially superseded for production media choice**  
**Created:** 2026-07-10  
**Owner surface (historical):** Path C (`rc_call_bot.py`) first; optional xAI Voice Agent track second  
**Superseding research (recommended path):** [research-voice-media-path.md](research-voice-media-path.md)  
**Canonical runtime:** `~/.grok/agency/ops/rocketchat/`  
**This doc lives in:** `~/IdeaProjects/rocketchat-agents/`

> **2026-07-10 research update:** Production-viable media should use **Grok Voice Agent API** (SIP/WebRTC/LiveKit transports) with Rocket.Chat as **control plane**. Path C (Playwright + public Jitsi) remains a useful failure analysis and optional lab track; it is **not** the recommended production media plane. See the research doc for the decision matrix and target architecture.

---

### Project Title

Make “Call Grok” on Rocket.Chat a real two-way spoken conversation — with **principal-audible audio** as the hard gate, not “bot log says greeting played.”

---

### Overview

Principal expectation: press **Call** in the Rocket.Chat DM with user `grok`, hear Grok join, hear a greeting, speak, and hear spoken replies.

Current system (**Path C**) is a home-built conference bot:

1. Operator sees `t=videoconf` → `spawn_call_bot`  
2. `rc_call_bot.py` calls `video-conference.join` as `grok`  
3. Playwright Chromium opens public **meet.jit.si**  
4. Injected Web Audio virtual mic + remote capture  
5. macOS `say` → ffmpeg → inject TTS; Whisper STT → headless Grok CLI → TTS  

**Evidence that it failed for the principal (not just “flaky”):**

| Observation | Source |
| --- | --- |
| Principal never heard an answer on the phone | User report 2026-07-10 |
| Early attempts only posted text (“no media peer”) | `operator-agent.log` 2026-07-09T21:38–21:41 |
| Later attempts spawned the bot; log claims `played greeting dur=1.6s` | `call-bot.log` 2026-07-09T21:41 and 21:45 |
| No successful STT → Grok → TTS turn in logs | Only `skip short utterance 0.60s` after greeting |
| Hundreds of tiny `call-media/chunk-*.wav` files | Capture path produces noise/silence, not speech |
| Text DM path works; call path has no activity since 2026-07-09 | Operator healthy 2026-07-10; no new call logs |

**Critical distinction:** xAI’s public **Voice Agent Builder** (phone numbers, native Grok voice, tools) proves Grok-as-phone-agent is product-real. It is **not** what Rocket.Chat Call currently uses. Conflating the two caused false confidence.

This plan prioritizes **hearing the agent on the principal’s device**. Server-side “greeting duration 1.6s” without that is a failed acceptance test.

---

### Key Themes Alignment

Drawn from existing agency / RC docs:

- **Transport honesty** — Rocket.Chat is a channel; do not claim telephony where we only have Jitsi WebRTC (`call/README.md` already states this).
- **Principal-only wake** — Call handling already gates on principal username; keep that.
- **One durable answer path** — Voice turns should resume the same room Grok session as text DM (already intended via `wake_lib` session pins).
- **No fake “fixed”** — Log lines that claim audio played do not count until the principal hears it (`NO_DUPLICATE_POSTS.md` spirit: durable proof, not verbal claims).
- **Evidence before scale** — Instrument and prove one full duplex turn before optimizing latency or multi-call.

---

### Objectives

**Primary Objective**  
Within one live DM Call from the principal’s phone, the principal **hears** Grok’s greeting and at least one spoken reply to something they said, with matching entries in `call-bot.log` (transcript + reply).

**Secondary Objectives**

- Prove whether failure is **outbound** (TTS never reaches remote peer), **inbound** (STT never gets speech), or **join/room** (bot not in the same conference the phone joined).
- Add an operator-visible **call health checklist** in logs (peer present, remote tracks, mic unmuted, play duration, RMS of outbound probe).
- Document go / no-go for Path C vs switching voice to xAI Voice Agent / Twilio.
- Keep text DM and channel operator behavior unchanged.

---

### Success Metrics

**Quantitative (must all pass in one test call)**

| Metric | Pass criteria |
| --- | --- |
| Join | RC `video-conference` status shows `grok` as participant while principal is connected |
| Outbound audio | Principal reports hearing greeting **or** a recorded remote capture of greeting ≥ 0.8 s speech |
| Inbound audio | `call-bot.log` shows `turn N transcript=` with ≥ 3 words matching what principal said |
| Reply | Principal hears spoken reply; log shows `turn N reply=` non-empty |
| End | Call ends cleanly (`call bot finished` or goodbye); lock file cleared |
| No false green | Unit/integration tests that only mock `played greeting` **cannot** be the sole gate |

**Qualitative**

- Principal no longer needs to ask “did it work?” — chat status messages match what they heard.
- Headed debug mode can show Chromium Jitsi UI with Grok unmuted.
- Latency for first reply is documented (target: under 15 s for MVP; under 8 s stretch — not blocking MVP).

**Validation**

- Manual acceptance script (below) signed off once with timestamp + log excerpts.
- Existing `test_videoconf_spawns_call_bot` still passes; new audio-path tests added where automatable.

---

### Mathematical / Theoretical Foundations (if applicable)

Not applicable as pure math. Signal-path invariants that must hold:

1. **Same conference identity:**  
   `RC callId → join URL room name → Chromium Jitsi room ≡ principal client room`.
2. **Outbound chain:**  
   `TTS wav → decodeAudioData → MediaStreamDestination → getUserMedia override track → Jitsi local audio → WebRTC → principal speaker`.
3. **Inbound chain:**  
   `Principal mic → WebRTC remote track → __grokRemoteMix → MediaRecorder → Whisper → Grok → TTS (chain 2)`.
4. **VAD gate:**  
   utterance accepted only if `duration ≥ MIN_SPEECH_S` (default 0.8) and chunk RMS ≥ `RMS_SPEECH` (default 0.012).  
   Current failures often look like duration ≈ `LISTEN_CHUNK_S` (0.6 s) → always skipped when only one short chunk aggregates.

Any break in (1)–(3) explains “log success, ear silence.” Gate (4) alone cannot explain never hearing the greeting.

---

### Assumptions and Priors

Verified or strongly evidenced:

- Operator WebSocket path is live and handles text wakes (`operator-agent.log` 2026-07-10).
- Path C code exists and is wired: `handle_videoconf_call` → `spawn_call_bot` → `rc_call_bot.py` (with unit test `test_videoconf_spawns_call_bot`).
- Jitsi app / VideoConf settings were enabled via `enable_conference_calls.sh` (Call button works enough to ring).
- Bot process has at least once joined meet.jit.si and executed greeting playback locally (log `played greeting dur=1.6s`).
- STT loop did not complete a real turn (only short-utterance skips).
- Public meet.jit.si requires Mac internet; Mac must be awake for Chromium bot.
- Native xAI Voice Agent is a separate product surface (video 2026-07-07, Eric Michaud walkthrough of builder + free/US number + tools).

Open / not yet verified:

- Whether Chromium’s virtual mic track is actually selected as the **sent** Jitsi track after join.
- Whether principal and bot land in the **same** Jitsi room name (URL rewrite / domain / tenant prefix).
- Whether mobile RC client plays remote Jitsi audio when bot has no video (audio-only).
- Playwright version / Chromium permissions stability after OS sleep.

---

### Novel Hypotheses

Ranked by how well they explain **principal never heard anything** while logs claim greeting played:

| ID | Hypothesis | Supporting observation |
| --- | --- | --- |
| H1 | **Outbound WebRTC never carries TTS** — play into Web Audio dest succeeds locally (`dur=1.6s`) but Jitsi holds a different/muted track | Greeting log without user hearing; `play_wav_in_page` only measures decode duration, not remote receipt |
| H2 | **Bot and principal not in the same media room** — RC join URL vs phone client diverge | Possible if join returns URL principal never used; needs side-by-side URL compare |
| H3 | **Local mute / prejoin race** — force-unmute runs before conference object ready | Join clicks + `__grokForceUnmute` best-effort; no hard assert on “mic is sending” |
| H4 | **Inbound path broken separately** — even if greeting were fixed, RMS/duration gates discard speech | `skip short utterance 0.60s`; chunk files ~19 KB noise |
| H5 | **Mobile client UX** — call UI stays on “ringing” and never attaches remote audio despite bot join | Early “no media peer” era; still possible if join API succeeds but client UI stuck |

MVP work orders hypotheses: **H2 → H1 → H3** (must hear greeting), then **H4** (conversation), then polish.

---

### Implementation Phases

#### Phase 0: Reproduce, instrument, decide go/no-go for Path C

**Goal:** One instrumented call attempt with headed Chromium and a written failure classification.

**Tasks**

- Run Call with `RC_CALL_HEADLESS=0` so Chromium is visible on the Mac.
- Log and retain for each attempt: full join URL, `call_info` users/status, `__grokDiag()` every 2 s for 30 s after join, whether `APP.conference.isLocalAudioMuted()` is false.
- Compare principal-side conference URL (from phone/desktop RC) with bot join URL (character-level).
- Capture 10 s of **outbound** probe tone (known 440 Hz) and ask principal if they hear a tone (binary test).
- Save run notes under `~/logs/rocketchat-dm-wake/call-runs/YYYYMMDD-HHMM.md`.

**Deliverables**

- `docs/call-debug-runbook.md` (or section in ops) with exact env flags and checklist.
- One classified result: H1 / H2 / H3 / other.

**Estimated effort:** 0.5–1 day  

**Validation:** Without a classified failure, do not change production logic beyond logging.

---

#### Phase 1: Principal hears Grok (outbound audio only)

**Goal:** Fix the chain until the principal hears *“Hello, Grok speaking.”* (or equivalent) every time.

**Tasks**

- Assert same-room identity (H2): refuse to claim success if principal username not in `call_info.users` after join; re-fetch join URL if needed.
- Outbound proof (H1): after TTS, verify Jitsi local audio stats / track enabled / not muted; optional Opus level meter.
- Prefer robust inject path if Web Audio dest is flaky:
  - try Jitsi `APP.conference` replace track APIs if available in current meet.jit.si build, **or**
  - file-based virtual device (BlackHole) only if Web Audio path fails headed tests (heavier ops cost — last resort).
- Raise greeting volume / remove sub-audible carrier issues if they confuse AGC.
- Chat status only after **outbound health check** passes (not merely `play` duration > 0).
- Optionally record remote mix for a self-loop test (bot hears its own playout only if Jitsi loops — do not rely on that alone).

**Deliverables**

- Patches to `rc_call_bot.py` (+ init script) with explicit `outbound_ok=true/false` log lines.
- Acceptance: 3/3 consecutive calls where principal confirms greeting heard.

**Estimated effort:** 1–3 days depending on H1 vs H2  

**Validation:** Principal verbal confirm + log excerpt; no STT required yet.

---

#### Phase 2: Principal is heard (inbound STT)

**Goal:** One accurate transcript of a spoken sentence during a live call.

**Tasks**

- Fix remote track attachment (RTCPeerConnection hook timing vs Jitsi load order).
- Revisit VAD: `MIN_SPEECH_S`, `LISTEN_CHUNK_S`, `RMS_SPEECH`; log RMS every chunk when `RC_CALL_DEBUG=1`.
- Manual test: principal says a fixed phrase (“Schedule a test for Tuesday at nine”).
- Whisper path: confirm `whisper` binary and model available to the bot’s PATH (same as operator spawn env).
- On empty remote tracks for > N seconds, post chat: “I joined but cannot hear you yet” (honest UX).

**Deliverables**

- `turn N transcript='...'` matching the fixed phrase.
- Debug flag docs for RMS/threshold tuning.

**Estimated effort:** 1–2 days  

**Validation:** Transcript match ≥ content words of the fixed phrase.

---

#### Phase 3: Full duplex conversation loop

**Goal:** Greeting + one Q&A + optional goodbye hangup.

**Tasks**

- Wire STT → `wake_voice_turn` (already present) with short voice system prompt (“answer aloud in ≤ 3 sentences”).
- Cap Grok CLI turn budget for voice (`max-turns` / prompt) to reduce latency.
- Speak reply; confirm principal hears it.
- Goodbye / hangup path already sketched — verify.
- Single-call lock behavior already present — document busy message on second call.

**Deliverables**

- End-to-end Path C MVP that matches `message-flow.md` Path C description **as experienced by the principal**.
- Latency note: time from end of speech to start of reply (log timestamps).

**Estimated effort:** 1–2 days  

**Validation:** Scripted 60–90 s call: greeting, one question, one answer, goodbye.

---

#### Phase 4: Ops hardening and documentation sync

**Goal:** Path C is operable, not a one-off debug miracle.

**Tasks**

- Update `call/README.md`, `docs/message-flow.md`, `docs/operations.md` with real status (works / known limits).
- Add launchd or env defaults only if needed; prefer env flags over new daemons.
- Log retention for `call-media/` (ties to IMP-08 prune patterns).
- Regression: `tests/test_usability_contracts.py` still green; add contract tests for “videoconf does not text-wake” and “spawn posts Answering… only when spawn succeeds.”
- Change chat copy so it never promises hearing the greeting until Phase 1 health check is green.

**Deliverables**

- Docs + small tests; CHANGELOG entry in this docs repo.

**Estimated effort:** 0.5–1 day  

**Validation:** Fresh session can follow runbook without reading source.

---

#### Phase 5 (optional parallel track): xAI Voice Agent as reliable voice channel

**Goal:** If Path C remains blocked by meet.jit.si / mobile WebRTC, ship **voice that works** via native Grok telephony without pretending it is the RC Call button.

**Tasks**

- Evaluate xAI Voice Agent Builder (account, region for free numbers, Twilio BYO if Canada).
- Define integration with agency:
  - **Voice brain:** native Grok voice agent with calendar / knowledge tools as needed.
  - **RC bridge (optional):** post call summary or “call completed” into DM as `grok`.
- Explicit product rule: **RC Call button ≠ phone line** until a true SIP/WebRTC bridge exists.
- Only after Path C go/no-go: avoid splitting effort mid-debug.

**Deliverables**

- Short ADR: “Voice primary channel = Path C | xAI phone | hybrid”.
- If hybrid: one Twilio number + RC text notification script.

**Estimated effort:** 2–5 days product/ops  

**Validation:** Principal places a real PSTN/SIP call and hears Grok (matches the public demo’s capability class).

---

### Tools and Technologies

| Area | Current stack (Path C) |
| --- | --- |
| Languages | Python 3.13, injected browser JS |
| RC API | REST login, `video-conference.join` / info / leave |
| Conference | Rocket.Chat VideoConf → Jitsi app → **meet.jit.si** |
| Browser | Playwright Chromium (`RC_CALL_HEADLESS`) |
| TTS | macOS `say` (`RC_CALL_SAY_VOICE`, default Ava) + ffmpeg |
| STT | local Whisper (`RC_WHISPER_*`) |
| Brain | Grok CLI (`GROK_BIN`, same session pins as text) |
| Orchestration | `rc_operator_agent.py` spawn + lock file |
| Logs | `~/logs/rocketchat-dm-wake/call-bot.log`, `call-bot.spawn.log`, `call-media/` |
| Tests | `~/.grok/agency/ops/rocketchat/tests/test_usability_contracts.py` |

**Build / test commands (from runtime tree):**

```bash
# Usability / contract tests (includes videoconf spawn test)
python3 ~/.grok/agency/ops/rocketchat/tests/test_usability_contracts.py

# Manual bot (needs live callId from a ringing Call)
RC_CALL_HEADLESS=0 python3 ~/.grok/agency/ops/rocketchat/call/rc_call_bot.py \
  --call-id <id> --room-id <dm-rid>
```

**Benchmarking approach:** wall-clock timestamps in `call-bot.log` for join → greeting → transcript → reply start; no synthetic load tests until Phase 3 passes once.

**Documentation standards:** update both live runbook (`~/.grok/agency/ops/ROCKETCHAT.md` / `call/README.md`) and this docs project when behavior changes.

---

### Validation and Testing Strategy

**Unit / Integration**

- Keep `test_videoconf_spawns_call_bot` (spawn, no text wake).
- Add pure tests for: VAD accept/reject thresholds on fixture wavs; join URL rewrite helpers; “do not post Answering if spawn false.”
- Do **not** claim E2E audio in unit tests without real WebRTC (false confidence).

**Manual / Acceptance (Phase gates)**

| Gate | Procedure | Pass |
| --- | --- | --- |
| G0 | Headed join + URL match | Bot visible in conference; URLs match |
| G1 | Greeting | Principal hears greeting 3/3 |
| G2 | Transcript | Fixed phrase appears in log |
| G3 | Reply | Principal hears answer to that phrase |
| G4 | Hangup | Clean end; lock cleared |

**Static analysis**

- No new broad dependency if avoidable; Playwright already required for Path C.

**Failure policy**

- If G1 fails after Phase 1 budget: stop Path C feature work; complete Phase 5 ADR and route principal voice to xAI/Twilio rather than shipping a silent bot.

---

### Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| meet.jit.si / Jitsi DOM changes break inject | High | Call silent again | Version-pin diagnostics; Phase 5 fallback |
| Mobile RC never plays remote audio-only peers | Medium | Desktop works, phone fails | Test both clients in Phase 1; document supported clients |
| Headless Chromium audio policy differs from headed | High | “Works in debug, fails in prod” | Default debug headed until G1 green; then re-test headless |
| Whisper / `say` / ffmpeg missing on spawn PATH | Medium | STT/TTS fail after join | Spawn env already extends PATH; add preflight check at bot start |
| Full Grok CLI too slow for voice | High | Unusable latency | Voice-specific short prompt + lower max-turns; later native voice API |
| Effort split between Path C and xAI builder | Medium | Neither finishes | Serial: Path C through G1 or explicit no-go, then Phase 5 |
| Concurrent call lock confuses principal | Low | Second call ignored | Clear chat message (already partial) |
| Logging “played greeting” trains false trust | High | Repeated user frustration | Rename metric to `tts_local_play_s`; require `outbound_health=ok` |

---

### Timeline

| Milestone | Target | Dependencies | Status |
| --- | --- | --- | --- |
| Phase 0: classify failure (H1–H5) | Day 1 | Operator up, Mac awake, phone on RC | [ ] |
| Phase 1: principal hears greeting (G1) | Days 1–3 | Phase 0 | [ ] |
| Phase 2: transcript works (G2) | Days 3–5 | Phase 1 | [ ] |
| Phase 3: full duplex MVP (G3–G4) | Days 5–7 | Phase 2 | [ ] |
| Phase 4: docs + ops hardening | Day 7–8 | Phase 3 or documented no-go | [ ] |
| Phase 5 ADR / xAI path (if needed) | Parallel after G1 no-go or post-MVP | Account access to xAI voice builder | [ ] |

Estimates assume one engineer familiar with this Mac’s agency stack; WebRTC surprises can double Phase 1.

---

### References and Resources

**Repo / runtime files examined**

| Path | Role |
| --- | --- |
| `~/IdeaProjects/rocketchat-agents/docs/message-flow.md` | Path A/B/C documentation |
| `~/IdeaProjects/rocketchat-agents/docs/related-systems.md` | Twilio adjacent, not RC voice |
| `~/.grok/agency/ops/rocketchat/call/README.md` | Path C design + limits |
| `~/.grok/agency/ops/rocketchat/call/rc_call_bot.py` | Join, Playwright, VAD, STT/TTS loop |
| `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` | `spawn_call_bot`, `handle_videoconf_call` |
| `~/.grok/agency/ops/rocketchat/wake/wake_lib.py` | `is_videoconf_message`, `videoconf_call_id` |
| `~/.grok/agency/ops/rocketchat/enable_conference_calls.sh` | Jitsi VideoConf enablement |
| `~/.grok/agency/ops/rocketchat/tests/test_usability_contracts.py` | `test_videoconf_spawns_call_bot` |
| `~/logs/rocketchat-dm-wake/call-bot.log` | Greeting play + short utterance skips |
| `~/logs/rocketchat-dm-wake/operator-agent.log` | Spawn / busy / early no-media |

**External**

- YouTube walkthrough of xAI Voice Agent Builder (native phone agents, calendar tools, free US number caveats): https://youtu.be/7lpdObaZT2Q — useful as **existence proof for Grok telephony**, not as a drop-in for RC Jitsi Path C.

**Related backlog**

- Improvements package `docs/improvements/` is mostly operator safety/scale, not voice media; this plan is a **separate vertical** until Path C is proven.

---

### Explicit non-goals (for this plan)

- Replacing text DM with voice.
- Multi-party conference facilitation.
- Pixel-perfect low latency equal to Grok iOS native speak mode (Path C will remain higher latency).
- Shipping “Answering…” chat promises without G1.

---

### Recommended first action

Run **Phase 0** on the next free 30 minutes with the phone:

1. Ensure operator is running and Mac is awake.  
2. `RC_CALL_HEADLESS=0` for the bot (env on spawn or temporary operator env).  
3. Call `grok` from the phone; leave the call up ≥ 45 s after ring stops.  
4. Watch Chromium: is Grok in the room, unmuted?  
5. Compare join URLs; save logs to `call-runs/`.  
6. Binary question: **Did you hear any greeting or tone?**  
   - Yes → Phase 2 focus.  
   - No → Phase 1 only (do not tune Whisper yet).

---

*End of implementation plan.*
