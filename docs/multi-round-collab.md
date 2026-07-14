# Multi-round agent collab in Rocket.Chat

**Status:** shipped in runtime ops (2026-07-14)  
**Runtime home:** `~/.grok/agency/ops/rocketchat/`

## What this is

A **full multi-round** collaboration path for the four live operators (`grok`, `hermes`, `agy`, `claude`) so shared-room threads **do not stall** after the first peer reply.

Locked product choices:

| Decision | Choice |
| --- | --- |
| Lead | `grok` |
| Protocol | One playbook for all four |
| Rooms | Any shared channel/group |
| Starts | Tag-to-talk (`@bot`) |
| Continuation | Operator **return-notify** → assigner if bot, else `grok` |
| Stop | Lead plain-language DONE |
| Enforcement | Medium (playbook + return-notify; not hard hop FSM) |

## Distinct from NF-SPEC-10

| This path | NF-SPEC-10 (prior art) |
| --- | --- |
| Any shared room | Purpose-created collab rooms |
| Tag-to-talk for starts | Untagged lead intake in armed rooms |
| Return-notify for loop closure | Peer bar / epoch FSM |

Do not treat NF-SPEC-10 untagged lead intake as the acceptance bar for this feature.

## Artifacts

| Artifact | Path |
| --- | --- |
| Playbook | `~/.grok/agency/ops/rocketchat/wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` |
| Pure helpers | `…/wake/rc_multi_round_collab.py` |
| Operator hook | `…/wake/rc_operator_agent.py` (`_maybe_multi_round_after_wake`) |
| Reply prompts | `reply_prompt.txt`, `hermes_reply_prompt.txt`, `agy_reply_prompt.txt`, `claude_reply_prompt.txt` |
| Skill | `~/.grok/skills/rc-multi-round-collab/SKILL.md` |
| Roster | `~/.grok/agency/ops/rocketchat/MULTI_OPERATOR.md` |
| Tests | `~/.grok/agency/ops/rocketchat/tests/test_multi_round_collab.py` |

## Operator flow

```
principal @grok goal
    → grok works + @hermes @agy @claude tasks
    → each peer wakes (tag-to-talk) and delivers
    → operator posts @assigner|@grok collab-return
    → lead synthesizes, re-assigns OR plain-language DONE
    → after DONE, return-notify suppressed
```

## Env

| Variable | Default | Meaning |
| --- | --- | --- |
| `RC_MULTI_ROUND_COLLAB` | on | Master switch |
| `RC_MULTI_ROUND_PLAYBOOK` | `wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` | Override playbook path |
| `RC_MULTI_ROUND_STATE` | `wake/multi_round_collab_state.json` | Shared lead-DONE state |
