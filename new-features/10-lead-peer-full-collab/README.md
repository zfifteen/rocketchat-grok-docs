# Feature 10 — Lead–Peer Full Collab (Grok lead · AGY full peer)

**Bundle home:** `new-features/10-lead-peer-full-collab/`  
**Status:** Documentation only (spec); runtime not required by this package  
**Parent index:** [`../README.md`](../README.md)

Purpose-created collab channel (e.g. `#grok-agy-collab`): principal posts **untagged** goals; **Grok is always lead** (intake + integration); **AGY is a full peer** (required substantive co-work, not an add-on). Dual RC identities, serial wakes, hop budget, peer bar before Done.

## Documents in this bundle

| Layer | File | ID |
| --- | --- | --- |
| **Technical specification** | [spec.md](./spec.md) | **NF-SPEC-10** |
| **Implementation plan** | [implementation-plan.md](./implementation-plan.md) | **NF-IP-10** (`!goal` ladder GOAL-00…22) |
| **Test plan** | [test-plan.md](./test-plan.md) | **NF-TP-10** (L0–L6; AC traceability) |

## Snapshot

| Piece | Choice |
| --- | --- |
| **Mode id** | `lead_peer_full` |
| **Channel** | Purpose-created, e.g. `#grok-agy-collab` |
| **Intake** | Untagged principal text → **Grok lead** always |
| **Peer** | **AGY full peer** — real packages, adversarial pass, peer bar |
| **Handoff** | Observable `@agy` / `@grok` on the floor |
| **Done** | Lead closes only if peer bar met (or principal `!collab complete`) |
| **Backend agy** | Local `agy` CLI only |
| **Prior specs** | [NF-SPEC-04](../04-agy-rocketchat-collab/spec.md), [NF-SPEC-09](../09-agy-collab-enablement/spec.md) |

## Reading order

1. [spec.md](./spec.md) — normative requirements  
2. [implementation-plan.md](./implementation-plan.md) — **NF-IP-10** fine-grained ladder for `!goal` execution  
3. [test-plan.md](./test-plan.md) — **NF-TP-10** meticulous proof plan (unit → live)  
4. [NF-SPEC-04](../04-agy-rocketchat-collab/spec.md) — dual-identity primitives  
5. [NF-SPEC-09](../09-agy-collab-enablement/spec.md) — arming / enablement  
6. [profiles](../04-agy-rocketchat-collab/profiles/) — L2 identity drafts (update for lead vs peer)

## Execute via `!goal` (summary)

```text
!cwd pin /Users/velocityworks/.grok/agency
!goal NF-IP-10 GOAL-01: In rc_collab.py implement lead_peer_full classifier …
```

Advance **one GOAL-XX at a time** (see NF-IP-10 §4). Prefer `!` not `/`.

## Related runtime (when implemented)

`~/.grok/agency/ops/rocketchat/wake/{rc_operator_agent,rc_collab,rc_commands,wake_lib}.py`
