# Multi-round agent collab in Rocket.Chat

**Status:** shipped in runtime ops; issue [#2](https://github.com/zfifteen/rocketchat-grok-docs/issues/2) hardening (P0 + partial P1) on branch `issue-2-multi-round-collab-hardening`  
**Runtime home:** `~/.grok/agency/ops/rocketchat/`  
**Reviewable mirror in this repo:** [`ops/rocketchat/`](../ops/rocketchat/)

## What this is

A **full multi-round** collaboration path for the four live operators (`grok`, `hermes`, `agy`, `claude`) so shared-room threads **do not stall** after the first peer reply, and so clean close-out does not thrash the room.

Locked product choices:

| Decision | Choice |
| --- | --- |
| Lead | `grok` |
| Protocol | One playbook for all four |
| Rooms | Any shared channel/group |
| Starts | Tag-to-talk (`@bot`) |
| Open (clean path) | Principal tags **only `@grok`**; lead fans out |
| Continuation | Operator **return-notify** → assigner if bot, else `grok` |
| Stop | Lead plain-language DONE (**zero** peer `@tags`) |
| Enforcement | Medium (playbook + return-notify; not hard hop FSM) |

## Distinct from NF-SPEC-10

| This path | NF-SPEC-10 (prior art) |
| --- | --- |
| Any shared room | Purpose-created collab rooms |
| Tag-to-talk for starts | Untagged lead intake in armed rooms |
| Return-notify for loop closure | Peer bar / epoch FSM |

Do not treat NF-SPEC-10 untagged lead intake as the acceptance bar for this feature.

## Artifacts

| Artifact | Runtime path | Repo mirror |
| --- | --- | --- |
| Playbook | `~/.grok/agency/ops/rocketchat/wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` | [`ops/rocketchat/wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md`](../ops/rocketchat/wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md) |
| Pure helpers | `…/wake/rc_multi_round_collab.py` | [`ops/rocketchat/wake/rc_multi_round_collab.py`](../ops/rocketchat/wake/rc_multi_round_collab.py) |
| Operator hooks | `…/wake/rc_operator_agent.py` | excerpt [`OPERATOR_MULTI_ROUND_HOOKS.md`](../ops/rocketchat/wake/OPERATOR_MULTI_ROUND_HOOKS.md) |
| Reply prompts | four `*_reply_prompt.txt` | (runtime) |
| Skill | `~/.grok/skills/rc-multi-round-collab/SKILL.md` | [`ops/rocketchat/skills/…`](../ops/rocketchat/skills/rc-multi-round-collab.SKILL.md) |
| Roster notes | `…/MULTI_OPERATOR.md` | [`MULTI_ROUND_OPERATOR_NOTES.md`](../ops/rocketchat/MULTI_ROUND_OPERATOR_NOTES.md) |
| Unit tests | `…/tests/test_multi_round_collab.py` | [`ops/rocketchat/tests/test_multi_round_collab.py`](../ops/rocketchat/tests/test_multi_round_collab.py) |
| Live smoke | `…/tests/live_four_agent_collab_smoke.py` | [`ops/rocketchat/tests/live_four_agent_collab_smoke.py`](../ops/rocketchat/tests/live_four_agent_collab_smoke.py) |

## Operator flow (clean path)

```
principal @grok goal          ← peers do not enqueue on multi-@ seed
    → grok works + @hermes @agy @claude tasks   ← opens collab epoch
    → each peer wakes (tag-to-talk) and delivers
    → operator posts @assigner|@grok collab-return  (quality-gated)
    → lead synthesizes, re-assigns OR plain-language DONE (zero peer @)
    → after DONE: return-notify suppressed; lead skips collab-return LLM
```

## Issue #2 hardening (this PR)

### P0 — shipped

| Item | Behavior |
| --- | --- |
| **Principal open = lead only** | `principal_multi_mention_lead_only`: when principal tags lead **and** ≥1 peer in one shared-room message, peers **do not** enqueue; lead handles fan-out. Kill-switch: `RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY=0`. |
| **Lead short-circuit after DONE** | `should_skip_lead_llm_on_collab_return` / `should_skip_lead_llm_on_peer_closeout_ack` — no lead CLI thrash on post-DONE returns/stand-by. |
| **Quality-gated return-notify** | Empty / operator-error templates (`Could not complete this reply`, empty `FINAL_ERR`, short `rc: 1` bodies) do **not** emit `collab-return` while collab is open. Phase/rc passed from `_maybe_multi_round_after_wake`. |
| **Close-out anti-loop** | Strong DONE language may set `lead_done` even with incidental “Copy @agy”; only **principal** re-opens; peers must not `@grok` on stand-down. |
| **Clean-path live smoke** | `live_four_agent_collab_smoke.py` gated by `RC_LIVE_COLLAB_SMOKE=1`. |

### P1 — partial

| Item | Behavior |
| --- | --- |
| **Collab epoch** | First lead peer-assign opens epoch; later assigns **reuse** (merge assignees, keep delivered) unless `force=True` / after DONE. Return-notify may stamp `epoch=…`. |
| **Peer soft footer** | Optional `STATUS:` / `FOR:` / `EPOCH:` parse via `parse_peer_delivery_footer`. |
| **Coalesce lead synthesis** | Deferred (not in this PR). |

### P2 — partial

| Item | Behavior |
| --- | --- |
| **Shared-state RMW** | `update_shared_state` holds `fcntl.flock` for full load→mutate→write (cross-process safe). |
| **Health snapshot** | `health_multi_round_fields`. |
| **Full observability suite** | Deferred. |

## Env

| Variable | Default | Meaning |
| --- | --- | --- |
| `RC_MULTI_ROUND_COLLAB` | on | Master switch |
| `RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY` | on | Principal multi-@ lead+peers → lead only |
| `RC_MULTI_ROUND_PLAYBOOK` | `wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` | Override playbook path |
| `RC_MULTI_ROUND_STATE` | `wake/multi_round_collab_state.json` | Shared lead-DONE / epoch state |
| `RC_LIVE_COLLAB_SMOKE` | off | Enable live smoke script |

## Tests

```bash
# Pure unit suite (defaults to repo/mirror wake dir next to the test file)
python3 ops/rocketchat/tests/test_multi_round_collab.py

# + runtime integration (wake_lib, four reply prompts, skill)
RC_TEST_RUNTIME=1 python3 ~/.grok/agency/ops/rocketchat/tests/test_multi_round_collab.py

# Live smoke (principal secrets; posts to RC)
RC_LIVE_COLLAB_SMOKE=1 RC_SMOKE_ROOM=general \
  python3 ~/.grok/agency/ops/rocketchat/tests/live_four_agent_collab_smoke.py
```

**Unit suite acceptance (16 cases):** pure policy always; tag-to-talk gates gated by `RC_TEST_RUNTIME`; return-notify assigner|grok; lead DONE suppress; collab-return template matcher; atomic concurrent RMW; principal multi-mention lead-only; quality gate; epoch reuse+footer; playbook **Opening a collab**.

## Deploy (runtime Mac)

After pulling/mirroring code into `~/.grok/agency/ops/rocketchat/`:

```bash
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-operator
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-hermes-operator
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-agy-operator
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-claude-operator
```

Confirm logs show `config applied` / `ws_connected` and greppable `multi-round` lines during the next collab.

## Related

- Issue: https://github.com/zfifteen/rocketchat-grok-docs/issues/2  
- Implementation plan: issue comment on #2  
- NF-SPEC-10 (different contract): [`new-features/10-lead-peer-full-collab/`](../new-features/10-lead-peer-full-collab/)
