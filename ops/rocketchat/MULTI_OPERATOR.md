# Multi-operator Rocket.Chat roster

**Last updated:** 2026-07-16  
**Status:** live — five independent operator processes on one RC workspace.  
**Claude:** RC user + launchd service **hard-removed 2026-07-16** (do not restore without explicit principal order).

## Live bots

| RC user | Display | Backend | launchd | Secrets | Logs | Reply prompt | State |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `grok` | Grok | Grok Build CLI | `com.velocityworks.rocketchat-operator` | `secrets/rocketchat.env` | `~/logs/rocketchat-dm-wake/` | `wake/reply_prompt.txt` | `wake/state.json` |

**Lead preflight (Grok):** `wake/grok_preflight.py` injects a short orientation pack into `build_prompt` (STATE slice, this-room + cross-room collab epochs, disk delta, blocked seats, path tokens). Env kill-switch: `RC_GROK_PREFLIGHT=0`. Peer hermes preflight remains `wake/hermes_preflight.py`.
| `hermes` | Hermes | Hermes CLI (`-p idea`) | `com.velocityworks.rocketchat-hermes-operator` | `secrets/rocketchat-hermes.env` | `~/logs/rocketchat-hermes-wake/` | `wake/hermes_reply_prompt.txt` | `wake/hermes_state.json` |
| `feynman` | Feynman | Hermes CLI (`-p feynman`, protocol feynman-mechanism) | `com.velocityworks.rocketchat-feynman-operator` | `secrets/rocketchat-feynman.env` | `~/logs/rocketchat-feynman-wake/` | `wake/feynman_reply_prompt.txt` | `wake/feynman_state.json` |
| `nie` | NIE | Hermes CLI (`-p nie`, z-mapping novel insight) | `com.velocityworks.rocketchat-nie-operator` | `secrets/rocketchat-nie.env` | `~/logs/rocketchat-nie-wake/` | `wake/nie_reply_prompt.txt` | `wake/nie_state.json` |
| `agy` | Antigravity / Gemini | `RC_WAKE_BACKEND=agy` | `com.velocityworks.rocketchat-agy-operator` | `secrets/rocketchat-agy.env` | `~/logs/rocketchat-agy-wake/` | `wake/agy_reply_prompt.txt` | `wake/agy_state.json` |

Wrappers: `wake/run_operator_agent.sh`, `run_hermes_operator_agent.sh`, `run_feynman_operator_agent.sh`, `run_nie_operator_agent.sh`, `run_agy_operator_agent.sh`.  
Shared engine: `wake/rc_operator_agent.py` + `wake/wake_lib.py`.

## Wake rules (all operators)

| Room | Who wakes |
| --- | --- |
| 1:1 DM with that bot | Principal messages free-wake (unless `RC_REQUIRE_MENTION_SCOPE=all`) |
| Channel / private group | **Only** if the message **@mentions** that bot’s username |
| Peer / other humans | With **`RC_PEER_TAG_WAKE=1`** (default **on**): **any author** who `@bot` wakes that bot |
| Self-posts | **Never** wake (loop prevention) |
| Control plane | Principal `!` / `/` commands mention-exempt where control plane is on |

Env (set on each launchd wrapper; defaults match production):

| Env | Default | Meaning |
| --- | --- | --- |
| `RC_REQUIRE_MENTION` | `1` | Tag-to-talk in shared rooms |
| `RC_REQUIRE_MENTION_SCOPE` | `channels` | Require @ in `c`/`p` only; DMs free-wake |
| `RC_PEER_TAG_WAKE` | `1` (unset = on in code) | Allow non-principal authors to wake via @tag |

Code: `wake_lib.should_enqueue_llm_wake`, `peer_tag_wake_enabled`, `message_mentions_operator`.  
Legacy principal-only helper `should_handle_dm_message` remains for older call sites; prefer `should_enqueue_llm_wake`.

## Collaboration (principal preference)

- Prefer **visible in-room tags** (`@grok` `@hermes` `@feynman` `@nie` `@agy`) so the principal can see handoffs.
- DMs between bots are optional for private side work.
- Still **one answer bubble per wake** (activity → `chat.update`); no duplicate answer posts.
- Images: only `wake/rc_post_media.py`.

## Multi-round collab (all shared rooms)

**Status:** live path — medium enforcement: shared playbook + operator return-notify.  
**Distinct from NF-SPEC-10:** this path keeps **tag-to-talk starts** in any shared room (no purpose-room-only untagged lead intake).

| Piece | Path / rule |
| --- | --- |
| Playbook (one protocol for all operators) | `wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` |
| Policy helpers | `wake/rc_multi_round_collab.py` |
| Skill | `~/.grok/skills/rc-multi-round-collab/SKILL.md` |
| Reply surfaces | grok/hermes/feynman/nie/agy `*_reply_prompt.txt` + wake `build_prompt` inject |
| Shared lead-DONE state | `wake/multi_round_collab_state.json` |
| Master switch | `RC_MULTI_ROUND_COLLAB` (default **on**) |

**Behavior:**

1. **Lead = `grok`.** Peers = `hermes` / `feynman` / `nie` / `agy`.
2. **Starts:** still **tag-to-talk** in channels/groups (`@bot` required). Untagged noise does not LLM-wake.
3. **Opening a collab (clean path):** principal tags **only `@grok`**. Lead fans out to peers. If principal multi-@s lead+peers in one message, operator enqueues **lead only** (`RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY`, default **on**). Direct principal→`@peer` (no `@grok`) still wakes that peer.
4. **After a peer finishes** a shared-room wake with a useful reply, the operator posts a short **`@assigner` return-notify** (assigner if that user is a bot; else **`@grok`**) so the chain continues without the principal re-tagging each hop.
5. **Quality gate:** empty / operator-error templates (`Could not complete this reply`, empty `FINAL_ERR`, `rc: 1` templates) **do not** return-notify while the collab is open.
6. **Lead** must re-assign with `@tags` or declare **plain-language DONE** (“This concludes the collab…”, “Goal met…”, etc.). Lead peer-assign opens a **collab epoch** (shared state).
7. After lead DONE, **return-notify is suppressed**; lead does **not** LLM-wake on further `collab-return` or peer “standing by @grok” acks.
8. **Close-out anti-loop (HARD):** Lead DONE messages must include **zero** peer `@tags` (not even “Copy @agy” / “Thanks @feynman”). Peers must **not** `@grok` on stand-down acks. Only the **principal** re-opens a closed collab.

**Env (multi-round):**

| Variable | Default | Meaning |
| --- | --- | --- |
| `RC_MULTI_ROUND_COLLAB` | on | Master switch |
| `RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY` | on | Principal multi-@ lead+peers → lead only |
| `RC_MULTI_ROUND_PLAYBOOK` | `wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` | Override playbook path |
| `RC_MULTI_ROUND_STATE` | `wake/multi_round_collab_state.json` | Shared lead-DONE / epoch state |

**Tests:** `ops/rocketchat/tests/test_multi_round_collab.py`  
**Live smoke (optional):** `RC_LIVE_COLLAB_SMOKE=1 python3 ops/rocketchat/tests/live_four_agent_collab_smoke.py` (peers: hermes / feynman / agy).

## Related docs

| Doc | Role |
| --- | --- |
| `HERMES_OPERATOR.md` | Hermes-specific runbook |
| `AGY_OPERATOR.md` | Antigravity (`agy`) runbook |
| `AGENT_INTEGRATION_GUIDE.md` | Pointer to full onboarding guide |
| `~/IdeaProjects/rocketchat-grok-docs/docs/agent-integration-guide.md` | Canonical multi-agent checklist |
| `wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` | Multi-round collab playbook |
| `FEYNMAN_OPERATOR.md` | Feynman-mechanism Hermes peer runbook |
| `NIE_OPERATOR.md` | NIE z-mapping Hermes peer runbook |
| `NO_DUPLICATE_POSTS.md` | Standing anti-dup rule |
| Agency `STATE.md` | Continuity roster + peer prefs |

## Restart live operators

```bash
uid=$(id -u)
for label in \
  com.velocityworks.rocketchat-operator \
  com.velocityworks.rocketchat-hermes-operator \
  com.velocityworks.rocketchat-feynman-operator \
  com.velocityworks.rocketchat-nie-operator \
  com.velocityworks.rocketchat-agy-operator
do
  launchctl kickstart -k "gui/${uid}/${label}" 2>/dev/null || true
done
```

## Smoke

1. DM each bot without @: should free-wake.
2. In `#general` (or any shared room), untagged noise: no bot should LLM-wake.
3. `@hermes pong` / `@feynman pong` / `@nie pong` / `@agy pong` / `@grok pong` from principal: that bot wakes.
4. From `grok` (or another bot), message containing `@hermes` / `@feynman` / `@nie` (etc.): peer should wake when `RC_PEER_TAG_WAKE=1`.

Voice/Call remains **retired** unless separately productized.
