# Feature 5 — Reading attachments in Rocket.Chat (inbound media → Grok can view)

**Status:** Research only (no runtime implementation in this document set)  
**Date:** 2026-07-11 · **Last reviewed:** 2026-07-11  
**Stack baseline:** Rocket.Chat **8.6** + operator `rc_operator_agent.py`; Path A voice notes (Whisper); partial image download → path inject; Grok CLI `read_file` multimodal for images; single-bubble `Thinking…` → reply file → `chat.update`  
**Hard rules preserved:** `NO_DUPLICATE_POSTS.md` (one answer bubble); outbound media only via `rc_post_media.py`; principal-only wake (except collab rooms); no secrets in bubble or reply file

### Downstream documentation (normative chain)

| Layer | Document | ID |
| --- | --- | --- |
| **Spec** | [spec.md](./spec.md) | **NF-SPEC-05** |
| **Test plan** | [test-plan.md](./test-plan.md) | **NF-TP-05** |
| **Implementation plan** | [implementation-plan.md](./implementation-plan.md) | **NF-IP-05** |

**Canonical recommended direction:** **A2 — harden and complete the existing operator inbound pipeline** (rehydrate → classify → download → type-specific ingest → explicit wake inject + `reply_prompt` contract). Prefer local paths + Grok tools over re-uploading bytes into the model API. Do **not** invent a second outbound path.

---

## 1. Problem framing (against the live stack)

### 1.1 Product requirement (hard)

When the principal sends Grok a **picture or a file** in Rocket.Chat (DM or watched channel), Grok must be able to **actually view / use the content** — not only see a caption that says “I attached something.”

| Principal action | Expected Grok capability |
| --- | --- |
| Photo / screenshot (JPEG, PNG, HEIC, …) | Describe, OCR-ish read, answer questions about pixels |
| Document (PDF, text, markdown, code) | Read text content and reason about it |
| Spreadsheet / data file | Open and summarize (within size limits) |
| Voice note | Already Path A: STT → text wake (keep) |
| Mixed caption + attachment(s) | Caption + attachment content both in context |

This is **phone-first agency messaging**. Attachment literacy is table stakes for “Grok is my remote operator,” not a nice-to-have.

### 1.2 What the principal experiences today (evidence)

Live stack already has **partial** image plumbing and **working** voice-note STT. Product behavior is still unreliable.

| Observation (2026-07-11, principal DM) | Evidence |
| --- | --- |
| Text “Can you view this image?” without (or without detected) file | Operator logged `audio=0`; wake ran caption-only |
| Text “I attached an image…” with upload | Wake prompt **`wake-prompt-1783806806.txt`** contained caption only — **no** `[Image attachment(s) — open each path…]` block |
| Later same minute | Operator log: `image downloaded …IMG_1651.jpg` **and** `…thumb-IMG_1651.jpg` under `~/logs/rocketchat-dm-wake/attachments/` |
| Thumb filter intent vs reality | `extract_image_file_candidates` **should** skip `thumb-*` names; both full + thumb hit disk |
| Wake outcome for attach message | Empty reply file; operator **restarted** mid-wake (`operator agent starting` ~11s after downloads); no clean FINAL_OK for that turn |
| Docs baseline | [`docs/message-flow.md`](../../docs/message-flow.md) documents Path A voice + outbound `rc_post_media.py`; **inbound images/files are undocumented** |

**Net:** Code for download + inject exists, but end-to-end “principal attaches → Grok sees pixels” is **not a trustworthy product surface** yet. Generic non-image files are effectively **unsupported**.

### 1.3 Why this is a product gap (not mere polish)

| Gap | Impact |
| --- | --- |
| Caption-only wake when upload present | Grok invents “I can’t see attachments” answers while files sat on RC |
| No generic file path | PDFs, logs, patches, CSVs cannot drive work from phone |
| `reply_prompt.txt` teaches **outbound** media only | Model not instructed to `read_file` inbound paths |
| Sparse DDP payloads | WS events often omit `file` / `attachments`; rehydrate is mandatory |
| Thumb / multi-file noise | Extra tokens, wrong “primary” image, wasted turns |
| No size / type / retention policy | Disk fill, malware risk, multi-GB uploads |
| Thin tests | Voice candidates covered; image compose + download path under-tested |

### 1.4 Non-negotiable constraints

1. **One answer bubble** — Thinking… → reply file → `chat.update` only (`NO_DUPLICATE_POSTS`).  
2. **Outbound media** remains **only** `rc_post_media.py` (ledgered). Inbound is the inverse problem.  
3. **Principal-only** trust for normal rooms (collab mention rules unchanged — Feature 4).  
4. **Restricted approval** default (`--permission-mode auto`); no secrets in inject.  
5. Attachments must not become a **second reply channel** (no auto-repost of received files).  
6. Work remains in **Project cwd** for code; attachment cache may live under log dir with clear retention.

---

## 2. Current baseline / interfaces (precise)

### 2.1 Operator components (shipped)

| Piece | Path | Role today |
| --- | --- | --- |
| Operator | `wake/rc_operator_agent.py` | WS intake, Thinking…, wake, finalize |
| Shared helpers | `wake/wake_lib.py` | `extract_file_candidates`, audio/image filters, `compose_wake_user_text` |
| Download | `download_rc_file` in operator | GET `title_link` or `/file-upload/{id}/{name}` with `X-Auth-Token` + `X-User-Id` |
| Rehydrate | `fetch_message_by_id` → `GET /api/v1/chat.getMessage` | Full payload when stream omits files |
| Resolve | `resolve_message_text_for_wake` | Caption + Whisper STT + image path list |
| Audio cache | `~/logs/rocketchat-dm-wake/audio/` | Voice note binaries + STT side dirs |
| Attachment cache | `~/logs/rocketchat-dm-wake/attachments/` | Downloaded images (observed live) |
| Outbound media | `wake/rc_post_media.py` | `rooms.media` + **one** `mediaConfirm` |
| Reply rules | `wake/reply_prompt.txt` | Outbound media rules; **no inbound “always read paths” rule** |

### 2.2 Message payload surfaces (Rocket.Chat 8.6)

Upload messages typically expose overlapping shapes:

| Field | Notes |
| --- | --- |
| `msg` | Caption text (may be empty for pure uploads / voice notes) |
| `file` | Single `{_id, name, type}` |
| `files[]` | Multi-file / RC-normalized list (often includes full + thumb) |
| `attachments[]` | Presentation: `title`, `title_link`, `image_url`, `image_type`, nested `file`, audio/video URLs |

`extract_file_candidates` already unions `file` + `files[]` + `attachments[]` and parses `/file-upload/{id}/…` from links. That design is sound.

### 2.3 Download contract (RC)

| Item | Fact |
| --- | --- |
| URL forms | Absolute/relative `title_link`; or `{BASE}/file-upload/{fileId}/{filename}` |
| Auth | REST headers **`X-Auth-Token`**, **`X-User-Id`** (same as other operator REST) |
| Access control | File links return **403** without session auth on locked-down instances ([community reports](https://forums.rocket.chat/t/file-system-attachments-access-denied/9811)); operator must always send headers |
| Upload (outbound) | `POST /api/v1/rooms.media/{rid}` then `rooms.mediaConfirm` — **not** used for inbound |

Operator’s `download_rc_file` matches this contract. Gaps are **classification, reliability, size limits, and wake integration**, not inventing a new download URL scheme.

### 2.4 Type handling matrix (as of 2026-07-11)

| Kind | Detect | Download | Ingest into wake text | Grok action expected |
| --- | --- | --- | --- | --- |
| Audio / voice note | `extract_audio_file_candidates` | `AUDIO_CACHE_DIR` | Whisper → `[Voice note transcript]` | Read transcript in prompt |
| Still image | `extract_image_file_candidates` | `ATTACHMENTS_DIR` | Path list + “use `read_file`” instruction | **Must** call `read_file` on path |
| PDF / office / code / other | Only in generic `extract_file_candidates` | **No** | **No** (falls through to caption or empty-attachment stub) | None |
| Video (non-voice) | May look like audio if `video/mp4` | Partial STT path | Unreliable | Unspecified |

Empty pure-attachment without audio/image after resolve:

```text
(Received a message with an attachment but no text and no
transcribable audio. Re-send as a voice note or with a caption.)
```

That stub is **wrong** once generic files are in scope — it tells the principal the system is blind to PDFs/logs.

### 2.5 Grok CLI consumption model

| Input type | Practical mechanism |
| --- | --- |
| Images | Local path + Grok **`read_file`** (multimodal / vision on image files) |
| Text-like files | `read_file` / shell read within approval mode |
| PDF | `read_file` if runtime supports PDF text/page images; else local extract (pdfplumber / `pdftotext`) **before** wake inject |
| Binary opaque | Metadata only + “cannot parse” unless a converter exists |

**Implication:** Operator should **materialize trusted local paths** (and optionally **pre-extract text**) rather than relying on Grok to authenticate to Rocket.Chat’s `/file-upload/` itself (Grok must not use bot tokens from secrets).

### 2.6 Related docs / adjacent features

| Doc / feature | Relationship |
| --- | --- |
| Path A voice notes | Same rehydrate + download spine; keep STT |
| Feature 2 streaming | Long OCR/PDF wakes benefit from WORKING meta |
| Feature 3 control plane | Optional `/attach status` later; not required for v1 |
| Feature 4 collab | Attachment reading should work for principal messages in collab rooms; bot↔bot file handoff is out of scope for v1 |
| Outbound `rc_post_media` | Orthogonal; do not conflate inbound cache with media-post ledger |

---

## 3. Candidate technical approaches

### Approach A0 — Status quo (partial images + voice)

| | |
| --- | --- |
| **Idea** | Keep current `resolve_message_text_for_wake`; hope rehydrate + path inject works |
| **Pros** | Zero new code |
| **Cons** | Live failure already observed; no PDFs; thumbs; weak prompt contract; thin tests |
| **Verdict** | **Reject** as product end-state |

### Approach A1 — Grok fetches RC URLs itself

| | |
| --- | --- |
| **Idea** | Inject `title_link` URLs; instruct Grok to curl with auth |
| **Pros** | Operator stays thin |
| **Cons** | Forces secrets into tool env or broken 403s; multiplies auth bugs; violates “don’t open secrets” prompt rule |
| **Verdict** | **Reject** |

### Approach A2 — Operator inbound pipeline (recommended)

| | |
| --- | --- |
| **Idea** | On every handleable message: rehydrate → classify → download under policy → type handlers → structured inject → prompt rules force consumption |
| **Pros** | Matches existing architecture; testable pure helpers; auth stays in operator; works offline from RC after download |
| **Cons** | Disk + retention policy required; type matrix grows |
| **Verdict** | **Preferred** |

Pipeline sketch:

```
principal message (WS)
  → enqueue (store mid; may store sparse file meta)
  → drain:
      chat.getMessage(mid)          # always when mid present
      extract_file_candidates
      classify: audio | image | document | binary | skip(thumb)
      download_rc_file (size cap, mime allowlist)
      ingest:
         audio → Whisper transcript
         image → local path (+ optional dimension probe)
         text/code → optional inline excerpt or path
         pdf → text extract or path for read_file
      compose_wake_user_text(...)
      Thinking… → Grok wake (reply_prompt requires open paths)
      chat.update final
```

### Approach A3 — Vision / file API direct to xAI without local cache

| | |
| --- | --- |
| **Idea** | Operator POSTs bytes to model multimodal endpoint, bypassing Grok CLI tools |
| **Pros** | Guaranteed vision without relying on model tool use |
| **Cons** | Forks away from CLI wake model; session/resume complexity; larger rewrite; harder restricted-mode story |
| **Verdict** | **Defer** (optional v2 if path inject proves flaky after prompt fixes) |

### Approach A4 — Apps-Engine / webhook media bot

| | |
| --- | --- |
| **Idea** | RC app receives file events and pushes to operator |
| **Pros** | Richer event metadata |
| **Cons** | New deploy surface; overkill for single-principal Mac stack |
| **Verdict** | **Reject for v1** |

### Approach comparison

| Criterion | A0 | A1 | **A2** | A3 | A4 |
| --- | --- | --- | --- | --- | --- |
| Fits operator architecture | partial | no | **yes** | weak | no |
| Auth safety | ok | bad | **ok** | ok | ok |
| Image reliability | low | low | **high** | high | med |
| Generic files | no | no | **yes** | partial | yes |
| Testability | low | low | **high** | med | low |
| Effort | 0 | med | **med** | high | high |

---

## 4. Integration points

### 4.1 Primary code touch points

| Area | Change class |
| --- | --- |
| `wake_lib.extract_*` | Thumb skip hardening; document/code classifiers; size metadata if present |
| `compose_wake_user_text` | Add `file_paths` / `file_errors` / optional `file_excerpts` (not only images) |
| `resolve_message_text_for_wake` | Unified attachment resolver; never silent-drop non-audio/non-image files |
| `download_rc_file` | Max bytes, content-type check, optional stream-to-disk; safer URL allowlist (same host as `BASE_HTTP`) |
| `_process_pending_item` | Ensure queue item always rehydrates by mid; log `image=` / `files=` counts |
| `reply_prompt.txt` | **Inbound** rule: if inject lists attachment paths, **must** `read_file` them before answering “I can’t see” |
| Usability / integration tests | Fixtures for sparse WS + full getMessage; image; PDF; thumb skip; size reject |
| `docs/message-flow.md` | New section **F. Inbound attachments** (docs package may land with feature ship) |

### 4.2 Config flags (proposed)

| Flag | Default | Purpose |
| --- | --- | --- |
| `RC_ATTACH_ENABLED` | `1` | Master switch for inbound attachment ingest |
| `RC_ATTACH_MAX_BYTES` | e.g. `20971520` (20 MiB) | Per-file download cap |
| `RC_ATTACH_MAX_FILES` | e.g. `5` | Per-message cap |
| `RC_ATTACH_IMAGE` | `1` | Image path inject |
| `RC_ATTACH_DOCS` | `1` | Non-image document download |
| `RC_ATTACH_PDF_EXTRACT` | `0` then `1` after soak | Pre-extract PDF text into inject |
| `RC_ATTACH_INLINE_MAX_CHARS` | e.g. `12000` | Max text excerpt inlined into wake prompt |
| `RC_ATTACH_RETENTION_HOURS` | e.g. `72` | Cache prune (ties IMP-08 log retention spirit) |
| `RC_ATTACH_ALLOW_MIME` / denylist | sensible defaults | Block executables / archives if desired |

### 4.3 Interaction with wake queue / streaming

- Attachment resolve must complete **before** building wake prompt (today’s intended order).  
- Live anomaly (downloads during an already-running wake / empty reply) must be treated as a **reliability bug class** in the test plan (restart safety, rehydrate before Popen).  
- Feature 2 meta text **should** eventually say `attachments: 2 images` during RUNNING_META (nice-to-have; not a v1 blocker).

### 4.4 Collab / multi-identity

v1: principal-originated attachments only (same principal filter).  
Out of scope: `agy` posting files to `grok` (Feature 4 extension).

---

## 5. Risks and failure modes

| ID | Risk | Mitigation |
| --- | --- | --- |
| R1 | Sparse WS → miss files | Always `chat.getMessage` when mid present; unit-test sparse fixture |
| R2 | Thumb + full double ingest | Skip `thumb-*` / size heuristics / prefer largest image per stem |
| R3 | Model ignores path list | Hard rule in `reply_prompt` + optional wake-time checklist in inject |
| R4 | Huge uploads fill disk | `RC_ATTACH_MAX_BYTES` + retention prune |
| R5 | Malicious file content | No auto-execute; restricted mode; mime allowlist; no secrets paths |
| R6 | HEIC / exotic image codecs | Convert with `sips`/`magick` if `read_file` fails; or accept JPEG/PNG first |
| R7 | PDF binary useless in plain read | Optional extract path; clear error in inject if unreadable |
| R8 | SSRF via `title_link` | Restrict download host to configured `RC_BASE` / `BASE_HTTP` |
| R9 | Operator restart mid-download/wake | Idempotent cache names; don’t mark processed until finalize; observability |
| R10 | Channel vs DM cwd confusion | Attachment cache stays under log dir; **not** project cwd (avoid polluting IdeaProjects) |
| R11 | Empty-attachment stub misleads | Replace with typed “unsupported / failed download / oversize” messages |
| R12 | Security of logging paths | Log basenames + sizes, not full binary; never log tokens |

---

## 6. Open questions

| ID | Question | Default if undecided |
| --- | --- | --- |
| OQ1 | Inline text excerpts vs path-only for code/PDF? | Path-only first; excerpts for small text files |
| OQ2 | Max image count / multi-photo bursts from iOS? | Cap 5; process in order; mention truncation |
| OQ3 | Should pure image-without-caption auto-OCR into text? | No — vision via `read_file` is enough for v1 |
| OQ4 | Video non-voice notes? | Explicit non-goal v1 (voice note MIME subset stays) |
| OQ5 | Prune policy shared with IMP-08? | Yes, extend prune script or attach-specific sweeper |
| OQ6 | Must Grok refuse “can’t see” if paths listed? | **Yes** — normative in spec |
| OQ7 | Channel room attachments same as DM? | **Yes** if room already wakes |

---

## 7. Recommended direction and success signals

### 7.1 Recommendation

Ship **Approach A2** in phases:

1. **P0 — Reliability for images (already half-built)**  
   - Prove rehydrate → download → inject path block is **always** present when RC message has an image.  
   - Fix thumb skip with fixtures from real `files[]` shapes.  
   - Add `reply_prompt` inbound rule.  
   - Regression tests + one live smoke.

2. **P1 — Generic documents**  
   - Download non-image allowlisted types; inject paths + metadata (name, mime, bytes).  
   - Small text files: optional inline excerpt.  
   - Replace empty-attachment stub with typed diagnostics.

3. **P2 — PDF / richer extract + hygiene**  
   - Optional PDF text extraction; retention prune; RUNNING_META attach counts; HEIC convert if needed.

### 7.2 Success signals

| Signal | Target |
| --- | --- |
| Principal sends JPEG + “what is in this photo?” | Grok answers about **image content**, not “I can’t view attachments” |
| Wake prompt for image message | Contains `[Image attachment(s)…]` and real path under `attachments/` |
| Thumb files | Not listed as primary image paths |
| PDF / `.md` / `.py` attach | Path (and/or excerpt) in inject; Grok can cite content |
| Oversize file | Clear FINAL path / inject error; no hang |
| Usability contracts | Remain green |
| Outbound media path | Unchanged ledger behavior |

### 7.3 Explicit non-goals (research)

- Replacing Path A Whisper with cloud STT  
- Auto-forwarding inbound files back out via `rc_post_media`  
- Full malware sandbox / AV gateway  
- Multi-user RBAC attachments  
- Implementing runtime in this documentation package  

---

## 8. Sources / primary interfaces

### 8.1 In-repo / live tree

- `~/.grok/agency/ops/rocketchat/wake/rc_operator_agent.py` — `download_rc_file`, `fetch_message_by_id`, `resolve_message_text_for_wake`  
- `~/.grok/agency/ops/rocketchat/wake/wake_lib.py` — extractors, `compose_wake_user_text`, `message_has_handleable_content`  
- `~/.grok/agency/ops/rocketchat/wake/rc_post_media.py` — outbound only  
- `~/.grok/agency/ops/rocketchat/wake/reply_prompt.txt`  
- `~/.grok/agency/ops/rocketchat/NO_DUPLICATE_POSTS.md`  
- `~/logs/rocketchat-dm-wake/attachments/` — live JPEG + thumb (2026-07-11)  
- `~/logs/rocketchat-dm-wake/wake-prompt-1783806806.txt` — caption-only inject despite attach claim  
- `~/logs/rocketchat-dm-wake/operator-agent.log` — download + restart timeline  
- Project docs: [`docs/message-flow.md`](../../docs/message-flow.md), [`docs/architecture.md`](../../docs/architecture.md)

### 8.2 External

- Rocket.Chat REST auth headers (`X-Auth-Token`, `X-User-Id`) — [Authentication API](https://developer.rocket.chat/apidocs/authentication-api)  
- Upload media (outbound reference) — [Upload Media Files to a Room](https://developer.rocket.chat/apidocs/upload-media-files-to-a-room)  
- File download auth / 403 behavior — community threads on file-upload access denied  
- Grok CLI tools: `read_file` multimodal for local images (operator already targets this)

---

## 9. Conclusion

The stack is **one hardening pass away** from credible image viewing and **one structured extension** away from general file literacy. The wrong move is a parallel bot architecture or teaching Grok to scrape RC with secrets. The right move is to finish the **operator-owned inbound attachment pipeline**, lock it with fixtures drawn from real RC payloads, and make the wake contract refuse “I can’t see” when local paths were supplied.

Continue: [spec.md](./spec.md) → [test-plan.md](./test-plan.md) → [implementation-plan.md](./implementation-plan.md).
