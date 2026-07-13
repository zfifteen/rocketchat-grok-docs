# Technical Specification: Reading attachments in Rocket.Chat

| Field | Value |
| --- | --- |
| **Spec ID** | **NF-SPEC-05** |
| **Version** | 1.0 |
| **Status** | Specification (implementation out of scope for this document package) |
| **Date** | 2026-07-11 · **Last reviewed:** 2026-07-11 |
| **Prior research** | [`./research.md`](./research.md) |
| **Test plan** | [`./test-plan.md`](./test-plan.md) (NF-TP-05) |
| **Implementation plan** | [`./implementation-plan.md`](./implementation-plan.md) (NF-IP-05) |
| **Related** | `wake/rc_operator_agent.py`, `wake/wake_lib.py`, `reply_prompt.txt`, Path A voice notes, `NO_DUPLICATE_POSTS.md`, outbound `rc_post_media.py` |
| **Owner surface** | Inbound message attachment resolve → local cache → wake inject → Grok tool consumption |

---

## 1. Problem and context

### 1.1 Problem statement

When the principal attaches a picture or file in Rocket.Chat, Grok often cannot view it. Partial image download and path-inject code exists, but live 2026-07-11 traffic showed caption-only wake prompts, empty replies after operator restart, thumb downloads, and no generic document pipeline. Voice notes (Path A) work; general attachment literacy does not.

### 1.2 Context (live stack)

| Element | Current fact |
| --- | --- |
| Intake | `rc_operator_agent` WebSocket + optional poll; principal-only (legacy rooms) |
| Rehydrate | `fetch_message_by_id` → `chat.getMessage` (intended before resolve) |
| Audio | Download → Whisper → transcript in wake text |
| Images | `extract_image_file_candidates` → `download_rc_file` → path list in `compose_wake_user_text` |
| Generic files | Extracted as candidates but **not** downloaded/injected |
| Outbound | `rc_post_media.py` + media-post ledger only |
| Answer UX | Thinking… → reply file → `chat.update` (one bubble) |
| Approval | Restricted default → `--permission-mode auto` |

### 1.3 Spec purpose

Define the engineering contract so **inbound attachments become first-class wake inputs**: reliable rehydrate, policy-bounded download, type-aware inject, and mandatory model consumption rules — without implementing runtime in this docs package.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
| --- | --- |
| G1 | Principal image attach → Grok can describe/answer about image content via local `read_file`. |
| G2 | Principal document attach (text, code, markdown, PDF under policy) → Grok can use content. |
| G3 | Caption + attachment(s) compose into one wake user text without losing either. |
| G4 | Failures are **typed** (oversize, unsupported mime, download 403, extract fail) — never silent blindness. |
| G5 | Preserve one-bubble answer path and outbound media ledger rules. |
| G6 | Attachment cache does not pollute Project cwd or leak secrets. |
| G7 | Automated tests cover sparse WS payloads, thumbs, multi-file, size limits. |

### 2.2 Non-goals

| ID | Non-goal |
| --- | --- |
| NG1 | Implementing this feature in the present documentation package. |
| NG2 | Changing outbound `rc_post_media` confirm semantics. |
| NG3 | Full AV sandbox / malware detonation. |
| NG4 | Grok authenticating to RC `/file-upload` with secrets. |
| NG5 | Non-voice video understanding (v1). |
| NG6 | Multi-user RBAC beyond principal (and existing collab mention rules). |
| NG7 | Auto-repost of received attachments as outbound media. |
| NG8 | Replacing Path A Whisper with a cloud STT provider. |

---

## 3. Normative requirements

### 3.1 Functional requirements — pipeline

| ID | Requirement |
| --- | --- |
| **FR-A0** | When `RC_ATTACH_ENABLED` is disabled (`0`/`false`/`off`), the operator **shall** preserve pre-feature behavior for non-audio attachments (audio Path A **may** remain independently enabled via existing Whisper env). |
| **FR-A1** | For every wake-eligible principal message with a message id, the operator **shall** rehydrate via `chat.getMessage` (or successor) before classifying attachments, when the API is reachable. |
| **FR-A2** | The operator **shall** collect candidates from `file`, `files[]`, and `attachments[]` (union, de-duplicated) as in `extract_file_candidates`. |
| **FR-A3** | The operator **shall** classify each candidate into exactly one primary class: `audio`, `image`, `document`, `binary_skip`, or `thumb_skip`. |
| **FR-A4** | Candidates whose name starts with `thumb-` or `thumb_` (case-insensitive) **shall** be class `thumb_skip` and **shall not** be injected as primary image paths. |
| **FR-A5** | For each `image` candidate under policy, the operator **shall** download bytes with operator auth to `ATTACHMENTS_DIR` (or configured cache) and inject absolute local paths into wake user text. |
| **FR-A6** | For each `audio` candidate, the operator **shall** continue Path A: download → Whisper (or configured STT) → transcript inject (existing behavior **shall** remain available). |
| **FR-A7** | For each `document` candidate under policy, the operator **shall** download to cache and inject at least: local path, original filename, mime/type, and byte size. |
| **FR-A8** | Wake user text **shall** include the original caption (if any) and **shall** include structured attachment blocks for successful downloads. |
| **FR-A9** | When download or classification fails, the operator **shall** inject a typed error line (per file) and **shall still** proceed with the wake if any caption or successful attachment remains; if nothing remains, the operator **shall** finalize with a clear user-facing error (not eternal Thinking…). |
| **FR-A10** | The empty-attachment stub that only mentions “transcribable audio” **shall** be replaced with language covering images and documents when those features are enabled. |
| **FR-A11** | The operator **shall not** require Grok to read `rocketchat.env` or use bot tokens to fetch attachments. |
| **FR-A12** | Download URLs **shall** be restricted to the configured Rocket.Chat base host (no open SSRF to arbitrary hosts). |
| **FR-A13** | Per-file size **shall** be enforced by `RC_ATTACH_MAX_BYTES`; exceeding files **shall** be rejected with a typed error and **shall not** be partially injected as success. |
| **FR-A14** | Per-message file count **shall** be capped by `RC_ATTACH_MAX_FILES`; excess **shall** be reported in inject as truncated. |
| **FR-A15** | Attachment cache files **shall** live under the operator log/attachments tree (not Project cwd). |

### 3.2 Functional requirements — model contract

| ID | Requirement |
| --- | --- |
| **FR-M1** | `reply_prompt.txt` (or equivalent inject) **shall** instruct: if the wake text lists attachment paths, Grok **shall** open them with `read_file` (or documented tool) before claiming inability to view attachments. |
| **FR-M2** | Image inject **shall** use an explicit instruction block that names `read_file` (or current multimodal tool) and lists absolute paths, one per line. |
| **FR-M3** | Document inject **shall** instruct Grok to read the path (and use any provided excerpt as helper, not sole source, when both exist). |
| **FR-M4** | Grok **shall not** `chat.postMessage` the final answer; reply-file + operator `chat.update` remains mandatory. |
| **FR-M5** | Outbound images/files **shall** still use only `rc_post_media.py` (NO_DUPLICATE_POSTS). |

### 3.3 Functional requirements — document types (v1)

| ID | Requirement |
| --- | --- |
| **FR-D1** | When `RC_ATTACH_DOCS=1`, the operator **shall** treat at least these as documents when mime/extension matches: `.txt`, `.md`, `.csv`, `.json`, `.py`, `.rs`, `.js`, `.ts`, `.html`, `.css`, `.yaml`, `.yml`, `.toml`, `.log`, `.pdf` (PDF may be path-only until extract enabled). |
| **FR-D2** | For text-like documents under `RC_ATTACH_INLINE_MAX_CHARS`, the operator **may** inline an excerpt into the wake text in addition to the path. |
| **FR-D3** | When `RC_ATTACH_PDF_EXTRACT=1`, the operator **should** extract text (or first-N pages) into the inject; on extract failure, path **shall** still be provided with an extract-error note. |
| **FR-D4** | Executables and archive types (e.g. `.exe`, `.dmg`, `.zip` by default denylist) **shall** be `binary_skip` unless explicitly allowlisted by config. |

### 3.4 Non-functional requirements

| ID | Requirement |
| --- | --- |
| **NFR-A1** | Attachment resolve for a typical phone JPEG (≤5 MiB) **should** complete in ≤ **5 s** on the principal Mac LAN path to local RC. |
| **NFR-A2** | Download timeout **shall** be bounded (default **60 s**, configurable). |
| **NFR-A3** | Operator **shall** log basename, class, bytes, and success/fail — **not** file contents or auth tokens. |
| **NFR-A4** | Cache retention **shall** be configurable (`RC_ATTACH_RETENTION_HOURS`); default **should** prune stale files (≥72 h suggested). |
| **NFR-A5** | Feature **shall** work for DM and channel rooms already supported by the operator. |
| **NFR-A6** | Implementation **shall** extend unit/integration/usability tests; tests **shall not** be deleted to pass. |
| **NFR-A7** | Restricted approval mode **shall** remain sufficient for `read_file` on attachment cache paths. |

### 3.5 Observability requirements

| ID | Requirement |
| --- | --- |
| **OBS-A1** | Principal-message log lines **shall** include counts: `audio=`, `image=`, `docs=` (or equivalent). |
| **OBS-A2** | `health.json` **should** expose `last_attach_at`, `last_attach_ok`, and `last_attach_error` (or equivalent) when available. |
| **OBS-A3** | Feature 2 RUNNING_META **may** include attachment summary; if present it **shall not** leak full paths with secrets directories. |

### 3.6 Configuration (normative defaults)

| Flag | Default | Meaning |
| --- | --- | --- |
| `RC_ATTACH_ENABLED` | `1` | Master inbound attach pipeline |
| `RC_ATTACH_MAX_BYTES` | `20971520` | 20 MiB per file |
| `RC_ATTACH_MAX_FILES` | `5` | Per message |
| `RC_ATTACH_IMAGE` | `1` | Image download + inject |
| `RC_ATTACH_DOCS` | `1` | Document download + inject |
| `RC_ATTACH_PDF_EXTRACT` | `0` | Off until soak |
| `RC_ATTACH_INLINE_MAX_CHARS` | `12000` | Excerpt cap |
| `RC_ATTACH_RETENTION_HOURS` | `72` | Cache prune |
| `RC_ATTACH_DOWNLOAD_TIMEOUT_S` | `60` | HTTP timeout |

---

## 4. Architecture and design decisions

### 4.1 Decision summary

| Decision | Choice | Rationale |
| --- | --- | --- |
| D1 Ownership | Operator resolves attachments | Auth + policy stay out of model tools |
| D2 Consumption | Local path + Grok `read_file` | Fits CLI wake; multimodal images already supported |
| D3 Cache location | Log-tree `attachments/` | Avoid polluting IdeaProjects cwd |
| D4 Thumbs | Hard skip by name + prefer largest non-thumb | Live double-download evidence |
| D5 SSRF | Same-host only | `title_link` must not open the network |
| D6 Outbound | Unchanged ledger helper | Hard rule already burned principal once |

### 4.2 Logical architecture

```
RC message
   │
   ▼
rehydrate (chat.getMessage)
   │
   ▼
extract_file_candidates → classify
   │
   ├─ audio  → download → Whisper → transcript block
   ├─ image  → download → image path block
   ├─ document → download → path (+ optional excerpt/PDF extract)
   └─ skip   → typed note if user-visible needed
   │
   ▼
compose_wake_user_text
   │
   ▼
Thinking… → Grok CLI (reply_prompt inbound rules) → reply file
   │
   ▼
chat.update FINAL_OK | FINAL_ERR
```

### 4.3 Inject block shapes (normative examples)

**Images:**

```text
[Image attachment(s) — open each path with the read_file tool to view the pixels]
- /Users/…/logs/rocketchat-dm-wake/attachments/1783…-photo.jpg
```

**Documents:**

```text
[File attachment(s) — open each path with read_file (or appropriate tool); do not claim you cannot view attachments if paths are listed]
- name=notes.pdf mime=application/pdf bytes=104422 path=/Users/…/attachments/1783…-notes.pdf
```

**Errors:**

```text
[Attachment error — notes.pdf: exceeds RC_ATTACH_MAX_BYTES (20 MiB)]
```

### 4.4 State machine (attachment resolve)

| State | Meaning |
| --- | --- |
| `ATTACH_OFF` | Master disabled |
| `REHYDRATE` | Fetch full message |
| `CLASSIFY` | Build typed candidate list |
| `DOWNLOAD` | Fetch under policy |
| `INGEST` | STT / excerpt / path list |
| `COMPOSED` | Wake text ready |
| `ATTACH_ERR` | Total failure with typed reason |

Resolve **shall** be synchronous with respect to wake spawn (COMPOSED before `Popen`).

---

## 5. Integration

### 5.1 Modules

| Module | Responsibility |
| --- | --- |
| `wake_lib.py` | Pure extract/classify/compose helpers (unit-testable) |
| `rc_operator_agent.py` | Auth download, rehydrate, wire into `_process_pending_item` |
| `reply_prompt.txt` | Inbound attachment consumption rules |
| Optional `wake/rc_attachments.py` | Download policy, prune, PDF extract (if split for clarity) |
| Tests under `ops/rocketchat/tests/` | Fixtures + contracts |

### 5.2 Interaction with other features

| Feature | Interaction |
| --- | --- |
| NF-SPEC-02 streaming | Meta may show attach counts; final still reply-file |
| NF-SPEC-03 control | No required slash commands for v1 |
| NF-SPEC-04 collab | Principal attachments in collab rooms follow same pipeline; bot-origin files out of scope |
| Path A voice | Shared download primitive; class `audio` unchanged |
| Path C/D voice Call | Out of scope |

### 5.3 Data retention

| Artifact | Location | Retention |
| --- | --- | --- |
| Image/doc binaries | `~/logs/rocketchat-dm-wake/attachments/` | `RC_ATTACH_RETENTION_HOURS` |
| Audio | `…/audio/` | existing + same prune spirit |
| Wake prompts | `wake-prompt-*.txt` | may contain paths; not file bytes |

---

## 6. Risks and dependencies

### 6.1 Dependencies

| Dependency | Need |
| --- | --- |
| RC 8.6 REST auth | Download + getMessage |
| Local Whisper | Audio only |
| Grok CLI `read_file` multimodal | Images |
| Disk space on Mac | Cache |
| Optional `pdftotext` / pdfplumber | Only if PDF extract on |

### 6.2 Risks

See research R1–R12. Spec-level residual risks:

| Risk | Spec control |
| --- | --- |
| Model ignores paths | FR-M1–M3 |
| Host SSRF | FR-A12 |
| Disk fill | FR-A13–A14, NFR-A4 |
| Restart mid-wake | FR-A9 + always finalize (align Feature 2) |

### 6.3 Open decisions

| ID | Decision | Default |
| --- | --- | --- |
| OD-A1 | Exact document allowlist | FR-D1 set |
| OD-A2 | PDF extract default on? | Off (`0`) until soak |
| OD-A3 | HEIC convert tool | Optional P2; accept if `read_file` handles HEIC |
| OD-A4 | health.json field names | OBS-A2 |

---

## 7. Acceptance criteria and phased delivery

### 7.1 Acceptance criteria

| ID | Criterion |
| --- | --- |
| **AC-A1** | Given a principal DM with JPEG attach + caption “what is this?”, wake prompt contains image path block and Grok’s reply references visible content (live or fixture-backed integration). |
| **AC-A2** | Sparse WS payload without `files` but full `chat.getMessage` with image → still AC-A1. |
| **AC-A3** | `files[]` containing full + `thumb-*` → only non-thumb injected. |
| **AC-A4** | PDF or `.md` attach with `RC_ATTACH_DOCS=1` → path block present; Grok can cite content. |
| **AC-A5** | File > `RC_ATTACH_MAX_BYTES` → typed error inject; no false success path. |
| **AC-A6** | `RC_ATTACH_ENABLED=0` → no new doc/image inject (audio policy independent as specified). |
| **AC-A7** | Final answer still single bubble via `chat.update`; no second answer post. |
| **AC-A8** | Usability contract suite remains green with new cases. |

### 7.2 Phased delivery

| Phase | Scope | Gate |
| --- | --- | --- |
| **P0** | Image reliability + thumb skip + reply_prompt inbound + tests | AC-A1–A3, A7–A8 |
| **P1** | Documents + size/count limits + typed errors | AC-A4–A6 |
| **P2** | PDF extract optional, retention prune, health fields, HEIC polish | OD-A2–A4 |

### 7.3 Traceability

| Spec cluster | Research | Test plan | Impl plan |
| --- | --- | --- | --- |
| FR-A0–A15 | A2 pipeline, R1–R12 | TP-A-*, E-A-* | Phase P0–P1 |
| FR-M1–M5 | Prompt contract | TP-A-prompt | P0 |
| FR-D1–D4 | Document matrix | TP-A-docs | P1–P2 |
| NFR/OBS | Success signals | TP-A-obs | P2 |

---

## 8. Explicit documentation-only scope

This specification **shall not** be read as authorization to modify production launchd, secrets, or operator code in the documentation goal. Runtime work follows **NF-IP-05** after operator approval.

Continue: [test-plan.md](./test-plan.md) · [implementation-plan.md](./implementation-plan.md) · parent [research.md](./research.md).
