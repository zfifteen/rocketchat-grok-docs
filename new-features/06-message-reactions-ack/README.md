# Feature 06 — Message reactions as wake ack

**Nav:** [All features](../README.md) · [Research](./research.md) · [Spec](./spec.md) · [Test plan](./test-plan.md) · [Impl plan](./implementation-plan.md)

| Field | Value |
| --- | --- |
| **Enhancement list ID** | **#11** (next-wave RC enhancements, principal DM 2026-07-12) |
| **Spec** | [NF-SPEC-06](./spec.md) |
| **Test plan** | [NF-TP-06](./test-plan.md) |
| **Status** | Documentation package — not yet implemented |
| **One-line** | Operator adds RC emoji reactions on Thinking… start / final (👀 / ✅ / ⚠️) without a second text bubble |

## Why

Thinking… meta text already signals work. Reactions are **zero-width** presence on mobile: glanceable, no extra bubbles, no duplicate-post risk.

## Primary code (when implemented)

- `wake/rc_operator_agent.py` — post/finalize hooks
- RC REST `chat.react` (operator auth only)
- Env: `RC_WAKE_REACT`
