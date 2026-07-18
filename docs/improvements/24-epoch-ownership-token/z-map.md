# Z-map: multi-round lead privileges

Domain: multi-round RC collab policy (`rc_multi_round_collab.py` + operator after-wake hooks).

## Triplet

```text
A: count of open (or intended) collab epochs whose session lead is not the hard-coded username "grok"
   (measurable: principal sole-@ non-grok + peer assigns this week; or rooms with intended_lead != grok in a test matrix)

B: peer-completion pressure on those epochs
   (measurable: return-notify evaluations + DONE-language checks per open epoch-hour; hop rate)

C: number of identities that may hold fused mechanical lead privileges today
   (measurable: code constant; c = 1, username "grok")

INTENSITY ≈ a * (b / c)
REGIME:
  low  — a≈0 (all collabs intend grok): hardcode is cheap and correct
  mid  — rare hermes/feynman lead trials: chat theater, occasional misroute
  high — a>0 and multi-hop b: every DONE, epoch open, fallback notify, principal multi-@ hits wrong identity
  near-threshold — first principal "only @hermes lead this…" that needs ≥1 peer hop and a clean DONE

DELTA: standard fix is "make lead configurable (env)". Missed object is epoch-scoped ownership:
  three fused privileges keyed to GROK_LEAD while opened_by is stored and unused.

FALSIFIER: implement rooms[rid].lead claim; run hermes-only seed + hermes@peer + hermes DONE.
  Fail if any of: wrong return fallback, lead_done not set by hermes, peers race on principal multi-@,
  epoch not opened by hermes assign. Fail-as-overkill if global env default alone passes all four
  across simultaneous rooms with different intended leads (then collapse to env-only residual).
```

## Path kills (brief)

1. **Only env `RC_COLLAB_LEAD`** — works for one global non-grok lead; fails multi-room different leads without restart; still "config theater" if playbook inject stays "Lead: grok".
2. **Intentional-mention class first** — reduces social-@ loops; does not unlock non-grok DONE/epoch open.
3. **Close-out state enum alone** — helps anti-loop; does not fix who owns DONE.

Survivor: **epoch ownership token** (with default lead residual).

## Prior-art pressure

| Nearby idea | Overlap | Delta |
| --- | --- | --- |
| Env role / `GROK_LEAD` rename | single identity for lead | epoch claim is per room open, not process-wide only |
| Distributed lease / owner token | exclusive rights while held | here rights are DONE + fallback notify + principal gate + epoch open |
| NF-SPEC-10 "always grok lead" | fixed lead product choice | multi-round path already wants flexible lead trials in shared rooms |
| Return-notify assigner-first | already routes to bot assigner | fallback and DONE authority still grok-constant |
| Soft footer `FOR: @x` | advisory routing | not enforced as mechanical lead |

## Adversarial notes

- **Already known:** "don't hardcode the lead." Survives only if the deliverable is the **epoch field + four-gate rebinding**, not a proverb.
- **Edge:** peer claims lead by opening epoch without principal intent; mitigate: principal sole-tag claim wins; only operators may claim; optional "only assignees of prior lead" later.
- **So-what:** if product forever wants grok-only lead, intensity stays low and this is backlog-not-now.
