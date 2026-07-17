# Voice / Call integration — RETIRED

**Date:** 2026-07-17  
**Decision:** Principal does **not** want voice/Call as an integration feature.

## Hard gates (do not bypass casually)

| Gate | Default | Meaning |
| --- | --- | --- |
| `RC_CALL_ENABLED` | **off** | Operator ignores videoconf; no media spawn |
| `RC_PUBLIC_VOICE` | **off** | Public proxy does **not** route `/Agency*` or `/ws` to voice |
| Voice bind | `127.0.0.1` | No `0.0.0.0` mesh listen |
| launchd `com.velocityworks.rocketchat-voice-room` | **disabled** (`.plist.disabled`) | Must not KeepAlive |
| VideoConf_* settings | **false** in `docker-compose.yml` | Call UI disabled at workspace level |

## Roadmap

- Feature **NF-01** (`new-features/01-true-voice-in-rc-call/`) is **WONTFIX / retired** — not on the product roadmap.
- Path C (`call/rc_call_bot.py`, Playwright) and Path D (LiveKit voice agent) are **lab archives only**.
- `voice_room/` is **not** a production surface (C1 security residual if re-published).

## To re-enable (explicit only — not recommended)

Requires **all** of:

1. Principal written approval + roadmap entry reinstating NF-01.
2. Authenticated join (RC session/token) before any public bind.
3. `RC_CALL_ENABLED=1` on operator env.
4. `RC_PUBLIC_VOICE=1` only after (2).
5. VideoConf settings re-enabled deliberately (not by accident from old scripts).

## Code still on disk

Left for archaeology / possible future rewrite. Runtime defaults prevent activation.
Do not add Call to multi-operator feature lists or “quick start” docs.
