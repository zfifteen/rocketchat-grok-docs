# Implementation plan: Outbound Imagine single path

**Nav:** [README](./README.md) · [Spec](./spec.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | **NF-IP-07** |
| **Effort** | S |
| **Already shipped** | `rc_post_media.py`, prompt block, ledger, NO_DUPLICATE_POSTS.md |

---

## Remaining work

1. **Unit tests** for ledger skip (T1–T4) with mocked HTTP — currently under-specified in suite.
2. **Optional** `wake/rc_imagine_post.py` or shell: args `--room-id` + image path (generation stays in Grok Imagine tool; script only posts).
3. **Ledger env override** `RC_MEDIA_LEDGER` for tests.
4. **Docs sync** — ROCKETCHAT.md outbound section points at this NF-SPEC-07.
5. **Optional health check** — count `mediaConfirm` in wake-run logs outside helper (warn only).

## Rollback

Remove wrapper only; helper remains. Prompt text stays.

## Definition of done

NF-TP-07 T1–T5 green; T6 optional live once.
