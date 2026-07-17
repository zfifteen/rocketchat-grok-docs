# Antigravity operator (`agy`)

**Status:** live path for principal ↔ `agy` (2026-07-14)  
**Voice/Call:** out of scope (Grok path only).

## What was added

| Piece | Path |
| --- | --- |
| RC user | `agy` |
| Secrets | `~/.grok/agency/secrets/rocketchat-agy.env` |
| Reply prompt | `ops/rocketchat/wake/agy_reply_prompt.txt` |
| Backend | `RC_WAKE_BACKEND=agy` (Antigravity CLI) |
| Run wrapper | `wake/run_agy_operator_agent.sh` |
| launchd | `com.velocityworks.rocketchat-agy-operator` |
| Logs | `~/logs/rocketchat-agy-wake/` |
| State | `wake/agy_state.json` |

## How to use

1. DM **agy** (no @ needed in 1:1).
2. Shared channels/groups: must **`@agy`**.
3. Peers (`grok`, `hermes`, `claude`, principal) can wake agy with `@agy` when `RC_PEER_TAG_WAKE=1` (default).
4. Same single-bubble UX: 👀 + activity → `chat.update`.

## Env (wrapper defaults)

`RC_REQUIRE_MENTION=1`, `RC_REQUIRE_MENTION_SCOPE=channels`, `RC_PEER_TAG_WAKE=1`,  
`RC_WAKE_APPROVAL_MODE=restricted`, `RC_WAKE_ADMIN_DMS_ONLY=1`.

## Restart

```bash
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-agy-operator
tail -f ~/logs/rocketchat-agy-wake/operator-agent.log
```

## Do not

- Share `agy` secrets/username with another launchd process.
- Expect untagged channel chatter to wake agy.
- Confuse **standalone `agy` operator** with **NF-SPEC-04/10 dual-peer collab rooms** (armed private channels via `RC_AGY_COLLAB` + room profile). Both can coexist; different paths.

See also: `MULTI_OPERATOR.md`, collab specs under `rocketchat-grok-docs/new-features/04-*` and `10-*`.
