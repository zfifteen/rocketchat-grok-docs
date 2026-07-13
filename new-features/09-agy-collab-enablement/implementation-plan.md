# Implementation plan: AGY collab enablement

**Nav:** [README](./README.md) · [Spec](./spec.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | **NF-IP-09** |
| **Effort** | M–L |
| **Depends on** | NF-SPEC-04 helpers, local `agy` CLI, RC user `agy` |

---

## Sequence

1. **Audit** — Confirm `rc_collab.py` + operator collab branches match NF-SPEC-04; list gaps.  
2. **Master flag** — Enforce `RC_COLLAB_MASTER` default off at every entry to collab classify.  
3. **Control commands** — `/collab on|off|status|budget|pause|resume` in control plane (principal-only).  
4. **Arm storage** — Durable room map in `state.json` via existing collab state helpers.  
5. **Routing wiring** — handle_principal_message uses classify only when master+armed.  
6. **agy spawn path** — Already partial; harden timeouts + reply finalize as collab identity if required.  
7. **Inject** — Load grok collab inject template when collab turn.  
8. **Tests** — NF-TP-09 T1–T6 unit; T7 live once.  
9. **Ops doc** — ROCKETCHAT.md “Collab” section + cutover checklist.  
10. **Profiles** — Keep `04-agy-rocketchat-collab/profiles/` as agent identity source of truth.

## Rollback

`RC_COLLAB_MASTER=0` + kickstart. Room arm bits ignored.

## Risks

| Risk | Mitigation |
| --- | --- |
| Cost spiral | Low hop budget; principal-only arm |
| Mention loops | Self-wake filter + budget |
| Channel noise | Private rooms only in cutover |
