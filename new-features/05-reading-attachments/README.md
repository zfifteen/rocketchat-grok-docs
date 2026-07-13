# Feature 05 — Reading attachments in Rocket.Chat

**Bundle home:** `new-features/05-reading-attachments/`  
**Status:** Runtime **shipped** on the live operator (2026-07-12) — docs package remains the normative design trail  
**Parent index:** [`../README.md`](../README.md)

When the principal sends a picture or file, Grok must be able to view it: rehydrate RC payloads, download under policy, inject local paths (and typed errors), and require `read_file` in the wake contract.

## Documents in this bundle

| Layer | File | ID |
| --- | --- | --- |
| **Research** | [research.md](./research.md) | — |
| **Technical specification** | [spec.md](./spec.md) | **NF-SPEC-05** |
| **Test plan** | [test-plan.md](./test-plan.md) | **NF-TP-05** |
| **Implementation plan** | [implementation-plan.md](./implementation-plan.md) | **NF-IP-05** |

## Preferred product model (snapshot)

| Piece | Choice |
| --- | --- |
| **Value prop** | Phone attach photo/file → Grok actually sees content |
| Ownership | Operator inbound pipeline (not Grok + secrets curl) |
| Images | Download → cache → path inject → Grok `read_file` |
| Voice notes | Keep Path A Whisper |
| Documents | Download + path (+ optional excerpt / PDF extract) |
| Limits | Max bytes / max files / same-host only |
| Outbound | Unchanged `rc_post_media.py` ledger |

Normative requirements: [spec.md](./spec.md). Rationale / options: [research.md](./research.md).

## Suggested reading order

1. [research.md](./research.md) — baseline, live 2026-07-11 evidence, A2 recommendation  
2. [spec.md](./spec.md) — normative shalls, flags, acceptance  
3. [test-plan.md](./test-plan.md) — how to prove FR-A* / AC-A* (NF-TP-05)  
4. [implementation-plan.md](./implementation-plan.md) — P0–P2 build, flags, rollback  

## Explicit non-goals of this package

- Implementing download/classify/prompt changes in production operator code  
- Changing launchd, secrets, or RC admin settings  
- Full AV sandbox or non-voice video understanding  
- Replacing outbound media helper  

## Related live systems (unchanged by this docs package)

| System | Path / note |
| --- | --- |
| Operator | `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` |
| Helpers | `wake/wake_lib.py` (`extract_*`, `compose_wake_user_text`) |
| Outbound media | `wake/rc_post_media.py` |
| One-bubble rule | `NO_DUPLICATE_POSTS.md` |
| Attachment cache (live) | `~/logs/rocketchat-dm-wake/attachments/` |
| Stack docs | [`../../docs/architecture.md`](../../docs/architecture.md), [`../../docs/message-flow.md`](../../docs/message-flow.md) |
| All features | [`../README.md`](../README.md) |
