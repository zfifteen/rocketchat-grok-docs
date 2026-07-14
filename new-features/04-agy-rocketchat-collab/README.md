# Feature 04 — Antigravity (agy) dual-peer collab via Rocket.Chat channel

**Bundle home:** `new-features/04-agy-rocketchat-collab/`  
**Status:** Implemented in production operator (`rc_operator_agent.py` supports `RC_WAKE_BACKEND=agy`)  
**Parent index:** [`../README.md`](../README.md)

Long-horizon Grok↔`agy` collab: dual accounts, @mention handoffs, many-turn durable sessions.

**v1 purpose-created room protocol (lead + full peer):** see **[NF-SPEC-10](../10-lead-peer-full-collab/spec.md)** — untagged principal goals → **Grok lead intake**; **AGY full peer** with peer bar (not add-on). NF-SPEC-04 remains baseline dual-identity / CLI-only primitives; where they conflict on `lead_peer_full` rooms, **NF-SPEC-10 wins**.

## Documents in this bundle

| Layer | File | ID |
| --- | --- | --- |
| **Research** | [research.md](./research.md) | — |
| **Technical specification** | [spec.md](./spec.md) | **NF-SPEC-04** (baseline) |
| **v1 room protocol (normative for #grok-agy-collab)** | [../10-lead-peer-full-collab/spec.md](../10-lead-peer-full-collab/spec.md) | **NF-SPEC-10** |
| **Enablement** | [../09-agy-collab-enablement/](../09-agy-collab-enablement/) | **NF-SPEC-09** |
| **Test plan** | [test-plan.md](./test-plan.md) | **NF-TP-04** |
| **Draft identity profiles** | [profiles/](./profiles/) | L2 social contract drafts |
| **Implementation plan** | *(deferred; see NF-SPEC-10 §12)* | NF-IP-04 / NF-IP-10 |

## Preferred product model (snapshot)

| Piece | Choice |
| --- | --- |
| **Value prop** | Long-horizon multi-turn inter-agent collab — not one-shot Q&A |
| New RC account | **`agy`** (bot user) |
| Channel | e.g. `#grok-agy-collab` with `principal`, `grok`, `agy` |
| **v1 wake rule** | **Lead intake** — untagged principal → Grok; handoffs via `@agy` / `@grok` (**NF-SPEC-10**) |
| Bot handoff | Replies `@`-tag the peer for continued auto-handoff |
| Peer utilization | **Full peer** — peer bar + adversarial pass; not optional LGTM |
| Depth | Soft epoch budgets + spin detection (not tiny hard hop caps) |
| Backend for `agy` | Local **`agy` CLI** only (never MCP `agy_*`) |
| Backend for `grok` | Existing Grok CLI wake path |
| Posting | Each identity owns Thinking… → `chat.update` |
| **Identity profile** | Durable `agy` AGENTS/agent.md + Grok collab inject |

Normative baseline: [spec.md](./spec.md). **v1 channel protocol:** [NF-SPEC-10](../10-lead-peer-full-collab/spec.md). Rationale / options: [research.md](./research.md).

## Suggested reading order

1. [research.md](./research.md) — why / options / C3 recommendation  
2. [spec.md](./spec.md) — normative shalls, architecture, acceptance  
3. [test-plan.md](./test-plan.md) — how to prove FR-A* / AC-A* (NF-TP-04)  
4. [profiles/](./profiles/) — draft L2 identity for `agy` and Grok inject  

## Related live systems (unchanged)

| System | Path / note |
| --- | --- |
| Operator | `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` (principal-only today) |
| One-bubble rule | `NO_DUPLICATE_POSTS.md` (per-speaker under this feature) |
| Channel map | `wake/channel_projects.json` |
| Skill | `~/.grok/skills/agy-cli-collab/` |
| Stack docs | [`../../docs/architecture.md`](../../docs/architecture.md), [`../../docs/message-flow.md`](../../docs/message-flow.md) |
| All features | [`../README.md`](../README.md) |
