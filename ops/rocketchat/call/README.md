# Rocket.Chat Call media (NF-SPEC-01 + Path C lab)

Principal **Call grok** on phone/desktop. Media backend is selected by flag.

## Backend selection

| `RC_CALL_MEDIA_BACKEND` | Worker | Brain |
|--------------------------|--------|--------|
| `livekit` (production target) | `voice_agent_worker.py` | Grok Voice Agent / Realtime (not Whisper+CLI primary) |
| `playwright` (default pre-cutover, **lab**) | `rc_call_bot.py` | Path C: Playwright + Whisper + Grok CLI + TTS |

## Flow (LiveKit)

1. Principal presses **Call** on DM `grok`.
2. Operator sees `t=videoconf` → `select_spawn_plan` → spawns voice agent when backend=`livekit`.
3. Worker mints short-lived LiveKit JWT for room `Agency{callId}`, joins SFU as `grok`.
4. Speech-to-speech via xAI Realtime; sparse DM status only (connecting/failed/ended).
5. Hangup / max / idle → worker exits; call lock released.

## Flow (Path C lab)

1. Principal presses **Call** on DM `grok`.
2. Operator spawns `rc_call_bot.py` when backend=`playwright`.
3. Bot: `video-conference.join` + Chromium + TTS greeting + Whisper/CLI/TTS loop.

## Files

| File | Role |
|------|------|
| `rc_call_media.py` | Pure backend/lock/token/worker contracts |
| `voice_agent_worker.py` | LiveKit + Voice Agent worker |
| `run_voice_agent.sh` | LiveKit worker wrapper |
| `rc_call_bot.py` | Path C Playwright lab bot |
| `run_call_bot.sh` | Path C wrapper |
| Operator hook | `wake/rc_operator_agent.py` → `handle_videoconf_call` |

## Env

| Var | Default | Meaning |
|-----|---------|---------|
| `RC_CALL_GREETING` | `Hello, Grok speaking.` | Opening line |
| `RC_CALL_SAY_VOICE` | `Samantha` | macOS `say` voice (Ava is Premium-only) |
| `RC_CALL_HEADLESS` | `1` | `0` to watch Chromium |
| `RC_CALL_MAX_S` | `900` | Max call length |
| `RC_WHISPER_MODEL` | `base` | STT model |

## Logs

- `~/logs/rocketchat-dm-wake/call-bot.log`
- `~/logs/rocketchat-dm-wake/call-bot.spawn.log`
- `~/logs/rocketchat-dm-wake/call-media/` (wav chunks)

## Limits (honest)

- **Media plane (2026-07-12):** RC VideoConf still uses the Jitsi *provider app*, but the
  domain is retargeted to the lobby-free **voice room** on this Mac
  (`voice_room/` → `0.0.0.0:8090`, launchd `com.velocityworks.rocketchat-voice-room`).
  **Phone join URL (required):** `https://velocityworks-rc.ngrok.app/Agency{callId}`
  via `public_proxy.py` (ngrok → :9080 → voice `/Agency*` + `/ws`, else RC :3000).
  `jitsi_ssl=true`. Plain `http://<LAN-IP>:8090` is **not** phone-media-safe (iOS has no
  `mediaDevices` outside a secure context) — that was the repeated false-green.
  Lab-only LAN HTTP: `RC_VOICE_JITSI_MODE=lan` (fails `validate_phone_voice_path.py`).
  Media bot may still use loopback for pure-LAN lab URLs; public HTTPS join is left alone.
- Mac + ngrok + public proxy + voice room must be up. Phone no longer needs same Wi‑Fi
  for *signaling* (HTTPS public host); WebRTC media still benefits from LAN/STUN.
- Latency is higher than native Grok iOS speaking mode (STT + full Grok turn + TTS).
- One concurrent call (lock file). A **new** Call supersedes a prior lock holder so
  “busy” does not stick after a hung worker. No-peer timeout
  (`RC_CALL_NO_PEER_TIMEOUT_S`, default 90s) frees the lock if the phone never joins media.
- Not a SIP/Twilio phone line.

## Preflight (bot / dual-peer — NOT phone media)

```bash
python3 ~/IdeaProjects/rocketchat-grok-docs/docs/tools/preflight_dual_peer_jitsi_audio.py
# expect RESULT: PASS and remote_rms >= 0.008
# This only proves Mac Chromium + voice room mesh audio. It does NOT prove iPhone mic.
```

## Phone media gate (fail-closed — required before claiming Call fixed)

iOS WebView needs a **browser secure context** for `navigator.mediaDevices.getUserMedia`.
`http://<LAN-IP>:8090/...` is **not** secure → mic dies with TypeError / mediaDevices undefined.
Bot path rewrites to `http://127.0.0.1` (secure on desktop only). That split caused false greens.

```bash
# Must print PHONE_VOICE_PATH: PASS before claiming voice Call works on the phone.
python3 ~/.grok/agency/ops/rocketchat/call/validate_phone_voice_path.py
python3 ~/.grok/agency/ops/rocketchat/call/validate_phone_voice_path.py --json

# Unit contracts (HTTP LAN must FAIL phone media gate):
python3 ~/.grok/agency/ops/rocketchat/tests/test_phone_voice_path.py
```

Policy: **do not claim Call/voice fixed** unless `PHONE_VOICE_PATH: PASS` and a human
phone Call confirms two-way audio. Bot greet + dual-peer preflight alone are insufficient.

## Manual test

```bash
# After operator is running AND phone gate is PASS, Call grok from the phone app.
# Or dry-run join + browser (needs a live callId):
python3 ~/.grok/agency/ops/rocketchat/call/rc_call_bot.py \
  --call-id <id> --room-id <dm-rid>
```
