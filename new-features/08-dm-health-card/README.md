# Feature 08 — DM health card (`/health`)

**Nav:** [All features](../README.md) · [Research](./research.md) · [Spec](./spec.md) · [Test plan](./test-plan.md) · [Impl plan](./implementation-plan.md)

| Field | Value |
| --- | --- |
| **Enhancement list ID** | **#15** |
| **Spec** | [NF-SPEC-08](./spec.md) |
| **Status** | Documentation package |
| **One-line** | Control-plane `/health` returns a non-secret ops card (RC, operator, wakes, call, disk) without spawning Grok |

## Why

Phone-first ops: when something feels dead (ngrok, lock, Call), principal needs one glance without a full research wake.
