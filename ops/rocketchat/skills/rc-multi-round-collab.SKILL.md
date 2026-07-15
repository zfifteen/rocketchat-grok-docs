---
name: rc-multi-round-collab
description: >
  Multi-round Rocket.Chat agent collaboration protocol for grok, hermes, agy, and
  claude. Grok lead, tag-to-talk starts, operator return-notify to assigner|grok,
  plain-language lead DONE with zero peer tags on close-out. Use when collaborating
  in RC channels/groups, handoffs stall, close-out loops, or multi-agent research
  threads need continuation.
---

# RC multi-round collab

## Canonical playbook

**Runtime source of truth (injected on every operator wake):**

`~/.grok/agency/ops/rocketchat/wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md`

**Policy helpers:**

`~/.grok/agency/ops/rocketchat/wake/rc_multi_round_collab.py`

**Roster note:**

`~/.grok/agency/ops/rocketchat/MULTI_OPERATOR.md`

## When this skill applies

- Any shared Rocket.Chat room where two or more of `grok` / `hermes` / `agy` / `claude` work a goal together
- Principal asks for multi-agent collab, handoffs, or “keep going until done”
- Close-out thrash / infinite ack loop after the research goal is finished
- Prior stall pattern: peers answered without re-engaging the lead

## Protocol (short)

1. **Open cleanly** — principal tags **only `@grok`**. Peers wait for lead `@` (operator suppresses peer enqueue on principal multi-@ of lead+peers).
2. **Grok is lead** — owns goal, assigns with `@hermes` / `@agy` / `@claude`, synthesizes returns.
3. **Peers deliver** their slice to the reply file (single bubble). Optional soft footer: `STATUS:` / `FOR:` / `EPOCH:`.
4. **Operator return-notify** re-wakes assigner (if bot) else `@grok` after peer completion (not after DONE; not for pure standing-by; not for empty/error templates).
5. **Lead ends** with plain-language DONE **and zero peer `@tags`** (“This concludes the collab…”, “Goal met. No further handoffs.”).
6. After DONE, peers **stop** — no `@grok` on acks; silence is correct until a **new** task tag.

## Close-out anti-loop (HARD)

**Confirmed failure (Prime-Gap-Structure):** Lead keeps `@`-tagging peers while declaring done → peers wake → peer `@grok` / return-notify → lead wakes → tags peers again → infinite loop.

| Role | Close-out rule |
| --- | --- |
| Lead | DONE text only. **Never** `@hermes` / `@agy` / `@claude` on the close message (not even “Copy @agy”). |
| Peer | **Never** `@grok` on standing-by / copy / “collaboration complete” acks. Prefer silence. |
| Both | Do not re-@ a peer to “retry a failed wake” after the lead has closed the collab. |

## Do

- Use visible `@tags` for **open** intentional handoffs only
- Re-assign **or** declare done every lead turn while the goal is open
- Convert disagreement into a check or residual with an owner
- On DONE: plain-language close with **no** peer tags

## Do not

- Leave a synthesis with neither `@peer` tasks nor a done statement **while work remains**
- Tag peers when declaring DONE / “copy” / “thanks” on close-out
- `@grok` (peer) when only standing by after DONE
- Expect untagged channel chatter to wake bots
- Continue an open collab after lead DONE without a new tag for new work
