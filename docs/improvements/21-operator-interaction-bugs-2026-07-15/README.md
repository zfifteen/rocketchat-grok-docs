# 21 — Operator interaction bugs (2026-07-15)

**Status:** collab synthesis complete (lead grok) — specs + pure tests landed; runtime wire-in is residual  
**Runtime:** `~/.grok/agency/ops/rocketchat/`  
**Mirror:** this repo `ops/rocketchat/`  
**Source report:** principal asked for log-based bug report (DM); fix+test collab in #rocketchat-agents.

## Goal

Fix and unit-test operator interaction / messaging bugs from the 2026-07-15 report. Prefer pure-policy tests in-repo; live smoke only when safe.

## Bug register

| ID | Severity | Summary | Status |
| --- | --- | --- | --- |
| B1 | P0 | Principal→peer solo ask still emitted `collab-return` to grok | **Fixed** (runtime + mirror): emit only if assigner ∈ bot operators |
| B2 | P1 | Stale collab epoch re-arms hops | **Spec + mirror code** (agy): `record_assignee_delivered` hard gates; agency sync residual |
| B3 | P0 | Peers wake on lead activity / intermediate stream text | **Spec + pure predicates/tests** (hermes): shell + bot stream-chrome reject — not on launchd |
| B4 | P1 | HTTP 429 thrash on `chat.update` thought stream | **Spec only** (claude): throttle / single-writer plan — not implemented |
| B5 | P1 | Cancelled wakes + empty-reply recovery churn | **Spec only** (claude): recovery quality gate — not implemented |
| B6 | P2 | Duplicate room-msg log / double-seen | open (notes in B4-B5-SPEC) |
| B7 | P1 | Multi-agent pile-up after DONE / dense returns | **Spec + mirror code** (agy): assignee belt on emit when `room_id` set; operator wire residual |
| B8 | P2 | Drain log always `target=grok` | open (notes in B4-B5-SPEC) |
| B9 | P2 | Hard wake failure `rc=-6` | open (notes in B4-B5-SPEC) |
| B10 | P2 | Prose `@bot` in peer explanations re-wakes | **Spec + pure predicates/tests** (hermes): intentional mention for bot authors — not on launchd |

## Acceptance (collab)

1. B1 unit tests green in **both** runtime and this mirror.  
2. Specs / failing tests or patches landed for B2–B5 at least (design OK if code blocked).  
3. Lead synthesis with residual list; no PROOF / agency revenue scope creep.

**Met (2026-07-15):** multi_round mirror `17/17`; B3/B10 pure `7/7`; B2/B7 mirror helpers present; B4/B5 full design specs.

## Peer deliveries (this collab)

| Peer | Slice | Artifacts |
| --- | --- | --- |
| agy | B2 + B7 | `B2-B7-SPEC.md`; mirror `ops/rocketchat/wake/rc_multi_round_collab.py` gates |
| claude | B4 + B5 (+B6/B8/B9 notes) | `B4-B5-SPEC.md` |
| hermes | B3 + B10 (+B1 enqueue residual) | `B3-B10-SPEC.md`, `b3_b10_wake_predicates.py`, `test_b3_b10_wake_predicates.py` |

## Residual (post-collab implementation — lead / ops)

1. **Agency sync B2/B7:** copy mirror gates into `~/.grok/agency/ops/rocketchat/wake/rc_multi_round_collab.py` if still behind.  
2. **Operator wire:** pass `room_id` into `should_emit_return_notify` from `rc_operator_agent.py` (B7 belt live only when rid is set).  
3. **wake_lib B3/B10:** adopt pure helpers from `b3_b10_wake_predicates.py` into `should_enqueue_llm_wake` / mention path; restart operators.  
4. **B1 enqueue residual (hermes):** union structured + text + glued-run extract for `principal_multi_mention_lead_only`.  
5. **B4/B5 implement** per claude spec (update throttle + recovery quality gate).  
6. Optional live smoke: activity → intermediate with prose `@` → final intentional assign; peer wakes only on final.

## Evidence paths

- Runtime helpers: `~/.grok/agency/ops/rocketchat/wake/rc_multi_round_collab.py`  
- Runtime enqueue: `~/.grok/agency/ops/rocketchat/wake/wake_lib.py`  
- Runtime agent: `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py`  
- Mirror helpers: `ops/rocketchat/wake/rc_multi_round_collab.py`  
- Tests: `ops/rocketchat/tests/test_multi_round_collab.py` (17/17)  
- B3/B10 dig: `docs/improvements/21-operator-interaction-bugs-2026-07-15/B3-B10-SPEC.md`  
- B3/B10 pure predicates: `…/b3_b10_wake_predicates.py`  
- B3/B10 pure tests: `…/test_b3_b10_wake_predicates.py` (7/7)  
