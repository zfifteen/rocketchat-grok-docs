# Feature 04 — Antigravity (agy) dual-peer collab via Rocket.Chat channel

**Bundle home:** `new-features/04-agy-rocketchat-collab/`  
**Status:** Documentation only (no runtime implementation in this package)  
**Parent index:** [`../README.md`](../README.md)

Long-horizon Grok↔`agy` collab: dual accounts, @mention handoffs, many-turn durable sessions.

## Documents in this bundle

| Layer | File | ID |
| --- | --- | --- |
| **Research** | [research.md](./research.md) | — |
| **Technical specification** | [spec.md](./spec.md) | **NF-SPEC-04** |
| **Test plan** | [test-plan.md](./test-plan.md) | **NF-TP-04** |
| **Draft identity profiles** | [profiles/](./profiles/) | L2 social contract drafts |
| **Implementation plan** | *(deferred)* | NF-IP-04 |

## Preferred product model (snapshot)

| Piece | Choice |
| --- | --- |
| **Value prop** | Long-horizon multi-turn inter-agent collab — not one-shot Q&A |
| New RC account | **`agy`** (bot user) |
| Channel | e.g. `#grok-agy-collab` with `principal`, `grok`, `agy` |
| Wake rule | **Tag to talk** — `@agy` / `@grok` wake matching backends |
| Bot handoff | Replies `@`-tag the peer for continued auto-handoff |
| Depth | Soft epoch budgets + spin detection (not tiny hard hop caps) |
| Backend for `agy` | Local **`agy` CLI** only (never MCP `agy_*`) |
| Backend for `grok` | Existing Grok CLI wake path |
| Posting | Each identity owns Thinking… → `chat.update` |
| **Identity profile** | Durable `agy` AGENTS/agent.md + Grok collab inject |

Normative requirements: [spec.md](./spec.md). Rationale / options: [research.md](./research.md).

## Suggested reading order

1. [research.md](./research.md) — why / options / C3 recommendation  
2. [spec.md](./spec.md) — normative shalls, architecture, acceptance  
3. [test-plan.md](./test-plan.md) — how to prove FR-A* / AC-A* (NF-TP-04)  
4. [profiles/](./profiles/) — draft L2 identity for `agy` and Grok inject  

## Explicit non-goals of this package

- Implementing channel wiring, operator patches, launchd, or RC user creation  
- Installing draft profiles into `~/.gemini` or production `wake/`  
- Replacing the CLI-only `agy-cli-collab` skill with MCP  
- Implementation plan (NF-IP-04 deferred)  

## Related live systems (unchanged)

| System | Path / note |
| --- | --- |
| Operator | `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` (principal-only today) |
| One-bubble rule | `NO_DUPLICATE_POSTS.md` (per-speaker under this feature) |
| Channel map | `wake/channel_projects.json` |
| Skill | `~/.grok/skills/agy-cli-collab/` |
| Stack docs | [`../../docs/architecture.md`](../../docs/architecture.md), [`../../docs/message-flow.md`](../../docs/message-flow.md) |
| All features | [`../README.md`](../README.md) |
