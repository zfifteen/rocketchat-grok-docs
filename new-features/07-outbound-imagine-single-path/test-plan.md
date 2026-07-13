# Test plan: Outbound Imagine single path

**Nav:** [README](./README.md) · [Spec](./spec.md)

| Field | Value |
| --- | --- |
| **ID** | **NF-TP-07** |
| **Requirements** | [NF-SPEC-07](./spec.md) |

---

## Preconditions

- `wake/rc_post_media.py` importable.
- Temp ledger path via env override if implemented; else use isolated temp home/ledger mock.

---

## Test cases

### T1 — First post confirms once

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Mock media + confirm HTTP | confirm called **1** time |
| 2 | Ledger contains file_id + sha256 | yes |

**Pass:** R2–R3.

### T2 — Second post same bytes skipped

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Call helper twice same file+room | second `skipped: true` |
| 2 | confirm call count still 1 | yes |

**Pass:** R5.

### T3 — Same fileId not re-confirmed

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Pre-seed ledger confirmed_file_ids | — |
| 2 | Upload returns same id | skip confirm |

**Pass:** R4.

### T4 — Force bypass

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `--force` after successful post | second confirm allowed only with force |

**Pass:** R6.

### T5 — Prompt contract

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Read `reply_prompt.txt` | contains `rc_post_media.py` and NO DUPLICATE / no double confirm |

**Pass:** R7–R8.

### T6 — Live smoke (opt-in `RC_LIVE_MEDIA=1`)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Post tiny png via helper | one bubble |
| 2 | Re-run helper | skip; still one bubble |

---

## Traceability

| Spec | Tests |
| --- | --- |
| R1–R3 | T1, T5 |
| R4–R6 | T2–T4 |
| R7–R8 | T5 |
