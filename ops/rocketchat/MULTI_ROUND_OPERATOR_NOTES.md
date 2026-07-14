# Multi-round collab — operator notes (mirror of MULTI_OPERATOR.md section)

Canonical: `~/.grok/agency/ops/rocketchat/MULTI_OPERATOR.md`

## Multi-round collab (all shared rooms)

**Status:** live path (2026-07-14) — medium enforcement: shared playbook + operator return-notify.  
**Distinct from NF-SPEC-10:** this path keeps **tag-to-talk starts** in any shared room (no purpose-room-only untagged lead intake).

| Piece | Path / rule |
| --- | --- |
| Playbook (one protocol for all four) | `wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` |
| Policy helpers | `wake/rc_multi_round_collab.py` |
| Skill | `~/.grok/skills/rc-multi-round-collab/SKILL.md` |
| Reply surfaces | All four `*_reply_prompt.txt` + wake `build_prompt` inject |
| Shared lead-DONE state | `wake/multi_round_collab_state.json` |
| Master switch | `RC_MULTI_ROUND_COLLAB` (default **on**) |

**Behavior:**

1. **Lead = `grok`.** Peers = `hermes` / `agy` / `claude`.
2. **Starts:** still **tag-to-talk** in channels/groups (`@bot` required). Untagged noise does not LLM-wake.
3. **Opening a collab (clean path):** principal tags **only `@grok`**. Lead fans out to peers. If principal multi-@s lead+peers in one message, operator enqueues **lead only** (`RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY`, default **on**). Direct principal→`@peer` (no `@grok`) still wakes that peer.
4. **After a peer finishes** a shared-room wake with a useful reply, the operator posts a short **`@assigner` return-notify** (assigner if that user is a bot; else **`@grok`**) so the chain continues without the principal re-tagging each hop.
5. **Quality gate:** empty / operator-error templates (`Could not complete this reply`, empty `FINAL_ERR`, `rc: 1` templates) **do not** return-notify while the collab is open.
6. **Lead** must re-assign with `@tags` or declare **plain-language DONE** (“This concludes the collab…”, “Goal met…”, etc.). Lead peer-assign opens a **collab epoch** (shared state).
7. After lead DONE, **return-notify is suppressed**; lead does **not** LLM-wake on further `collab-return` or peer “standing by @grok” acks.
8. **Close-out anti-loop (HARD):** Lead DONE messages must include **zero** peer `@tags` (not even “Copy @agy”). Peers must **not** `@grok` on stand-down acks. Tagging on close-out caused an infinite ping-pong in `Prime-Gap-Structure` (2026-07-14 residual-cell-R). Only the **principal** re-opens a closed collab.

**Env (multi-round):**

| Variable | Default | Meaning |
| --- | --- | --- |
| `RC_MULTI_ROUND_COLLAB` | on | Master switch |
| `RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY` | on | Principal multi-@ lead+peers → lead only |
| `RC_MULTI_ROUND_PLAYBOOK` | `wake/RC_MULTI_ROUND_COLLAB_PLAYBOOK.md` | Override playbook path |
| `RC_MULTI_ROUND_STATE` | `wake/multi_round_collab_state.json` | Shared lead-DONE / epoch state |

**Tests:** `ops/rocketchat/tests/test_multi_round_collab.py`  
**Live smoke (optional):** `RC_LIVE_COLLAB_SMOKE=1 python3 ops/rocketchat/tests/live_four_agent_collab_smoke.py`
