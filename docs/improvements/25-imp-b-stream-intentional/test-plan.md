# IMP-B test plan — stream/intentional wake honesty

**Status:** draft v2 (hermes lead, 2026-07-18) — feynman pass-with-edits folded  
**Nav:** [Implementation plan](./implementation-plan.md) · [Folder](./README.md)

## Unit table

Assume bot author = grok, target peer = feynman unless noted.  
“nonfinal” = `looks_like_nonfinal_stream` True.  
“wake” = bot-author path would enqueue feynman (nonfinal false **and** intentional mention).

| ID | Body (abbrev) | nonfinal? | wake? | Notes |
| --- | --- | --- | --- | --- |
| T2a | `*Thoughts*\n@feynman dig residual X` | **True** | **no** | Labeled mid-stream |
| T2-live | `*Thoughts*\n\n@feynman dig residual X` (post-wrap intermediate) | **True** | **no** | Live shape after chrome wrap |
| T2-live-raw | bare `@feynman dig residual X` | **False** | **yes** | Indistinguishable from F2 — **must not be painted as intermediate** |
| T2-bare-mid | multi-line thought under `*Thoughts*` ending `@feynman dig` | **True** | **no** | |
| T2c | `…` / `Thinking…` | **True** | **no** | Shell |
| F1 | `*Thoughts*\nfoo\n\n────────────────\n\n@feynman dig residual X` | **False** | **yes** | Unicode rule (not markdown `---`) |
| F2 | `@feynman dig residual X` only | **False** | **yes** | Bare final assign |
| F3 | `**Shared goal:** …\n\n@feynman kill-check Y` | **False** | **yes** | |
| F4 | `*Thoughts*`…`────────────────`…`FOR: @hermes` | **False** | **yes** hermes | Footer on final |
| T1a | `I'll have feynman kill-check that @feynman when free.` | **False** | **no** | Prose — B10 intentional filter |
| T1b | `Thanks @agy for the dig.` | n/a | **no** | |
| R1 | `@hermes collab-return from \`feynman\`` | **False** | **yes** hermes | |
| R-int | recovery interim with rule + assign in thoughts | **False** | **yes risk** | Residual — document only this ship |

## Regression

| ID | Check |
| --- | --- |
| G1 | Principal `@feynman please dig` still wakes |
| G2 | Self-posts never wake |
| G3 | Operator final always uses unicode rule in `compose_final_with_thoughts` |

## Wrap unit (agent path)

| ID | Check |
| --- | --- |
| W1 | `_flush_thoughts` / chrome helper never emits body without `*Thoughts*` when thought text non-empty |
| W2 | Intermediate body never contains `────────────────` |

## Commands

```bash
python3 ops/rocketchat/tests/test_imp_b_stream_intentional.py
```

## Live smoke (after deploy)

1. During a long wake, mid-bubble text starts with `*Thoughts*` and may contain assign-shaped lines → peer must **not** wake.  
2. Final bubble with unicode rule + `@peer dig` → peer **must** wake.  
3. Bare final assign-only reply (no thoughts) → peer **must** wake.

## Pass criteria

All unit rows except R-int residual green; W1/W2 green; live smoke 1–3 once; feynman plan re-pass + impl review.
