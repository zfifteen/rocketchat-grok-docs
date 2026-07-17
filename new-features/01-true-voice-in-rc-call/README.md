# Feature 01 — True voice-in-RC Call

**Status: RETIRED / WONTFIX — 2026-07-17**  
**Not on the product roadmap.**

Principal decision: no voice/Call integration feature. Runtime hard gates:

- `RC_CALL_ENABLED` default **off**
- `RC_PUBLIC_VOICE` default **off**
- VideoConf settings disabled
- `voice_room` launchd disabled

Canonical policy: `~/.grok/agency/ops/rocketchat/VOICE_RETIRED.md`

The documents below remain as **historical archive** only (research / rejected design).  
Do **not** implement NF-IP-01 or schedule Call work without reinstating this feature in the index with principal approval.

## Documents in this bundle (archive)

| Layer | File | ID |
| --- | --- | --- |
| **Research** | [research.md](./research.md) | — |
| **Technical specification** | [spec.md](./spec.md) | NF-SPEC-01 |
| **Test plan** | [test-plan.md](./test-plan.md) | NF-TP-01 |
| **Implementation plan** | [implementation-plan.md](./implementation-plan.md) | NF-IP-01 |

## Related

- Live system: text/operator only — [`../../docs/architecture.md`](../../docs/architecture.md)  
- Runtime: `~/.grok/agency/ops/ROCKETCHAT.md`  
- All features: [`../README.md`](../README.md)
