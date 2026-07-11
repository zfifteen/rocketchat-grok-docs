# Message flow

**Last reviewed:** 2026-07-10

---

## A. Normal text (DM or joined channel)

1. **Principal** sends a message in a room the operator watches  
   (DM with `grok`, or a channel/group `grok` has joined).
2. **Rocket.Chat** delivers an event over the operator WebSocket  
   (`rc_operator_agent.py`).
3. Operator **filters** (principal-only, not self, not already handled).
4. Operator posts **`Thinking...`** as `grok` in that room  
   (single message id reserved for the answer).
5. Operator builds a wake package:
   - inject from `reply_prompt.txt` + room metadata  
   - resolve **cwd** (DM → agency; channel → IdeaProjects slug / override)  
   - spawn **Grok CLI** with `--cwd`, often `--resume` for same room  
   - Grok writes the **final answer to a reply file** (not direct RC API for text).
6. Operator **`chat.update`s** the Thinking… message with the final answer only.  
   **No second bubble.**
7. Optional: Grok may shell out to `rc_post_media.py` for images/files  
   (ledgered; one confirm only).

### Same-room continuity

Same RC room → same Grok session resume key so conversation context sticks.
Cwd pins can also live in `wake/state.json`.

### Membership refresh

Operator re-scans joined rooms roughly every **60s** (`RC_ROOM_REFRESH_S`) so
newly created channels (after invite) get subscriptions and short unread catch-up.

---

## B. Voice note (Path A)

1. Principal attaches audio (or voice note) in **DM → grok**.
2. Operator downloads media → cache under `~/logs/rocketchat-dm-wake/audio/`.
3. **Whisper** (local CLI) transcribes; optional caption kept.
4. Transcript labeled (e.g. `[Voice note transcript]`) and enters the **same**
   text wake path as A.
5. Reply remains **text** in the Thinking… → update bubble.

Env: `RC_WHISPER_BIN`, `RC_WHISPER_MODEL`, `RC_WHISPER_LANGUAGE`, `RC_STT_TIMEOUT_S`.

---

## C. Conference call (Path C)

1. Principal hits **Call** in DM (Jitsi VideoConf enabled).
2. Operator notices join / call signal; may post chat notice (“Answering…”).
3. **`rc_call_bot.py`** joins as `grok` (Chromium + Jitsi path).
4. TTS greeting (e.g. “Hello, Grok speaking.”).
5. Loop: STT → headless Grok → TTS until hangup / “goodbye”.
6. Logs under `~/logs/rocketchat-dm-wake/call-bot.log` and `call-media/`.

Requires: Mac awake, Docker RC up, network to meet.jit.si, operator alive.

**Status (2026-07-11):** Media unblocked for RC Call via lobby-free **voice room**
(`voice_room` on LAN `:8090`; Jitsi app domain retargeted). Automated dual-peer
preflight **T2 PASS** (`remote_rms` ≈ 0.28). Public meet.jit.si lobby was the
prior silence root cause.

- Preflight: **[preflight-voice-test-protocol.md](preflight-voice-test-protocol.md)**  
- Research / next upgrades: **[research-voice-media-path.md](research-voice-media-path.md)**

---

## D. Poll backup (usually off)

1. `rc_dm_poll.py` on an interval checks DMs for unread principal messages.
2. Same wake machinery as WebSocket path.
3. Higher latency (~20s class when it was default); kept as optional launchd.

---

## E. PGS hourly memo (adjacent, not operator wake)

1. Hourly PGS job writes `last_run.json` / activation summary.
2. EXIT trap (or dispatch) runs `pgs_hourly_rocketchat_notify.py`.
3. Script logs in as `grok` via REST and posts **one** memo to  
   `#Prime-Gap-Structure` (idempotent activation key + lock).
4. **Does not** go through `rc_operator_agent` Thinking… flow.
5. Analytic/Grok research jobs must **not** post to RC themselves  
   (see PGS `HOURLY_RELAY_CONTRACT.md`).

---

## Hard rules that shape the flow

| Rule | Effect on flow |
| --- | --- |
| One answer bubble | Only `chat.update` after Thinking… |
| Media only via helper | `rc_post_media.py` + `media-post-ledger.json` |
| No duplicate posts | See `NO_DUPLICATE_POSTS.md` |
| Principal-only wake | Other users do not trigger Grok by default |
| Channel cwd isolation | Code/tools land in the mapped project, not always agency |

---

## Sequence (text reply)

```
principal msg
    → WS event
    → postMessage "Thinking..."
    → write wake prompt / spawn grok --cwd …
    → grok finishes → reply file
    → chat.update(thinking_msg_id, final_text)
    → [optional] rc_post_media.py
```
