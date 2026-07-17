# NIE operator (Hermes z-mapping novel insight)

**Status:** live path for principal ↔ `nie` (2026-07-16)  
**Hermes profile:** `nie` (`RC_HERMES_PROFILE=nie`)  
**Protocol:** `nie` (z-map a/b/c/intensity/regime). **Not** insight cosplay.

## What was added

| Piece | Path |
| --- | --- |
| RC user | `nie` (display NIE) |
| Secrets | `~/.grok/agency/secrets/rocketchat-nie.env` |
| Reply prompt | `ops/rocketchat/wake/nie_reply_prompt.txt` |
| Operator script | same `rc_operator_agent.py` with `RC_WAKE_BACKEND=hermes` |
| Run wrapper | `wake/run_nie_operator_agent.sh` |
| launchd | `com.velocityworks.rocketchat-nie-operator` |
| Logs / locks | `~/logs/rocketchat-nie-wake/` |
| State | `wake/nie_state.json` |
| Hermes SOUL | `~/.hermes/profiles/nie/SOUL.md` |

Parallel to `hermes` / `feynman`. Do **not** share secrets, state, logs, or RC username with other bots.

## How to use

1. Phone/desktop: DM **nie** (no @ tag needed in 1:1).
2. Shared channels/groups: tag-to-talk only — message must `@nie`.
3. Same UX: activity bubble → `chat.update` with answer.
4. Control plane: principal `!` commands mention-exempt where enabled.

## Restart

```bash
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-nie-operator
tail -f ~/logs/rocketchat-nie-wake/operator-agent.log
```

## Env knobs (launchd)

`RC_WAKE_BACKEND=hermes`, `RC_HERMES_PROFILE=nie`, `HERMES_BIN`, `RC_SECRETS_PATH`,  
`RC_STATE_PATH`, `RC_REPLY_PROMPT`, `RC_REQUIRE_MENTION=1`, `RC_REQUIRE_MENTION_SCOPE=channels`,  
`RC_PEER_TAG_WAKE=1`, approval/timeouts same family as hermes/feynman.

## Do not

- Run two operators as the same RC user.
- Point this launchd at hermes or feynman secrets.
- Force fake breakthroughs on trivial asks.
- Forget multi-round collab treats `nie` as a first-class **peer** (lead remains `grok`).
