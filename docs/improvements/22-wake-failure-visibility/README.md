# IMP-22 — Wake failure visibility & restricted-tool diagnostics

**Status:** Implemented (2026-07-16) — PR + live runtime patched; restart operators to load  
**Date:** 2026-07-16  
**Author:** hermes (principal request in #rocketchat-agents)  
**Runtime:** `~/.grok/agency/ops/rocketchat/wake/`  
**Issue:** https://github.com/zfifteen/rocketchat-agents/issues/4  
**Related:** [IMP-01 approval](../../new-features/…), [improvement 21 interaction bugs](../21-operator-interaction-bugs-2026-07-15/), [B4-B5](../21-operator-interaction-bugs-2026-07-15/B4-B5-SPEC.md), phase-chrome FINAL_ERR

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Implementation](./IMPLEMENTATION.md)

---

## One-line summary

Make restricted-mode wake failures **specific and visible in the Rocket.Chat bubble** (denied tools, stopReason, approval mode) instead of generic “could not complete” / empty finals — without flipping all channels to full YOLO.

## Why this exists

Principal is happy with the RC multi-agent integration overall, but day-to-day pain is **wake/response errors**: tools fail (often under restricted approval), then **error detail is lost** and chat only shows thin agent or operator messages.

Analysis (2026-07-16): hypothesis is largely correct for Hermes-on-channels; Grok had a known headless permission incident (`acceptEdits` → Cancelled); Agy currently skips CLI permissions for headless reply writes. The operator’s FINAL_ERR path knows `stopReason` / `rc` / log basename but **does not surface denied-tool lines** from the wake log.

## Deliverables in this folder

| File | Role |
| --- | --- |
| `README.md` | This overview |
| `requirements.md` | Ranked improvements + acceptance |
| `test-plan.md` | How to verify |

## Out of scope

- Migrating the transport to Discord (evaluated; stay on RC).
- Full multi-agent thrash package (B2–B10 under improvement 21) except where it overlaps error UX.
- Secrets in chat bubbles (never).
