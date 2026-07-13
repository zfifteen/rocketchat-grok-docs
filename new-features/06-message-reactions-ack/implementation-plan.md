# Implementation plan: Message reactions as wake ack

**Nav:** [README](./README.md) · [Spec](./spec.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | **NF-IP-06** |
| **Effort** | S |
| **Depends on** | Live RC 8.6; operator REST session |

---

## Sequence

1. **T0 live probe** — confirm `chat.react` body for RC 8.6; write result into `rc_operator_agent` comment.
2. **Helper** — `react_message(msg_id, emoji, *, should_react=True) -> bool` next to `update_message`.
3. **Env gates** — `wake_react_enabled()`, emoji defaults from env.
4. **Hooks**
   - After `post_thinking_placeholder` success → async start react.
   - In finalize FINAL_OK / FINAL_ERR → terminal react.
5. **Tests** — T1–T4 unit; T5 optional live.
6. **Docs** — `ops/ROCKETCHAT.md` one row; config.example flags.
7. **Deploy** — kickstart operator (or autoreload if #3 lands).

## Rollback

Set `RC_WAKE_REACT=0` on launchd; kickstart. No schema migration.

## Files touched (expected)

- `wake/rc_operator_agent.py`
- `wake/wake_lib.py` (optional pure env helpers)
- `tests/test_usability_contracts.py` or new `test_nf06_reactions.py`
- `ops/ROCKETCHAT.md`, `config.example`
