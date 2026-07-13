# Research: Outbound Imagine single path

**Nav:** [README](./README.md) · [Spec](./spec.md)

| Field | Value |
| --- | --- |
| **ID** | NF-R-07 |
| **Date** | 2026-07-12 |
| **Enhancement #** | 13 |

---

## Problem

RC 8.6: `rooms.media` + `rooms.mediaConfirm` is the upload path (`rooms.upload` 404). Confirming the same `fileId` twice creates **two** messages. Headless Grok can still invent probe loops.

## Current mitigations

- `wake/rc_post_media.py` — single confirm + ledger (`media-post-ledger.json`)
- `reply_prompt.txt` NO DUPLICATE POSTS block
- `NO_DUPLICATE_POSTS.md` + INVALIDATED.md

## Gaps

- No first-class “Imagine then post” wrapper for models
- No automated test that double helper invoke is idempotent in unit form (ledger)
- No runtime detection of forbidden raw confirm in wake logs

## Recommendation

1. Keep helper as **only** allowed path (spec R1).  
2. Add thin wrapper script for Imagine→post.  
3. Unit-test ledger skip paths.  
4. Optional log scanner for `mediaConfirm` outside helper (ops health).
