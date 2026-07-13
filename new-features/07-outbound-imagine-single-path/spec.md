# Technical Specification: Outbound Imagine / media single path

| Field | Value |
| --- | --- |
| **Spec ID** | **NF-SPEC-07** |
| **Version** | 1.0 |
| **Status** | Specification (helper already partially shipped) |
| **Date** | 2026-07-12 |
| **Enhancement list** | #13 |
| **Test plan** | [NF-TP-07](./test-plan.md) |
| **Impl plan** | [NF-IP-07](./implementation-plan.md) |
| **Primary code** | `wake/rc_post_media.py`, `reply_prompt.txt`, `NO_DUPLICATE_POSTS.md` |
| **Related** | NF-SPEC-05 inbound attachments, IMP-07 secrets hygiene |

---

## 1. Problem

Outbound media must never produce duplicate RC bubbles. Historical failure: double `rooms.mediaConfirm` on one `fileId`.

---

## 2. Goals

| ID | Goal |
| --- | --- |
| G1 | Exactly one confirm per successful new upload. |
| G2 | Same bytes / same fileId in same room cannot create a second message via helper. |
| G3 | Grok wakes have only one documented CLI path for posting media. |
| G4 | Principal-facing policy remains NO DUPLICATE POSTS. |

## 3. Non-goals

- Changing RC server media storage backend.
- Inline images via markdown remote URLs as primary path.
- Multi-file album API beyond sequential helper calls (each call still once-per-file).

---

## 4. Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Outbound post MUST use `python3 …/wake/rc_post_media.py --room-id … --file … [--msg …]`. |
| R2 | Helper MUST call `rooms.media` then **at most one** `rooms.mediaConfirm` per new `fileId`. |
| R3 | Ledger path `~/logs/rocketchat-dm-wake/media-post-ledger.json` MUST record `file_id`, `sha256`, `room_id`, `msg_id`. |
| R4 | If `file_id` already in `confirmed_file_ids`, helper MUST skip confirm and return `skipped: true`. |
| R5 | If same `sha256` already posted to same `room_id`, helper MUST skip upload+confirm (`skipped: true`). |
| R6 | `--force` MAY bypass skips for emergency re-post only; must be explicit. |
| R7 | `reply_prompt.txt` MUST forbid hand-rolled `mediaConfirm` loops and raw multi-confirm probes. |
| R8 | Wake inject MUST continue to state NO DUPLICATE POSTS + helper path. |
| R9 | Optional wrapper `scripts/rc_imagine_post.sh` (or under wake/) MAY chain Imagine output path → helper once; MUST NOT confirm twice. |
| R10 | Operator process MUST NOT auto-post media from Grok stdout; only the wake model invokes helper as a tool/shell step (or future structured side-effect). |

---

## 5. Non-functional

| ID | Requirement |
| --- | --- |
| N1 | Helper exits 0 on success or intentional skip; non-zero on hard failure. |
| N2 | JSON stdout for machine parse: `{success, skipped, file_id, msg_id, reason?}`. |
| N3 | No secrets printed. |

---

## 6. RC API sequence (normative)

```
1. POST /api/v1/rooms.media/{rid}   multipart file
   → { file: { _id, url } }
2. If file._id already confirmed → STOP (skip)
3. POST /api/v1/rooms.mediaConfirm/{rid}/{fileId}
   body: { msg, description }
   → exactly once
4. Append ledger
```

---

## 7. Acceptance criteria

- [ ] Unit: second helper call same bytes → skipped, no second confirm mock.
- [ ] Unit: same fileId re-confirm path skipped.
- [ ] Prompt contains forbid + helper path.
- [ ] Live opt-in: one image appears once in DM.
- [ ] Documented in `NO_DUPLICATE_POSTS.md` and ROCKETCHAT.md.

---

## 8. Security

- Auth only via operator secrets inside helper (not model-printed).
- Caption length soft-cap (e.g. 2000 chars) to avoid abuse.
