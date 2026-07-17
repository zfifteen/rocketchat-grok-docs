# Multi-round collab — reviewable runtime mirror

**Canonical live code** remains under:

`~/.grok/agency/ops/rocketchat/`

This tree holds **reviewable copies** of the multi-round collab surface for PR review in `zfifteen/rocketchat-grok-docs` (issue #2). Deploy by copying into the agency ops tree (or edit runtime in place on the principal Mac).

## Layout

| Path | Role |
| --- | --- |
| `wake/rc_multi_round_collab.py` | Pure policy helpers (unit-testable) |
| `wake/wake_denials.py` | IMP-22 tool-denial extract |
| `wake/wake_ux_imp23.py` | IMP-23 S1/S2/S4/S7 pure helpers |
| `wake/wake_inflight_ux.py` | IMP-23 S5 in-flight busy / follow-up / pending-update policy |
| `wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` | Injected playbook (v3) |
| `wake/OPERATOR_MULTI_ROUND_HOOKS.md` | Excerpt of `rc_operator_agent.py` wiring |
| `tests/test_multi_round_collab.py` | Unit suite (loads runtime `WAKE_DIR` by default) |
| `tests/test_wake_denials_imp22.py` | IMP-22 pure tests |
| `tests/test_wake_ux_imp23.py` | IMP-23 Wave 1 pure tests |
| `tests/test_wake_inflight_ux_s5.py` | IMP-23 S5 pure tests (22) |
| `tests/test_wake_telemetry_b4_b5.py` | B4 StreamThrottle cool-down probes |
| `tests/live_four_agent_collab_smoke.py` | Optional live smoke (`RC_LIVE_COLLAB_SMOKE=1`) |
| `scripts/rc_wake_digest.py` | 24h multi-bot wake UX digest (S14) |
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
