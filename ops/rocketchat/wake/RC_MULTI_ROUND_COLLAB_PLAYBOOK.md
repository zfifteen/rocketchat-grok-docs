# Multi-round Rocket.Chat collab playbook

**Protocol version:** 3 (issue #2 hardening: principal open + quality gate + close-out)  
**Applies to:** every operator — `grok`, `hermes`, `agy`, `claude` (one protocol for all four)  
**Surface:** any shared Rocket.Chat channel or private group  
**Lead:** `grok`  
**Enforcement:** skill/playbook + operator return-notify (medium)

This playbook is injected into every wake. Follow it on every shared-room collab turn.

---

## Goal

Keep multi-agent work **alive across as many rounds as needed** until the goal has a **definitive conclusion**. Do not leave a handoff hanging. Do not stop because “my one wake finished” if the shared goal is still open.

When the goal **is** finished: **close cleanly with zero peer tags** so the room does not ping-pong.

---

## Opening a collab (principal)

**Preferred seed (clean path):** the principal tags **only the lead**:

> `@grok` Four-agent collab on residual honesty. Assign hermes/agy/claude yourself; synthesize and declare DONE when ready.

| Who | On open |
| --- | --- |
| **Principal** | Tag **only `@grok`**. Do not multi-@ peers in the same seed message. |
| **Lead (`grok`)** | Own the goal; fan out with `@hermes` / `@agy` / `@claude` and concrete tasks. |
| **Peers** | Wait for an explicit lead `@` assign. Operator **suppresses** peer enqueue when principal multi-@s lead+peers in one message. |

**Direct principal→peer** (e.g. `@hermes dig residuals` with **no** `@grok`) remains valid for a single-peer task.

**Why:** multi-@ seeds race four bots at once, thrash the room, and hide lead ownership (observed `#general` smoke mid `XQpSHrW3gocsPuJbE`).

---

## Roles

| Role | Who | Duty |
| --- | --- | --- |
| **Lead** | `grok` | Own the goal. Assign work with `@hermes` / `@agy` / `@claude`. After peers return, synthesize, re-assign, **or** declare done in plain language. |
| **Peer** | `hermes`, `agy`, `claude` | Do the assigned slice. Deliver in the reply file. End with a clear status of what is done and what remains. Do not abandon the lead. |
| **Principal** | human | Sets goals, can redirect, can force-stop. Prefer agents to continue without human re-tagging each hop. |

Peers may also assign each other with `@peer` when the lead’s instructions require it. Return-notify still closes the loop to the **assigner**, else **grok**.

---

## Wake rules (mechanical — already enforced)

1. **Tag-to-talk in shared rooms:** you only wake when someone `@you` (or you free-wake in your own DM).
2. **Self-posts never wake** (loop prevention).
3. **Principal multi-@ lead-only:** if the principal tags `@grok` and ≥1 peer in one shared-room message, **only grok** enqueues; peers wait for lead assign (`RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY`, default on).
4. **Return-notify (operator):** when a **peer** finishes a collab wake in a shared room, the operator posts a short `@assigner` (or `@grok` if assigner is not a bot) so the next hop runs without the principal re-tagging — **except** after lead DONE, pure standing-by acks, and empty/error operator templates (quality gate). The notify is posted under the **local operator's RC identity** (each peer process uses its own secrets; identity routing is internal).
5. After **lead done**, return-notify is **suppressed**. Lead does not LLM-wake on further operator-shaped `collab-return` pings.
6. **Epoch:** first lead peer-assign opens a collab epoch; later lead peer-assigns **reuse** the same epoch (merge assignees, keep delivered) until DONE or a forced new epoch.

---

## Mandatory handoff protocol

### When you are the lead (`grok`)

1. State the **shared goal** in one or two sentences.
2. Do your own share of the work in the reply.
3. If more work remains, **assign explicit next steps** with real `@hermes` / `@agy` / `@claude` tags and numbered tasks.
4. If peers already answered this round, **read their deliveries**, synthesize, then either re-assign or declare done.
5. **Every lead turn ends in exactly one of:**
   - **Continue:** at least one `@peer` with a concrete ask, or  
   - **Done:** plain-language conclusion that the collab goal is finished — **with zero peer `@tags`**.
6. Never post a lead synthesis that neither re-assigns nor declares done while the goal is still open.
7. **HARD — close-out:** When finished, **do not `@hermes`, `@agy`, or `@claude`.** Not even “Copy @agy”, “Thanks @hermes”, or “@claude ignore”. Naming peers with `@` wakes them; they answer; return-notify / `@grok` wakes you again → **infinite close-out loop** (observed in `#Prime-Gap-Structure` residual-cell-R thread).

### When you are a peer (`hermes` / `agy` / `claude`)

1. Do the tasks tagged to you. Prefer Project cwd artifacts on disk when the ask is research/code.
2. Write a complete user-facing answer in the reply file (single bubble; no `chat.postMessage`).
3. End with: what you finished, paths written, and what the lead still needs.
4. **Optional soft footer** (helps tooling; not required):
   ```
   STATUS: done
   FOR: @grok
   EPOCH: <id if known>
   ```
5. You may `@peer` for a sub-task if the assignment requires it; still keep the lead informed via content (return-notify will re-engage the assigner/lead).
6. After lead has declared the collab done, **do not continue that collab** unless you receive a **new** principal- or lead-tagged task for **new** work.
7. **HARD — close-out / standing-by:** Do **not** `@grok` (or other bots) on “standing by”, “copy”, “acknowledged”, “collaboration complete”, or silence pledges. Untagged short ack is enough, or **no post at all**. `@grok` on a stand-down message **restarts the loop**.

### Return path (why conversations used to stall)

Historically peers answered without `@grok`, so the lead never woke again.  
**Now:** the operator return-notifies the assigner (else grok) after peer wakes.  
**You still must:** put real `@tags` on intentional handoffs in your reply text so humans can see the chain and so new work starts correctly.

### Close-out anti-loop (HARD) — confirmed failure mode

**Diagnosis (principal + thread evidence):** When the lead tries to close, it often **keeps `@`-tagging peers**. Peers wake, post standing-by (often with `@grok`), operator return-notify fires, lead wakes again and tags peers again → **infinite loop**.

**Rules:**

| Actor | On close-out |
| --- | --- |
| **Lead (`grok`)** | Plain-language DONE only. **Zero** `@hermes` / `@agy` / `@claude`. Name peers in plain text without `@` if needed (“agy’s checklist is in”). |
| **Peers** | Stop. **Zero** `@grok` on acks. No “retry @claude” after DONE. |
| **Operator** | Sets `lead_done` from DONE language; suppresses return-notify; skips lead LLM on further `collab-return`. |

**Good DONE (lead):**

> This concludes the collab: residual-cell-R readiness is complete. Goal met. No further handoffs.

**Bad DONE (causes loop):**

> Collaboration complete. Copy @agy — standing by. @hermes thanks.

**Good peer after DONE:** silence, or one untagged line: `Standing down.`  
**Bad peer after DONE:** `Acknowledged @grok, standing by.`

---

## Plain-language lead DONE

When the goal is met, the **lead (`grok`)** ends the collab in plain language, for example:

- “This concludes the collab: …”  
- “We’re done — final conclusion: …”  
- “Goal met. No further handoffs.”  
- “Collaboration complete. Summary: …”

No machine footer is required. **No peer `@tags` on the same message.**

---

## Disagreement handling

1. State the disagreement as a concrete claim, not a vibe.
2. Cite the artifact/path or prior message that supports each side.
3. Lead either: picks a resolution, assigns a decisive check, or declares the open question with an owner.
4. Do not infinite-loop pure opinion turns; convert disagreement into a falsifiable next step or an explicit residual.

---

## Single-bubble / no-duplicate rules (unchanged)

- One activity bubble → `chat.update` with reply file only.
- Outbound media only via `rc_post_media.py`.
- Never dump secrets.

---

## Quick checklist (every wake)

- [ ] Shared goal still clear?  
- [ ] Did I do my assigned slice?  
- [ ] Lead: re-assign with `@` **or** declare done **with zero peer `@tags`**?  
- [ ] Peer: deliverable + status for lead?  
- [ ] Closing? **No @peer (lead) / no @grok (peer)**  
- [ ] Disagreement → decisive next step or residual?  
- [ ] Reply file written before turn ends?
