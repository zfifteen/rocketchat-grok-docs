# Feynman operator (Hermes protocol brain)

**Status:** live path for principal ↔ `feynman` (2026-07-16)  
**Hermes profile:** `feynman` (`RC_HERMES_PROFILE=feynman`)  
**Protocol:** `feynman-mechanism` (toy → moving part → kill check). **Not** historical cosplay.

## What was added

| Piece | Path |
| --- | --- |
| RC user | `feynman` |
| Secrets | `~/.grok/agency/secrets/rocketchat-feynman.env` |
| Reply prompt | `ops/rocketchat/wake/feynman_reply_prompt.txt` |
| Operator script | same `rc_operator_agent.py` with `RC_WAKE_BACKEND=hermes` |
| Run wrapper | `wake/run_feynman_operator_agent.sh` |
| launchd | `com.velocityworks.rocketchat-feynman-operator` |
| Logs / locks | `~/logs/rocketchat-feynman-wake/` |
| State | `wake/feynman_state.json` |
| Hermes SOUL | `~/.hermes/profiles/feynman/SOUL.md` |

Parallel to `hermes` (`-p idea`). Do **not** share secrets, state, logs, or RC username with hermes/grok/agy.

## How to use

1. Phone/desktop: DM **feynman** (no @ tag needed in 1:1).
2. Shared channels/groups: tag-to-talk only — message must `@feynman`.
3. Same UX: 👀 + activity bubble → `chat.update` with answer.
4. Control plane: principal `!` commands mention-exempt where enabled.

## Restart

```bash
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-feynman-operator
tail -f ~/logs/rocketchat-feynman-wake/operator-agent.log
```

## Env knobs (launchd)

`RC_WAKE_BACKEND=hermes`, `RC_HERMES_PROFILE=feynman`, `HERMES_BIN`, `RC_SECRETS_PATH`,  
`RC_STATE_PATH`, `RC_REPLY_PROMPT`, `RC_REQUIRE_MENTION=1`, `RC_REQUIRE_MENTION_SCOPE=channels`,  
`RC_PEER_TAG_WAKE=1`, approval/timeouts same family as hermes.

## Open-claim ledger (2026-07-17)

Mechanism memory for this protocol brain (not cosplay):

| Piece | Path |
| --- | --- |
| Library / CLI | `~/.hermes/profiles/feynman/scripts/feynman_claim_ledger.py` |
| Seed | `…/feynman_claim_ledger_seed.py` |
| Ledger | `~/.hermes/profiles/feynman/memories/CLAIM_LEDGER.jsonl` |
| Open summary | `…/memories/OPEN_CLAIMS.md` |

**Pre-wake:** `rc_operator_agent.build_prompt` injects open + recently closed claims when this process is feynman.  
**Post-wake:** on `FINAL_OK`, extracts TOY / MOVING PART / FAILURE from the reply file into the ledger.

```bash
python3 ~/.hermes/profiles/feynman/scripts/feynman_claim_ledger_seed.py
python3 ~/.hermes/profiles/feynman/scripts/feynman_claim_ledger.py inject --cwd ~/IdeaProjects/agency
python3 ~/.hermes/profiles/feynman/scripts/feynman_claim_ledger.py list --status open
```

## Do not

- Run two operators as the same RC user.
- Point this launchd at hermes secrets.
- Cosplay Feynman the person in prompts or SOUL.
- Forget that multi-round collab treats `feynman` as a first-class **peer** (lead remains `grok`).
