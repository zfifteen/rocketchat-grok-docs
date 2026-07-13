# Feature 09 — AGY collab enablement

**Nav:** [All features](../README.md) · [Research](./research.md) · [Spec](./spec.md) · [Test plan](./test-plan.md) · [Impl plan](./implementation-plan.md)

| Field | Value |
| --- | --- |
| **Enhancement list ID** | **#16** |
| **Spec** | [NF-SPEC-09](./spec.md) |
| **Parent feature** | [04-agy-rocketchat-collab](../04-agy-rocketchat-collab/) (NF-SPEC-04) |
| **v1 protocol** | [10-lead-peer-full-collab](../10-lead-peer-full-collab/) (**NF-SPEC-10**) — lead intake + full peer bar |
| **Status** | Documentation package — enablement / cutover layer on top of NF-04 / NF-10 |
| **One-line** | Principal-gated arming of dual-peer Grok↔agy rooms with hop budget, mention routing, and no infinite self-wake |

## Why

NF-SPEC-04 defines collab mechanics and pure helpers exist (`rc_collab.py`). This package specifies **how to turn it on safely** in production RC without dual-agent noise or runaway cost.
