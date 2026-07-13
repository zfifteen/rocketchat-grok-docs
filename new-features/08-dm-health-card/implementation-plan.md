# Implementation plan: DM health card

**Nav:** [README](./README.md) · [Spec](./spec.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | **NF-IP-08** |
| **Effort** | S–M |
| **Depends on** | NF-SPEC-03 control plane intercept |

---

## Sequence

1. Pure module functions in `rc_commands.py` or `wake_health.py`:
   - `compute_health_snapshot() -> dict`
   - `format_health_card(snapshot) -> str`
   - `overall_status(snapshot) -> GREEN|YELLOW|RED`
2. Register `/health` `/ops` in `KNOWN_CMDS` + help text.
3. Wire control-plane dispatcher to post card as grok (existing command reply path).
4. Unit tests T1–T4.
5. Docs: ROCKETCHAT.md control plane table; 03-phone-control-plane cross-link.

## Rollback

Remove command registration; no state migration.

## Files expected

- `wake/rc_commands.py`
- `wake/rc_operator_agent.py` (dispatch)
- `tests/test_usability_contracts.py` or `test_nf08_health.py`
- `ops/ROCKETCHAT.md`
