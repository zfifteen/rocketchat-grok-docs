# Feature 07 — Outbound Imagine / media single path

**Nav:** [All features](../README.md) · [Research](./research.md) · [Spec](./spec.md) · [Test plan](./test-plan.md) · [Impl plan](./implementation-plan.md)

| Field | Value |
| --- | --- |
| **Enhancement list ID** | **#13** |
| **Spec** | [NF-SPEC-07](./spec.md) |
| **Status** | Documentation package — partial runtime exists (`rc_post_media.py`) |
| **One-line** | All outbound images/files go through one idempotent helper; ban double `mediaConfirm` and ad-hoc upload loops |

## Why

Principal was burned by duplicate image bubbles when `rooms.mediaConfirm` ran twice on the same `fileId`. Helper + ledger exist; this package makes the contract **normative** end-to-end (prompt, tests, optional wrapper script).
