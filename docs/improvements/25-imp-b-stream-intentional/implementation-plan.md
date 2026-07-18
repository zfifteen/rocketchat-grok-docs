# IMP-B implementation plan — stream/intentional wake honesty

**Status:** draft v2 (hermes lead, 2026-07-18) — incorporates feynman pass-with-edits  
**Parent ranking:** ship-this-week  
**Not in scope:** IMP-A / epoch ownership (IMP-24)

**Nav:** [Test plan](./test-plan.md) · [B3-B10 SPEC](../21-operator-interaction-bugs-2026-07-15/B3-B10-SPEC.md) · [Index](../INDEX.md)

**Review history:**  
- v1: hermes draft (delete short-circuit only)  
- feynman: **pass-with-edits** — live intermediate paints are bare thought tails (no `*Thoughts*`); delete-only leaves T2-live green  
- v2: intermediate chrome wrap + short-circuit delete + expanded table (this file)

---

## Goal

Stop **live** intermediate activity-bubble paints from waking peers when they contain intentional-looking `@op dig…`, while still allowing **final** bot→peer assigns (including bare F2 and `*Thoughts*` + unicode rule + assign) to wake.

## Root cause (disk, confirmed)

### Predicate

Live `wake_lib.looks_like_nonfinal_stream`:

```text
if looks_like_final_composed_reply(raw): return False
if intentional_operator_mentions(raw): return False   # intentional short-circuit
# stream-shell head → True else False
```

### Live intermediate paint (the real T2)

`rc_operator_agent._flush_thoughts` (~2902):

```text
body = thoughts.format(...)   # format_thought_intermediate: raw tail only
update_thinking_meta(rid, mid, body, ...)
```

`ThoughtAccumulator.format` → `format_thought_intermediate`: **no** `*Thoughts*` label, **no** `────────────────` rule. A thought buffer that happens to contain a line-start `@feynman dig X` is **string-equal to a bare final assign (F2)**.

So:

| Shape | After delete-only short-circuit | Reality |
| --- | --- | --- |
| T2a `*Thoughts*\n@feynman dig` | nonfinal True → no wake | Rare as intermediate |
| T2-live bare `@feynman dig` mid-stream | nonfinal False → **still wake** | Live `_flush_thoughts` |
| F1 `*Thoughts*` + `─`×16 + answer | final → wake | Live `compose_final_with_thoughts` |
| F2 bare final `@feynman dig` | final → wake | Must keep |

**Algorithm cannot mind-read F2 vs T2-live when strings are identical.** Ship must make intermediates **recognizably nonfinal chrome**.

## Design — two-line product rule (ship)

### 1) Intermediate paints always wrap stream chrome

In **agency** `rc_operator_agent._flush_thoughts` (and any sibling flush that paints thought-only bodies), wrap before `update_thinking_meta`:

```text
body = "*Thoughts*\n\n" + thoughts.format(max_chars=stream_max_chars())
```

- Prefer reusing `THOUGHTS_SECTION_LABEL` from `wake_lib` (`*Thoughts*`).  
- **Never** put `THOUGHTS_SECTION_RULE` (`────────────────`) on intermediate paints.  
- Optionally centralize as `format_thought_intermediate_chrome(text)` in `wake_telemetry` next to `format_thought_intermediate`.

### 2) Predicate: delete intentional short-circuit; shell head without final marker ⇒ nonfinal

`looks_like_nonfinal_stream`:

```text
if shell/empty: return True
if looks_like_final_composed_reply(raw): return False   # unicode ─{3,} or Shared goal
if stream_shell_head(raw): return True                 # *Thoughts* / Thinking / …
# DELETE: if intentional_operator_mentions(raw): return False
return False
```

Effects:

- **T2-live after wrap:** `*Thoughts*\n\n@feynman dig` + no rule → nonfinal True → no wake.  
- **F1:** has `─{3,}` → final False for nonfinal fn → wake via intentional path.  
- **F2 bare final:** no shell head → nonfinal False → wake.  
- **Collab-return / bare FOR finals:** no shell head → still wake.  
- **FOR under *Thoughts* without rule:** nonfinal (false negative residual for hand-edited bots; operator finals always add rule).

### Files to change

| Path | Change |
| --- | --- |
| `~/.grok/agency/ops/rocketchat/wake/wake_lib.py` | Delete intentional short-circuit in `looks_like_nonfinal_stream` |
| `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` | Wrap intermediate body in `_flush_thoughts` with `*Thoughts*\n\n` |
| `~/.grok/agency/ops/rocketchat/wake/wake_telemetry.py` (optional) | `format_thought_intermediate_chrome` helper |
| `ops/rocketchat/tests/test_imp_b_stream_intentional.py` (new) | Unit table below |
| Docs mirror under `ops/rocketchat/` if present | Sync after agency green |

### Out of scope

- IMP-A / `session_lead`  
- Expanding assign-verb lists  
- Recovery-interim polluted thoughts (has rule → residual R-int)  
- Stricter “post-rule segment only” intentional filter  
- Aligning `intentional_handoff_mentions` vs `intentional_operator_mentions` (sibling)

### Deploy

1. Unit tests green against agency `wake_lib`.  
2. Patch agency wake_lib + rc_operator_agent (+ optional telemetry helper).  
3. Restart **all** operator LaunchAgents (each process loads its own copy).  
4. Live smoke: mid-wake bubble must show `*Thoughts*` prefix; peer must not wake until final with rule or bare intentional final.

### Rollback

Revert wrap + short-circuit delete; keep tests as xfail or remove.

---

## Acceptance

- [ ] Unit table green (including T2-live *after wrap*, F1, F2, F4, R1)  
- [ ] Intermediate paints never bare intentional-looking text  
- [ ] Operators restarted  
- [ ] Live smoke: no mid-stream peer wake; final assign wakes  
- [ ] Feynman re-pass on plans **and** implementation review after code

## Explicit F2 vs T2-live contract

| Situation | Body shape | Wake? |
| --- | --- | --- |
| Intermediate (operator path) | Always `*Thoughts*\n\n` + tail, no rule | **no** |
| Final bare assign | `@peer dig …` only | **yes** |
| Final with thoughts | `*Thoughts*` + … + `────────────────` + answer | **yes** if intentional in body |

Without wrap, F2 and T2-live are indistinguishable — **wrap is mandatory for ship**, not optional polish.
