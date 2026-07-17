# IMP-23 — Wake / response UX rough edges (log deep dive)

**Status:** In progress — Wave 1 (S1/S2) + S4/S7/S14 + **S5 code** (2026-07-17); residual S3/S6/S8/S10–S13 + S5 live acceptance  
**Date:** 2026-07-16  
**Author:** hermes (principal: “experience still has rough edges — deep dive logs + list improvements”)  
**Evidence window:** operator + wake-run logs under `~/logs/rocketchat-*-wake/` (through ~2026-07-17T01:00Z)  
**Related:** [21 interaction bugs](../21-operator-interaction-bugs-2026-07-15/), [22 wake failure visibility](../22-wake-failure-visibility/), [phase-chrome plan](../../reviews/2026-07-14-phase-chrome-implementation-plan.md), [Heavy review](../../reviews/2026-07-14-rc-integration-heavy-review.md)

**Nav:** [Index](../INDEX.md) · [Suggested improvements](./suggested-improvements.md) · [Evidence notes](./evidence.md) · [Implementation](./IMPLEMENTATION.md) · [S5 test plan](./test-plan-s5.md)

---

## One-line summary

Quantify live wake/response friction from production logs, then rank concrete fixes that close the gap between “agent woke” and “principal got a trustworthy bubble.”

## Scope

| In | Out |
| --- | --- |
| Operator agent UX (wake → stream → finalize → collab return) | Docker/ngrok/infra (covered elsewhere) |
| All five live operators: grok, hermes, agy, nie, feynman | Voice/call path |
| Rate limits, Cancelled empty replies, multi-agent pile-up, cwd/spawn fails | Product features (new NF-*) |

## Headline metrics (this Mac, log corpus)

| Signal | Grok | Hermes | Agy | Nie | Feynman |
| --- | ---: | ---: | ---: | ---: | ---: |
| Wakes logged | 409 | 102 | 110 | 16 | 11 |
| FINAL_OK | 329 | 103 | 91 | 16 | 12 |
| FINAL_ERR | 15 | 0 | **33** | 0 | 0 |
| HTTP 429 on update | **491** | 235 | 316 | 23 | 25 |
| empty-reply recovery | 11 | 2 | 2 | 0 | 0 |
| stopReason=Cancelled (op log) | 42 | 2 | 0 | 0 | 0 |
| enqueue skip in-flight | 308 | 177 | 187 | 31 | 24 |
| skip no_operator_mention | 121 | 250 | 278 | 42 | 42 |

**Dominant pain (honest ranking):** (1) RC `chat.update` 429 thrash during stream/finalize, (2) Grok `Cancelled` + empty reply file despite streamed text, (3) Agy high FINAL_ERR rate, (4) multi-agent mention/collab residual noise, (5) missing cwd / process exceptions without good bubble text.

## Deliverables

| File | Role |
| --- | --- |
| `README.md` | This overview + metrics |
| `suggested-improvements.md` | Ranked S1–S14 improvements with acceptance |
| `evidence.md` | Log quotes / event counts / sample wake-runs |
| `IMPLEMENTATION.md` | What shipped (Wave 1 + helpers) + deploy/verify |
| `test-plan-s5.md` | S5 in-flight busy chrome + follow-up queue test plan (pure / regression / mock / live) |
