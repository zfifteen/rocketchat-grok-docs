# Third protocol object vs IMP-A / IMP-B

**Nav:** [IMP-24 ownership (A)](./README.md) · [z-map A](./z-map.md) · [B3-B10](../21-operator-interaction-bugs-2026-07-15/B3-B10-SPEC.md)  
**Hop:** hermes refined ask 2026-07-18 (A = session_lead, B = intentional+stream)

## Verdict (one line)

No third object **dominates** both A and B on every axis. The best *orthogonal* third is **IMP-C: close-out atomic finalize** (phase + DONE-masks-peer-enqueue), not a re-badge of ownership or B3/B10.

## Intensity (three axes, not one fake c)

**IMP-A session_lead / ownership token**

- a = open epochs (or seeds) whose intended lead ≠ hard-coded grok  
- b = hop / DONE / fallback-notify evaluations while mismatch holds  
- c = 1 fused privilege slot (username `grok` in code)  
- intensity high only when product actually runs non-grok lead trials  
- regime now: mid for this room (hermes-lead theater), low if product stays grok-only  

**IMP-B intentional mention + non-final stream shell**

- a = false-positive peer enqueues per open collab (stream chrome, prose @)  
- b = intermediate chat.update / synthesis rate with `@` in body  
- c = true intentional handoff rate (desired capacity)  
- intensity = false wakes / true assigns  
- **runtime note:** `wake_lib.should_enqueue_llm_wake` already has B3 shell skip + B10 intentional for bot authors (live path). Residual is incomplete shapes, footer edge cases, and same-mid races, not a greenfield design.  

**IMP-C close-out atomic finalize (third)**

- a = close-out attempts that still spawn peer LLM or return-notify thrash  
- b = messages that mix strong DONE language with residual `@peer` (or peer stand-down with `@lead`)  
- c = 1 clean close per epoch (bool `lead_done` is not enough if peer enqueue runs on the DONE mid before stamp, or if DONE+@ is still intentional)  
- intensity high exactly on the worst observed loop class (PGS residual-cell-R shape)  

## Why C is not theater

Playbook already forbids peer `@` on DONE. Operator already sets `lead_done` from DONE language **for grok only**, after finalize. Gap:

1. Peer enqueue is independent of `lead_done` (no check in `should_enqueue_llm_wake`).  
2. Same final bubble can carry DONE language **and** line-start or assign-shaped `@peer` → B10 may still wake.  
3. Stamp order: peers can observe the mid before `mark_lead_done` is durable.  

**Protocol object:** room phase `open | closing | closed` (or synchronous rule: bot-authored body matching `reply_declares_lead_done` ⇒ **no peer enqueue** for that mid; stamp `lead_done` before or at first publish of that body).

## Rank for this collab goal

| If goal is… | Pick | Residual |
| --- | --- | --- |
| Enable hermes-led epochs without split-brain | **A full** (session_lead / ownership) | thrash from mentions until B residuals cleaned |
| Cut thrash under fixed grok lead this week | **B residual wire-check** + **C** | non-grok lead still chat theater |
| Kill worst close-out loop per line of code | **C** | does not unlock hermes lead; does not replace full B |

**Not better as “the one”:** ownership token alone (already A); assign-shaped mentions alone (already B, largely shipped).

## Falsifier for IMP-C

Bot lead posts final body: strong collab DONE language plus line-start `@nie thanks`.  
**Pass:** nie does not enqueue LLM; room `lead_done` true within same finalize path; no return-notify from nie.  
**Kill:** nie still wakes, or lead_done never sets, or only works when `@` is absent (then C is redundant with playbook compliance).

## Next pressure for lead

Pick **one** ship bar:

1. **A** if principal wants hermes-lead as product (full reify only; grok split-brain warning stands).  
2. **C** if the win is “close never thrash” under grok lead (smallest new state).  
3. **B residual audit** if live still shows stream `@` wakes (prove with mid log before more design).

Do not half-ship A.
