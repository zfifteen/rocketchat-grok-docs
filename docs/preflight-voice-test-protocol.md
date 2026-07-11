# Pre-principal voice test protocol

**Purpose:** Validate (or falsify) Rocket.Chat ↔ Grok voice **before the principal has to pick up a live call**.  
**Hard requirement:** Final acceptance still requires **Call in Rocket.Chat** on mobile — but most failure modes can be found earlier.  
**Status:** Protocol active; **T2 PASS + criterion3 PASS** (re-verified 2026-07-11 evening) on lobby-free voice room path (RC Call VideoConf → `http://LAN:8090/Agency{callId}`).  
**Principal T5:** **READY** — operator + voice-room up; phone on same Wi‑Fi as Mac (`10.71.11.69`).

Related: [research-voice-media-path.md](research-voice-media-path.md), [implementation-plan-voice-calls.md](implementation-plan-voice-calls.md)

---

## 1. Test ladder (who runs what)

| Layer | What it proves | Who runs | Blocks principal? |
| --- | ---: | --- | --- |
| **T0** | Stack up: RC healthy, operator running, deps present | Agent | No |
| **T1** | VideoConf API: start/join as `grok` + `principal` | Agent | No |
| **T2** | Dual-browser media: simulated principal **hears** simulated Grok tone over provider room | Agent | No |
| **T3** | Path C bot greeting energy (optional lab) | Agent | No |
| **T4** | Grok Voice API lab (speech quality only — not “in RC”) | Agent | No |
| **T5** | **Final acceptance:** principal Call on mobile RC | **You** | Yes — only after T2 green on chosen stack |

**Rule:** Do not ask the principal to do T5 until **T2 passes** on the media stack under test.

---

## 2. What was already run (2026-07-11)

### T0 — Stack up — **PASS**

| Check | Result |
| --- | --- |
| Docker `agency-rocketchat-rocketchat-1` | healthy |
| Mongo | healthy |
| Operator launchd | running |
| `whisper`, `ffmpeg`, `say`, Grok CLI | present |
| Playwright Chromium | available |
| `XAI_API_KEY` in environment | present (name only; not printed) |

### T1 — VideoConf API — **PASS**

| Step | Result |
| --- | --- |
| Login `grok` / `principal` | success |
| `video-conference.providers` | `jitsi` only |
| `video-conference.start` on principal↔grok DM | `callId` issued, provider `jitsi` |
| `video-conference.join` as `grok` | join URL `https://meet.jit.si/Agency{callId}...` |
| `video-conference.info` | `grok` listed in `users` |

**Conclusion:** Rocket.Chat **signaling** for Call is fine. The break is not “Call button doesn’t create a conference.”

### T2 — Dual-peer Jitsi audio — **FAIL** (critical)

**Tool:** [`docs/tools/preflight_dual_peer_jitsi_audio.py`](tools/preflight_dual_peer_jitsi_audio.py)

**Method (no human phone):**

1. API-start a VideoConf on principal↔grok DM.  
2. Open **two** Playwright Chromium contexts on the same meet.jit.si room.  
3. Modes: **inject** (Path C Web Audio mic) and **fake** (Chromium fake device GUM).  
4. Settle 15 s, force unmute via `APP.conference`, record remote RMS.  
5. Screenshots under `~/logs/rocketchat-dm-wake/preflight/`.

**Result (report):** `~/logs/rocketchat-dm-wake/preflight/dual-peer-report.json`  
**Runs:** 2026-07-11 initial + deep T2 (inject+fake).

| Metric | inject | fake |
| --- | --- | --- |
| Local mic/track live on Grok peer | yes (MediaStreamAudioDestination) | yes (Fake Default Audio Input) |
| `APP.conference` present / unmute attempted | yes | yes |
| Remote RMS at principal | **0.0** | **0.0** |
| Exit | **FAIL** | **FAIL** |

#### Root cause (screenshot-proven) — public Jitsi **lobby / no moderator**

Both peers land on meet.jit.si UI:

> **“The conference has not yet started because no moderators have yet arrived.”**  
> “Asking to join meeting…” / “Configuring devices…”

| Peer screenshot | State |
| --- | --- |
| `principal-inject.png` | Lobby; waiting for moderator |
| `grok-inject.png` | Lobby; waiting for moderator |

So **WebRTC media never starts**. Local TTS/tone can still “play” into a virtual mic (matches Path C `played greeting dur=1.6s`) while the other party hears **nothing**.

#### Jitsi app config on this workspace (API read)

| Setting | Value |
| --- | --- |
| `jitsi_domain` | `meet.jit.si` (public) |
| `jitsi_auth_token` | **false** |
| `jitsi_application_id` / `secret` | **empty** |
| JWT / JaaS | off |

Without token auth + moderator claims (or a self-hosted Jitsi with lobby off), **Path C cannot complete a conference** on public meet.jit.si. This is a **structural** block, not only a flaky inject bug.

**Interpretation for your silent phone:** same class — Call signaling works; media room never truly opens for the bot peer (and often not for usable duplex).

---

## 3. How to re-run T2 (agent or later session)

```bash
# Headless (default)
python3 ~/IdeaProjects/rocketchat-grok-docs/docs/tools/preflight_dual_peer_jitsi_audio.py

# Watch browsers
python3 ~/IdeaProjects/rocketchat-grok-docs/docs/tools/preflight_dual_peer_jitsi_audio.py --headed

# Reuse a URL
python3 ~/IdeaProjects/rocketchat-grok-docs/docs/tools/preflight_dual_peer_jitsi_audio.py \
  --join-url 'https://meet.jit.si/Agency…'
```

**Pass criterion:** `ok: true` and `remote_rms >= 0.008` (env `RC_PREFLIGHT_RMS_OK` overrides threshold).

**On FAIL:** do not schedule principal T5 on this stack; fix media (or switch to LiveKit agent path) first.

---

## 4. T3 — Optional Path C bot smoke (still no human)

Only useful after T2 is green or to confirm bot process wiring:

```bash
# Requires a live callId from T1 start/join
python3 ~/.grok/agency/ops/rocketchat/call/rc_call_bot.py \
  --call-id <callId> \
  --room-id 6a4f92351fe46bdff6c54ce6aJRdBYykszJiTGd7g \
  --room-name dm:principal
```

With dual-peer principal browser open, watch for remote energy. Prefer T2 over manual T3.

---

## 5. T4 — Grok Voice lab (optional quality proof)

Does **not** satisfy hard requirement alone. Proves speech-to-speech quality if implementing Option 1a (LiveKit + Grok Voice).

- Use xAI cookbook WebRTC/WebSocket agent with `XAI_API_KEY`.  
- Pass = you hear natural duplex in a browser page.  
- Then wire that agent into the **same room RC Call opens** (T2-equivalent on LiveKit).

---

## 6. T5 — Principal acceptance (only when T2 green)

You run this last:

1. Mac awake; operator running; RC open on phone.  
2. DM `grok` → **Call**.  
3. Stay connected ≥ 45 s.  
4. Checklist:

| # | Question | Pass |
| --- | --- | --- |
| 1 | Did ring stop / call connect? | |
| 2 | Did you hear Grok’s greeting? | |
| 3 | Did Grok answer something you said? | |
| 4 | Hangup clean? | |

**3/3 calls** required for “done.”

Agent support during T5 (if you want): watch `operator-agent.log` + `call-bot.log` / agent worker logs in parallel; you still own the ear test.

---

## 7. Mapping to recommended architecture

| Stack | T2 means | Principal T5 when |
| --- | --- | --- |
| Path C (Playwright + meet.jit.si) | Dual Chromium tone test (current tool) | T2 PASS only |
| LiveKit + Grok Voice agent | Dual join: human-sim browser + agent worker; measure remote RMS / transcript | T2 PASS on LiveKit room, then RC Call provider points at that room |
| Team Voice + SIP UA | SIP softphone as principal + SIP UA as grok | SIP path T2 equivalent |

Current evidence says: **do not spend principal time on Path C T5.**

---

## 8. Agent checklist before asking you to Call

- [x] T0 pass  
- [x] T1 pass  
- [x] T2 **FAIL** on public meet.jit.si (lobby) documented  
- [x] Media path retargeted to lobby-free **voice_room** (`:8090`)  
- [x] T2 re-run **PASS** (`remote_rms ≈ 0.28` ≥ 0.008)  
- [x] Criterion3 **honest media**: `join room … name=Grok` in voice-room.log + principal remote RMS ≥ 0.008 while bot greets (`media_ok=1`)  
- [x] Bot prefer_loopback nav + refuse greeting until localReady/selfId  
- [x] Operator launchd `PYTHON_BIN` → rocketchat `.venv` (playwright)  
- [x] Invite principal **T5**

---

## 9. Artifacts

| Artifact | Path |
| --- | --- |
| Dual-peer probe script | `docs/tools/preflight_dual_peer_jitsi_audio.py` |
| Latest report | `~/logs/rocketchat-dm-wake/preflight/dual-peer-report.json` |
| Tone / capture | `~/logs/rocketchat-dm-wake/preflight/` |
| Voice room server | `~/.grok/agency/ops/rocketchat/voice_room/` |
| Call media bot | `~/.grok/agency/ops/rocketchat/call/rc_call_bot.py` |

---

## 10. Bottom line for you

**Ready for your Call test (T5).**  

Verified just before invite:

1. RC Call **API works** (T1) — join URL is `http://10.71.11.69:8090/Agency{callId}` (not public meet.jit.si).  
2. Dual-peer media **PASS** (T2): remote RMS ~0.28 on voice room.  
3. Live bot **join + “Hello, Grok speaking.”** without FATAL (criterion3).  
4. Services: RC healthy, operator launchd, voice_room launchd (single instance), Mac LAN `10.71.11.69`.

**How to test:** same Wi‑Fi as the Mac → DM `grok` → **Call** → wait for greeting → speak after it.

When T2 is green on a chosen stack, **then** your Call is the final gate (T5).

---

*Docs/tools only; operator config left to the other session.*
