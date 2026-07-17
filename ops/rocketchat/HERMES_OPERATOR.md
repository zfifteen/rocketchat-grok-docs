# Hermes operator (parallel to Grok)

**Status:** live path for principal ↔ `hermes` (2026-07-14)  
**Voice/Call:** intentionally out of scope (same WIP as Grok call stack).

## What was added

| Piece | Path |
| --- | --- |
| RC user | `hermes` (password in secrets) |
| Secrets | `~/.grok/agency/secrets/rocketchat-hermes.env` |
| Reply prompt | `ops/rocketchat/wake/hermes_reply_prompt.txt` |
| Backend helpers | `wake_lib.build_hermes_wake_argv` etc. |
| Operator script | same `rc_operator_agent.py` with `RC_WAKE_BACKEND=hermes` |
| Run wrapper | `wake/run_hermes_operator_agent.sh` |
| launchd | `com.velocityworks.rocketchat-hermes-operator` |
| Logs / locks | `~/logs/rocketchat-hermes-wake/` |
| State | `wake/hermes_state.json` |
| **Preflight pack** | `wake/hermes_preflight.py` + inject in `build_prompt` (Hermes only) |

Grok operator (`com.velocityworks.rocketchat-operator`) is **unchanged** at runtime defaults (`backend=grok`, original secrets).

## Hermes preflight pack (disk truth inject)

**Why:** Hermes wakes were re-reading the same Agency files every heartbeat because Lead cannot see prior disk claims. Preflight injects a short deterministic snapshot **before** the LLM runs.

**When:** Hermes operator only (`RC_WAKE_BACKEND=hermes` / hermes reply prompt / operator username hermes). Disable with `RC_HERMES_PREFLIGHT=0`.

**Contents (local only, no network, no secrets):**
- Paths named in the new message(s) that resolve under allowlist (`project_cwd`, `~/IdeaProjects`, `~/.grok/agency`): exists, mtime, size, first `#` heading, optional spotcheck hit
- Last 1–2 `wake-reply-*.txt` previews from `~/logs/rocketchat-hermes-wake/`
- If Agency residual file present: one-line open-gates hint

**Audit:** optional `~/logs/rocketchat-hermes-wake/preflight-<id>.txt`

**Tests:** `python3 ops/rocketchat/tests/test_hermes_preflight.py`

## How to use

1. Phone/desktop: DM **hermes** (no @ tag needed in 1:1).
2. **Shared channels/groups: tag-to-talk only** — message must `@hermes` (or structured mention). Untagged channel messages are ignored by Hermes so Grok can free-talk or also use `@grok`.
3. Same UX as Grok when waking: 👀 + activity bubble → `chat.update` with answer.
4. Control plane: use `!` prefix (`!help`, `!status`, `!new`, …) — still works without @ (mention-exempt).

## Tag-to-talk (multi-operator; same rules as agy/grok)

| Room | Hermes wakes when |
| --- | --- |
| DM principal↔hermes | Any principal message |
| Channel / private group | Any author who **@hermes** (principal, grok, agy, or others) |
| Control plane | Principal `!status` etc. (mention not required) |

Peers always need an explicit `@hermes` (or structured mention). Self-posts never wake (loop prevention). Disable peer tags with `RC_PEER_TAG_WAKE=0` (principal-only legacy).

Env: `RC_REQUIRE_MENTION=1` (default for Hermes), `RC_REQUIRE_MENTION_SCOPE=channels`, `RC_PEER_TAG_WAKE=1` (default).  
Set scope to `all` only if you also want @hermes required inside DMs.

## Restart

```bash
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-hermes-operator
tail -f ~/logs/rocketchat-hermes-wake/operator-agent.log
```

## Env knobs (launchd)

Same family as Grok: `RC_WAKE_APPROVAL_MODE`, `RC_WAKE_ADMIN_DMS_ONLY`, timeouts, max turns.  
Hermes-specific: `RC_WAKE_BACKEND=hermes`, `RC_HERMES_PROFILE=idea`, `HERMES_BIN`, `RC_SECRETS_PATH`,  
`RC_HERMES_PREFLIGHT=1` (default on; set `0` to disable disk-truth inject).  
Dual-operator: `RC_REQUIRE_MENTION=1`, `RC_REQUIRE_MENTION_SCOPE=channels`.

## Do not

- Run two operators as the **same** RC user.
- Point Hermes launchd at the Grok secrets file (would fight for identity).
- Expect Grok streaming-json thought stream on Hermes (stream forced off).
- Expect Hermes to answer untagged channel chatter when Grok is also present.