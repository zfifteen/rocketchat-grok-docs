# Multi-round collab — reviewable runtime mirror

**Canonical live code** remains under:

`~/.grok/agency/ops/rocketchat/`

This tree holds **reviewable copies** of the multi-round collab surface for PR review in `zfifteen/rocketchat-grok-docs` (issue #2). Deploy by copying into the agency ops tree (or edit runtime in place on the principal Mac).

## Layout

| Path | Role |
| --- | --- |
| `wake/rc_multi_round_collab.py` | Pure policy helpers (unit-testable) |
| `wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` | Injected playbook (v3) |
| `wake/OPERATOR_MULTI_ROUND_HOOKS.md` | Excerpt of `rc_operator_agent.py` wiring |
| `tests/test_multi_round_collab.py` | Unit suite (loads runtime `WAKE_DIR` by default) |
| `tests/live_four_agent_collab_smoke.py` | Optional live smoke (`RC_LIVE_COLLAB_SMOKE=1`) |
| `MULTI_ROUND_OPERATOR_NOTES.md` | Roster / ops notes section |
| `skills/rc-multi-round-collab.SKILL.md` | Skill mirror |

## Run tests against live runtime

```bash
python3 ~/.grok/agency/ops/rocketchat/tests/test_multi_round_collab.py
```

The mirrored test file uses `Path.home() / ".grok/agency/ops/rocketchat/wake"` so it always exercises the **deployed** helpers.
