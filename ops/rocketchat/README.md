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

## Run tests

```bash
# Pure policy against **this mirror** (default; PR self-check)
python3 ops/rocketchat/tests/test_multi_round_collab.py

# Optional runtime integration (wake_lib / reply prompts / skill)
RC_TEST_RUNTIME=1 python3 ops/rocketchat/tests/test_multi_round_collab.py
```

`POLICY_WAKE` defaults to `Path(__file__).resolve().parents[1] / "wake"` when
`rc_multi_round_collab.py` is present there. Runtime-only cases skip unless
`RC_TEST_RUNTIME=1`.
