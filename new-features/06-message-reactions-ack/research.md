# Research: Message reactions as wake ack

**Nav:** [README](./README.md) · [Spec](./spec.md)

| Field | Value |
| --- | --- |
| **ID** | NF-R-06 |
| **Date** | 2026-07-12 |
| **Enhancement #** | 11 |

---

## Problem

Principals on mobile cannot always tell if a wake started, finished, or failed without reading the Thinking bubble. Streaming meta (`Working…`) helps but still mutates the same text bubble and can thrash. A second status post violates **NO DUPLICATE POSTS**.

## Options

| Option | Description | Verdict |
| --- | --- | --- |
| A | Text-only meta stream | Status quo; no zero-width signal |
| B | `chat.react` on Thinking message id | Zero extra bubbles; native RC UX |
| C | Separate “ack” channel message | **Reject** — second bubble |
| D | Presence API only | Not per-message; weak |

## Recommendation

**B:** Operator-owned reactions on the Thinking message only:

| Phase | Reaction |
| --- | --- |
| Wake start / Thinking posted | 👀 or ⏳ |
| FINAL_OK | remove start react; add ✅ |
| FINAL_ERR | remove start react; add ⚠️ |

React failures must never fail the wake. Feature flag `RC_WAKE_REACT` (default on).

## Open questions

- Exact emoji set (client rendering differs).
- Whether `chat.react` requires different API shape on RC 8.6 (verify in TP live case).
- Remove vs replace reaction when transitioning start → final.
