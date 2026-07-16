# B3 + B10 wake enqueue spec (hermes dig)

**Owner:** hermes (collab assign from lead grok)  
**Date:** 2026-07-15  
**Runtime:** `~/.grok/agency/ops/rocketchat/wake/`  
**Artifacts:** `b3_b10_wake_predicates.py`, `test_b3_b10_wake_predicates.py` (this folder)

## Status

| ID | Summary | Finding | Patch |
| --- | --- | --- | --- |
| B3 | Peers wake on lead activity / intermediate stream | Confirmed root cause | Proposed pure gates (not wired to launchd) |
| B10 | Prose `@bot` re-wakes | Confirmed; tag-to-talk is literal | Proposed intentional-mention for **bot authors** |
| B1 recheck | Glued + structured multi-mention | Residual hole beyond bot-assigner emit | Proposed lead-only uses structured+glued extract |

---

## Trace (current code)

### Entry

`rc_operator_agent.OperatorAgent.on_message` → `stream-room-messages` `changed` → `handle_principal_message` → `should_enqueue_llm_wake` (`wake_lib.py`).

### `should_enqueue_llm_wake` (live)

1. No `_id` → false  
2. Self-post (`user == operator`) → false  
3. No handleable content → false  
4. `last_seen_id` / `processed_ids` hit → false  
5. **Principal:** free-wake unless shared room requires `@op` (`RC_REQUIRE_MENTION`)  
6. **Anyone else:** `RC_PEER_TAG_WAKE` (default on) **and** `message_mentions_operator`

### `message_mentions_operator` (live)

True if **either**:

- structured `mentions[]` contains operator, **or**
- body matches `(?<!\w)@([A-Za-z0-9._-]+)\b` equal to operator

No author-role split. No intentional vs prose distinction. No activity-shell filter.

### Activity / stream path (B3)

1. Operator posts activity bubble via `post_thinking_placeholder` → body `…` (`ACTIVITY_PLACEHOLDER`), **author = that bot**.  
2. Same `msgId` is `chat.update`d with intermediate thought text (`format_thought_intermediate` / stream tail), then final answer.  
3. Websocket delivers `stream-room-messages` **changed** events for updates. Handler does **not** special-case edits.  
4. `_enqueue_pending` blocks re-queue of the **same mid** once pending/in-flight/processed — but the **first** body that contains `@peer` wins.  
5. Pure `…` does **not** match mentions → no enqueue (good).  
6. Intermediate body that **quotes or drafts** `@hermes …` (or starts with `*Thoughts*` and includes prose `@hermes`) **does** match mentions → peer enqueues **before final assign is stable**. That is B3.  
7. Observed thrash shape: lead synthesis / recovery text that *discusses* `@hermes` mid-sentence re-wakes hermes (also B10).

### Prose @bot (B10)

Literal text match wakes on:

- `the principal's @hermes direct requests`  
- `` mention of `@agy` is prose `` (backticks still match regex)  
- any bot explanation that names `@claude` / `@hermes` / `@agy` / `@grok`

Intentional lead assigns also match (desired):

```text
@hermes please dig **B3** ...
```

### Processed timing

`_enqueue_pending` does **not** mark processed until drain finishes. In-flight/pending dedupe same mid. Cross-operator: each bot has **its own** state file — grok’s activity mid is fresh on hermes until hermes processes it.

---

## Exact proposed predicates

See `b3_b10_wake_predicates.py`.

### G1 — activity shell (B3)

`is_activity_or_stream_shell(text)` true for empty, `…`, `Thinking...`, trivial placeholders → **never enqueue**.

### G2 — non-final stream chrome (B3)

`looks_like_nonfinal_stream(text)` true when body starts with `*Thoughts*`, `Thinking`, `Recovery wake`, `PHASE:` (unless a hard line-start `@op` assign is also present) → **bot-authored** messages do not enqueue peers.

### G3 — intentional mention for bot authors (B10)

When `author ∈ {grok,hermes,agy,claude}`:

`message_mentions_operator_intentional` requires `@op` via:

- line-start `@op`, or  
- `@op` + assign verb (`please dig|own|fix|trace|…`), or  
- collab-return template `@op collab-return from …`

Principal / other humans: keep **literal** any-`@op` (channel tag-to-talk UX).

### G4 — B1 lead-only must use full mention set

`principal_multi_mention_lead_only` today uses **text-only** `extract_mention_usernames`. Holes:

| Case | Text extract | Structured mentions[] | Peer enqueue today | Desired |
| --- | --- | --- | --- | --- |
| `@grok @hermes collab` | {grok,hermes} | both | peer **skipped** by lead-only | skip peer |
| `@grok@hermes collab` (glued) | often {grok} only | may be both | peer may enqueue via mentions[] while lead-only sees no peer | skip peer |
| text `@grok fan out` + mentions[] hermes+grok | {grok} | {grok,hermes} | **peer enqueues** (hole) | skip peer |
| `@hermes dig` only | {hermes} | hermes | peer enqueues | enqueue (solo) |

Proposed: union structured + text + glued-run splitter; then same lead∈mentions ∧ peers∩mentions ⇒ peers skip.

---

## Kill cases (must pass)

| # | Author | Body (shared channel) | Op under test | Enqueue? |
| --- | --- | --- | --- | --- |
| K1 | grok | `…` | hermes | no |
| K2 | grok | `Thinking...` | hermes | no |
| K3 | grok | `*Thoughts*\n… need @hermes later` | hermes | no |
| K4 | grok | `principal's @hermes direct requests…` | hermes | no |
| K5 | grok | `@hermes please dig B3` | hermes | **yes** |
| K6 | hermes | `@grok collab-return from hermes · mid=x` | grok | **yes** |
| K7 | principal | `@hermes you up?` | hermes | **yes** |
| K8 | principal | `you up?` (channel) | hermes | no |
| K9 | principal | `@grok @hermes collab` | hermes | lead-only **skip** (enqueue false at agent layer) |
| K10 | principal | `@grok@hermes collab` glued | hermes | lead-only **skip** (after glue fix) |
| K11 | hermes | `@hermes dig` (self) | hermes | no |
| K12 | grok | final multi-line assign starting `@agy please own B2` | agy | **yes** |

---

## Wire-in plan (minimal)

1. Add helpers to `wake_lib.py` (or import from shared module).  
2. In `should_enqueue_llm_wake`, after handleable-content checks:  
   - if shell → false  
   - if author bot and nonfinal stream → false  
   - replace bare `message_mentions_operator` with intentional variant when author is bot  
3. In `principal_multi_mention_lead_only`, accept optional `msg` / structured mentions; use `extract_all_mention_usernames` + glued recovery.  
4. Port pure tests into `ops/rocketchat/tests/test_multi_round_collab.py` or keep this folder’s suite in CI.  
5. Restart all four operators after wire-in.

**Do not** require structured mentions for principal (mobile clients sometimes omit them).  
**Do not** disable peer tag-wake globally (`RC_PEER_TAG_WAKE=0` is too blunt).

---

## B1 adversarial re-check (emit path already fixed)

`should_emit_return_notify` bot-assigner gate (mirror + runtime): principal-direct → peer does **not** return-notify. Re-verified by lead; hermes did not re-open that path.

Remaining B1-adjacent: **enqueue** multi-mention hole above (lead-only text-only). Separate from return-notify emit.

---

## What lead still needs

1. Review proposed predicates; wire into runtime `wake_lib` / `rc_multi_round_collab`.  
2. Run pure suite:  
   `python3 docs/improvements/21-operator-interaction-bugs-2026-07-15/test_b3_b10_wake_predicates.py`  
3. Optional: live smoke — lead posts activity `…`, intermediate `*Thoughts* … @hermes …`, then final `@hermes please dig …`; peers must wake **only** on final intentional assign.  
4. agy/claude slices (B2/B7, B4/B5) independent.

No launchd restart performed by hermes this turn (proposal + pure tests only).
