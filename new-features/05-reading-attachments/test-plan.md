# Test plan: Reading attachments in Rocket.Chat

| Field | Value |
| --- | --- |
| **ID** | **NF-TP-05** |
| **Feature** | Reading attachments (inbound pictures & files → Grok can view) |
| **Spec** | [`./spec.md`](./spec.md) (NF-SPEC-05) |
| **Implementation plan** | [`./implementation-plan.md`](./implementation-plan.md) (NF-IP-05) |
| **Research** | [`./research.md`](./research.md) |
| **Related** | `wake/rc_operator_agent.py` (`download_rc_file`, `resolve_message_text_for_wake`, `fetch_message_by_id`), `wake_lib` extractors / `compose_wake_user_text`, `reply_prompt.txt`, usability contracts |
| **Type** | Unit + contract (mock RC) + golden fixtures + optional live RC smoke |
| **Status** | Test-planning documentation only · **Last reviewed:** 2026-07-11 |
| **Flags under test** | `RC_ATTACH_ENABLED`, `RC_ATTACH_MAX_BYTES`, `RC_ATTACH_MAX_FILES`, `RC_ATTACH_IMAGE`, `RC_ATTACH_DOCS`, `RC_ATTACH_PDF_EXTRACT`, `RC_ATTACH_INLINE_MAX_CHARS`, `RC_ATTACH_RETENTION_HOURS`, `RC_ATTACH_DOWNLOAD_TIMEOUT_S` |

---

## 1. Scope and traceability

### 1.1 In scope

- Rehydrate via `chat.getMessage` before classify  
- Classify: audio / image / document / thumb_skip / binary_skip  
- Download auth headers + same-host policy  
- Image path inject + thumb exclusion  
- Document path inject + size/count caps  
- Typed errors; no silent caption-only success when files present  
- `reply_prompt` inbound consumption rule  
- Single-bubble finalize still holds  
- Cache location outside Project cwd  

### 1.2 Out of scope

- Implementing attachment pipeline in this package  
- Outbound `rooms.mediaConfirm` ledger redesign  
- Full malware sandbox  
- Non-voice video understanding  
- Live network tests in default CI (L3 is opt-in)  

### 1.3 Requirement map

| Spec | Cases |
| --- | --- |
| FR-A0, AC-A6 | TP-A-00 |
| FR-A1–A2, AC-A2 | TP-A-01, TP-A-02 |
| FR-A3–A5, AC-A1, AC-A3 | TP-A-03, TP-A-04, TP-A-05 |
| FR-A6 | TP-A-06 (Path A regression) |
| FR-A7–A8, FR-D1–D2, AC-A4 | TP-A-07, TP-A-08 |
| FR-A9–A10, AC-A5 | TP-A-09, TP-A-10 |
| FR-A11–A12 | TP-A-11, E-A-ssrf |
| FR-A13–A14 | TP-A-12, TP-A-13 |
| FR-A15 | TP-A-14 |
| FR-M1–M3 | TP-A-15 |
| FR-M4–M5, AC-A7 | TP-A-16 |
| FR-D3–D4 | TP-A-17, TP-A-18 |
| NFR-A3, OBS-A1 | TP-A-19 |
| AC-A8 | TP-A-20 |

---

## 2. Test strategy and layers

| Layer | Proves | Tools |
| --- | --- | --- |
| **L0 Unit** | extract/classify/compose pure functions; size/cap helpers; thumb skip | pytest/unittest on `wake_lib` |
| **L1 Contract** | Mock `chat.getMessage` + HTTP download; resolve builds correct wake text | Mock urllib / http_api |
| **L2 Golden fixtures** | Real RC-shaped payloads (sparse WS, full getMessage, iOS multi-file + thumb) | JSON fixtures under tests |
| **L3 Live opt-in** | Principal phone JPEG + PDF smoke on local RC | `RC_LIVE_ATTACH=1` |
| **L4 Regression** | Usability contracts + integration suite green | `test_usability_contracts.py`, `test_rc_integration.py` |

---

## 3. Preconditions

- Ability to import `wake_lib` and operator helpers under test  
- Mock RC layer recording getMessage bodies and download URLs/headers  
- Fixtures:  
  - sparse WS message (text only fields)  
  - full getMessage with `files[]` image + thumb  
  - pure voice note audio  
  - PDF / markdown document  
  - oversize file meta  
  - external `title_link` host (SSRF)  
- For L3: live RC, operator, principal account, sample JPEG/PDF  

---

## 4. Concrete test cases

### TP-A-00 — Master switch off

| | |
| --- | --- |
| **Phase** | P0 |
| **Preconditions** | `RC_ATTACH_ENABLED=0` |
| **Steps** | Resolve message with image candidate. |
| **Expected** | No new image path inject (FR-A0, AC-A6). Audio Path A policy independent as implemented. |
| **Pass** | Compose output lacks image path block |

### TP-A-01 — Rehydrate before classify

| | |
| --- | --- |
| **Phase** | P0 |
| **Preconditions** | Sparse WS msg; mock getMessage returns image file |
| **Steps** | Call resolve with mid present. |
| **Expected** | getMessage called; image downloaded/injected (FR-A1, AC-A2). |
| **Pass** | Mock call count ≥1; path block present |

### TP-A-02 — Union of file / files / attachments

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Fixtures covering each surface alone and combined duplicates. |
| **Expected** | De-duplicated candidates; no double inject of same id (FR-A2). |
| **Pass** | Candidate id set size correct |

### TP-A-03 — Image path inject shape

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Download mock returns JPEG bytes; compose wake text. |
| **Expected** | Caption preserved; `[Image attachment(s)` block; absolute path; mentions `read_file` (FR-A5, FR-M2, AC-A1). |
| **Pass** | Regex + path exists on fake FS |

### TP-A-04 — Thumb skip

| | |
| --- | --- |
| **Phase** | P0 |
| **Preconditions** | `files[]` with `IMG.jpg` and `thumb-IMG.jpg` |
| **Steps** | extract_image + resolve. |
| **Expected** | Only full image injected (FR-A4, AC-A3). |
| **Pass** | No path basename starting with `thumb-` in inject |

### TP-A-05 — Live regression fixture (2026-07-11 shape)

| | |
| --- | --- |
| **Phase** | P0 |
| **Preconditions** | Golden from observed RC multi-file image+thumb if capturable; else synthetic equivalent |
| **Steps** | classify + inject. |
| **Expected** | Full image only; no caption-only false success. |
| **Pass** | Fixture assertion |

### TP-A-06 — Voice note Path A still works

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Empty caption + audio file; mock STT returns text. |
| **Expected** | `[Voice note transcript]` present; wake continues (FR-A6). |
| **Pass** | Existing usability voice test remains green |

### TP-A-07 — Markdown / text document

| | |
| --- | --- |
| **Phase** | P1 |
| **Preconditions** | `RC_ATTACH_DOCS=1` |
| **Steps** | Attach `notes.md` with body; resolve. |
| **Expected** | File attachment block with path; optional excerpt ≤ inline max (FR-A7, FR-D1–D2, AC-A4). |
| **Pass** | Path + name/mime/bytes fields |

### TP-A-08 — Caption + document both present

| | |
| --- | --- |
| **Phase** | P1 |
| **Steps** | Caption “summarize this” + PDF/md. |
| **Expected** | Both caption and file block in composed text (FR-A8). |
| **Pass** | Order: caption then blocks (or documented order) |

### TP-A-09 — Partial failure still wakes

| | |
| --- | --- |
| **Phase** | P1 |
| **Steps** | Two files; first download fails; second succeeds. |
| **Expected** | Error line for first; success path for second; wake proceeds (FR-A9). |
| **Pass** | Both markers in text |

### TP-A-10 — Total failure typed message

| | |
| --- | --- |
| **Phase** | P1 |
| **Steps** | Pure attach; all downloads fail; no caption. |
| **Expected** | User-facing typed error; Thinking… finalized (FR-A9–A10); not audio-only stub. |
| **Pass** | Final body mentions attachment failure class |

### TP-A-11 — No secrets required in Grok tools

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Inspect inject + reply_prompt; ensure no instruction to open `rocketchat.env`. |
| **Expected** | FR-A11 holds. |
| **Pass** | Static string absence |

### TP-A-12 — Max bytes reject

| | |
| --- | --- |
| **Phase** | P1 |
| **Preconditions** | `RC_ATTACH_MAX_BYTES=1000`; file meta/download larger |
| **Steps** | Resolve. |
| **Expected** | Typed oversize error; no success path inject (FR-A13, AC-A5). |
| **Pass** | Error substring; file not marked success |

### TP-A-13 — Max files truncate

| | |
| --- | --- |
| **Phase** | P1 |
| **Preconditions** | `RC_ATTACH_MAX_FILES=2`; three images |
| **Steps** | Resolve. |
| **Expected** | Two processed; truncation note (FR-A14). |
| **Pass** | Count + note |

### TP-A-14 — Cache not in Project cwd

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Download image with project cwd = IdeaProjects slug. |
| **Expected** | Path under log attachments dir (FR-A15). |
| **Pass** | Path prefix assertion |

### TP-A-15 — reply_prompt inbound rule

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Read `reply_prompt.txt` after change. |
| **Expected** | Explicit rule: listed attachment paths → must `read_file` before “can’t view” (FR-M1). |
| **Pass** | Regex presence |

### TP-A-16 — Single bubble / no outbound double confirm

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Full wake mock with image attach. |
| **Expected** | One Thinking postMessage; final chat.update only; no answer postMessage (FR-M4–M5, AC-A7). |
| **Pass** | Usability-style call sequence |

### TP-A-17 — PDF extract flag

| | |
| --- | --- |
| **Phase** | P2 |
| **Preconditions** | `RC_ATTACH_PDF_EXTRACT=1`; PDF fixture with known text |
| **Steps** | Resolve. |
| **Expected** | Extract text or extract-error + path (FR-D3). |
| **Pass** | Known string or error class |

### TP-A-18 — Executable denylist

| | |
| --- | --- |
| **Phase** | P1 |
| **Steps** | Attach `.exe` / `.dmg`. |
| **Expected** | `binary_skip` typed skip; no execute (FR-D4). |
| **Pass** | No success path for binary |

### TP-A-19 — Logging shape

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | Process image message; capture logs. |
| **Expected** | Counts `audio`/`image`/`docs`; basename+bytes; no token strings (NFR-A3, OBS-A1). |
| **Pass** | Log assertions |

### TP-A-20 — Full regression green

| | |
| --- | --- |
| **Phase** | P0+P1 |
| **Steps** | Run usability + integration suites. |
| **Expected** | Exit 0 with new tests (AC-A8). |
| **Pass** | CI/local exit code |

### TP-A-21 — Same-host download only

| | |
| --- | --- |
| **Phase** | P0 |
| **Steps** | `title_link` points to `https://evil.example/file`. |
| **Expected** | Reject; typed error; no request to evil host (FR-A12). |
| **Pass** | Mock network sees zero evil host calls |

---

## 5. Edge cases and negative cases

| ID | Scenario | Expected |
| --- | --- | --- |
| **E-A-01** | Empty caption + image only | Wake with image block; no audio stub |
| **E-A-02** | Empty caption + unknown binary | Typed unsupported; finalize error if nothing else |
| **E-A-03** | getMessage 500 | Fall back to queue meta; log error; best-effort |
| **E-A-04** | Download 403 | Typed auth/download error line |
| **E-A-05** | Download empty body | Typed empty-download error |
| **E-A-06** | Filename with path traversal `../../etc/passwd` | Safe basename only (`_safe_filename`) |
| **E-A-07** | Unicode filename | Sanitized stored name; original title in inject |
| **E-A-08** | HEIC image | Success if readable; else typed codec error (P2) |
| **E-A-09** | GIF / WebP | Treated as image if mime/ext allow |
| **E-A-10** | Multi-page PDF huge text | Inline cap respected; path still present |
| **E-A-11** | Concurrent two rooms attach | Per-wake isolation; no path mix-up |
| **E-A-12** | Operator restart mid-download | No crash loop; next message recovers |
| **E-A-13** | Attachment in channel with cwd pin | Cache still under log dir; cwd unchanged |
| **E-A-14** | Collab room principal attach | Pipeline runs; bot-origin out of scope |
| **E-A-15** | Voice note mislabeled as `video/mp4` | Still audio class if Path A rules match |
| **E-A-16** | Duplicate file id in files + attachments | Single download |
| **E-A-17** | Secret-looking file content | Still may inject path; reply_prompt forbids dumping secrets to RC |
| **E-A-ssrf** | External title_link | Blocked (see TP-A-21) |
| **E-A-secret** | Inject must not include X-Auth-Token | Static + runtime log check |
| **E-A-ledger** | Inbound path never calls mediaConfirm | No ledger mutation on receive |

Minimum **≥ 8** edge IDs satisfied by table above (E-A-01… and named edges).

---

## 6. Pass / fail and exit criteria

### 6.1 Phase gates

| Phase | Must pass | May defer |
| --- | --- | --- |
| **P0** | TP-A-00…06, 11, 14–16, 19–21; E-A-01, 04–07, 16, ssrf, secret, ledger | PDF extract |
| **P1** | TP-A-07–10, 12–13, 18; E-A-02, 10, 13 | HEIC convert polish |
| **P2** | TP-A-17; retention prune test; health fields | — |

### 6.2 Overall pass criteria

1. All P0 cases green before enabling images as “supported” in runbook.  
2. All P1 cases green before advertising document attach on phone.  
3. Usability suite exit 0.  
4. No regression: voice notes, Thinking… finalize, NO_DUPLICATE outbound.  
5. Live L3 smoke (optional but recommended before principal trust): one JPEG + one markdown file.

### 6.3 Fail criteria (ship blockers)

- Caption-only inject when getMessage shows an image (2026-07-11 class)  
- Thumb listed as only/primary image path  
- Grok instructed to open secrets for download  
- SSRF open download  
- Second answer bubble introduced  

---

## 7. Fixtures and tooling notes

| Fixture idea | Purpose |
| --- | --- |
| `fixtures/rc_msg_sparse_ws.json` | WS without files |
| `fixtures/rc_msg_image_thumb.json` | files[] full+thumb |
| `fixtures/rc_msg_voice_m4a.json` | Path A |
| `fixtures/rc_msg_markdown.json` | docs |
| `fixtures/sample.jpg` / `sample.md` | Binary/text for mock download |

Mock download should return fixture bytes and assert headers contain `X-Auth-Token` and `X-User-Id` without printing values.

---

## 8. Mapping to implementation plan

| Impl phase | Test gate |
| --- | --- |
| P0.1–P0.5 image harden | P0 exit criteria |
| P1.1–P1.4 documents | P1 exit criteria |
| P2 hygiene | P2 exit criteria |

See [implementation-plan.md](./implementation-plan.md) for eng sequencing. Prior research: [research.md](./research.md). Spec: [spec.md](./spec.md).
