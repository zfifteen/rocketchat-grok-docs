# Implementation plan: Reading attachments in Rocket.Chat

| Field | Value |
| --- | --- |
| **ID** | **NF-IP-05** |
| **Feature** | Reading attachments — inbound pictures & files → Grok can view |
| **Spec** | [NF-SPEC-05](./spec.md) (**source of truth for flags & shalls**) |
| **Test plan** | [NF-TP-05](./test-plan.md) (**source of truth for validation gates**) |
| **Research** | [research.md](./research.md) |
| **Runtime home** | `~/.grok/agency/ops/rocketchat/wake/` (`rc_operator_agent.py`, `wake_lib.py`, `reply_prompt.txt`; optional new `rc_attachments.py`) |
| **Status** | Implementation-planning documentation only · **Last reviewed:** 2026-07-11 |

---

## 1. Overview and goals

### 1.1 Problem

Principal attachments (images, documents) do not reliably reach Grok’s reasoning context. Partial image download/inject exists but live 2026-07-11 runs showed caption-only prompts, thumbs downloaded, empty replies after restart, and zero generic document pipeline. Voice Path A works; general attachment literacy does not.

### 1.2 Primary objective

Complete an **operator-owned inbound attachment pipeline**: rehydrate → classify → policy download → type-specific inject → prompt contract forcing `read_file`, with tests and safe defaults — without breaking Thinking… / reply file / `chat.update` or outbound `rc_post_media`.

### 1.3 Success metrics

| Metric | Target |
| --- | --- |
| Image attach → path block in wake prompt | 100% when getMessage has image |
| Thumb as primary inject | 0 |
| “I can’t view attachments” when paths listed | 0 under fixture prompts |
| Oversize false success | 0 |
| Usability contracts | Still pass |
| Outbound media ledger behavior | Unchanged |
| eng-days to P0 | ~2–4 |

### 1.4 Why this order

Highest trust ROI after Feature 2 (streaming already improves hang visibility): phone photo literacy unblocks daily agency use. Depends only on local RC + existing Grok tools.

---

## 2. Assumptions

| Assumption | Note |
| --- | --- |
| `download_rc_file` + `chat.getMessage` remain valid on RC 8.6 | Live evidence downloads work |
| Grok `read_file` can view local JPEG/PNG | Existing multimodal tool path |
| Restricted `--permission-mode auto` allows cache `read_file` | Confirm in P0 live smoke |
| Queue still has message mid for rehydrate | Current design |
| Docs package does not ship runtime | This IP is sequencing only |

---

## 3. Design execution summary

```
_process_pending_item:
  raw = queue fields + mid
  text = resolve_message_text_for_wake(raw)   # rehydrate → classify → download → compose
  if not text: typed empty-attach error
  post Thinking... (if not yet)
  wake Grok with inject including text
  reply file → chat.update
```

**Flags (production-safe defaults per NF-SPEC-05):**

| Flag | Default | Meaning |
| --- | --- | --- |
| `RC_ATTACH_ENABLED` | `1` | Master |
| `RC_ATTACH_MAX_BYTES` | `20971520` | 20 MiB |
| `RC_ATTACH_MAX_FILES` | `5` | Cap |
| `RC_ATTACH_IMAGE` | `1` | Images |
| `RC_ATTACH_DOCS` | `1` after P1 soak else start `0` if risk-averse | Docs |
| `RC_ATTACH_PDF_EXTRACT` | `0` | P2 |
| `RC_ATTACH_INLINE_MAX_CHARS` | `12000` | Excerpt |
| `RC_ATTACH_RETENTION_HOURS` | `72` | Prune |
| `RC_ATTACH_DOWNLOAD_TIMEOUT_S` | `60` | HTTP |

**Rollout preference:** Ship P0 with images on; docs flag can default `1` once P1 tests green, or `0` for canary.

---

## 4. Phased work breakdown

### Phase P0 — Image reliability + prompt contract  
**Effort:** 2–4 eng-days  
**Risk:** Low–medium (touches wake text path)

| # | Task | Deliverables | Validation (NF-TP-05) |
| --- | --- | --- | --- |
| P0.1 | Capture golden fixtures from RC-shaped payloads (sparse WS, image+thumb `files[]`) | `tests/fixtures/rc_msg_*.json` | TP-A-05 |
| P0.2 | Harden `extract_image_file_candidates` thumb skip + unit tests | `wake_lib.py` | TP-A-04, E-A-16 |
| P0.3 | Ensure resolve **always** rehydrates before classify; log image counts | `rc_operator_agent.py` | TP-A-01, TP-A-19 |
| P0.4 | Same-host URL allowlist in `download_rc_file` | operator download helper | TP-A-21, E-A-ssrf |
| P0.5 | `compose_wake_user_text` image block stable; empty stub not used for pure image | `wake_lib.py` | TP-A-03, E-A-01 |
| P0.6 | `reply_prompt.txt` inbound: must `read_file` listed paths | prompt file | TP-A-15 |
| P0.7 | Contract test: mock getMessage + download → path in prompt → single bubble | tests | TP-A-16, TP-A-20 |
| P0.8 | Live smoke: principal JPEG “what is this?” | runbook note | AC-A1 |

**Exit:** Image attach never caption-only when RC has file; thumbs not primary; prompt rule present.  
**Rollback:** `RC_ATTACH_ENABLED=0` or `RC_ATTACH_IMAGE=0`; revert prompt lines.

---

### Phase P1 — Generic documents + limits  
**Effort:** 2–3 eng-days  
**Risk:** Medium (mime matrix)

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| P1.1 | `extract_document_file_candidates` + denylist binaries | `wake_lib.py` | TP-A-18 |
| P1.2 | Download docs to `ATTACHMENTS_DIR`; inject metadata block | resolve path | TP-A-07, TP-A-08 |
| P1.3 | Enforce max bytes / max files | download policy | TP-A-12, TP-A-13 |
| P1.4 | Typed multi-error compose; replace audio-only empty stub | compose + process | TP-A-09, TP-A-10 |
| P1.5 | Optional small-text inline excerpt | compose | FR-D2 cases |
| P1.6 | Integration + usability extensions | tests | TP-A-20 |

**Exit:** md/txt/pdf path inject works; oversize safe.  
**Rollback:** `RC_ATTACH_DOCS=0`.

---

### Phase P2 — PDF extract, retention, observability  
**Effort:** 1–3 eng-days  
**Risk:** Low

| # | Task | Deliverables | Validation |
| --- | --- | --- | --- |
| P2.1 | Optional PDF text extract behind flag | helper + deps note | TP-A-17 |
| P2.2 | Prune script / hook for attachments cache | ops script or IMP-08 extend | NFR-A4 |
| P2.3 | health.json attach fields | operator health write | OBS-A2 |
| P2.4 | Optional HEIC convert via `sips` | helper | E-A-08 |
| P2.5 | Update `docs/message-flow.md` section F | docs project | human review |

**Exit:** PDF extract optional; disk not unbounded; docs aligned.  
**Rollback:** flags off; delete prune if harmful.

---

## 5. File and integration map

| File | Change |
| --- | --- |
| `wake/wake_lib.py` | classify, document extract, compose blocks, thumb tests |
| `wake/rc_operator_agent.py` | resolve pipeline, download policy, logging, health |
| `wake/reply_prompt.txt` | inbound attachment rules |
| `wake/rc_attachments.py` | **optional** extract of download/prune/pdf to keep operator smaller |
| `wake/rc_config.py` | load new `RC_ATTACH_*` flags |
| `ops/rocketchat/tests/*` | fixtures + TP-A cases |
| `docs/message-flow.md` (this repo) | document inbound path when runtime ships |
| launchd | usually env-only; no plist structure change required |

### 5.1 Dependencies

| Depends on | Why |
| --- | --- |
| Existing REST auth (`_operator_auth`) | Download + getMessage |
| Feature 2 finalize always | Empty attach errors still update bubble |
| Disk under `~/logs/rocketchat-dm-wake/` | Cache |

### 5.2 Does not depend on

- LiveKit / call bot  
- Feature 4 agy dual account  
- Apps-Engine  

---

## 6. Rollout, feature flags, rollback

### 6.1 Rollout sequence

1. Merge P0 behind existing code paths; keep `RC_ATTACH_ENABLED=1` only after unit green.  
2. Live JPEG smoke with principal.  
3. Enable P1 docs on DM first (if staged) then channels.  
4. P2 extract/prune after soak ≥3 days.

### 6.2 Rollback

| Level | Action |
| --- | --- |
| Soft | `RC_ATTACH_DOCS=0` or `RC_ATTACH_IMAGE=0` |
| Hard | `RC_ATTACH_ENABLED=0` |
| Code | Revert PR; Path A audio remains |

### 6.3 Ops impact

| Area | Impact |
| --- | --- |
| Disk | Attachments cache growth — prune required |
| CPU | Whisper unchanged; PDF extract optional cost |
| Network | Extra getMessage + download per attach message |
| Security | Same-host download; no new public ports |

---

## 7. Validation strategy (test-plan mapping)

| Gate | Maps to |
| --- | --- |
| Unit extract/classify | TP-A-02, 04, 18 |
| Resolve contract | TP-A-01, 03, 07–13 |
| Prompt + bubble | TP-A-15, 16 |
| Regression suite | TP-A-06, 20 |
| Live smoke | TP-A L3 / AC-A1 |

Full case text: [test-plan.md](./test-plan.md).

---

## 8. Risks and ops impact

| Risk | Mitigation in build |
| --- | --- |
| Break voice notes | TP-A-06 first in every PR |
| SSRF | P0.4 before any title_link trust |
| Disk fill | caps + P2.2 prune |
| Model ignores images | P0.6 prompt + live smoke insist on content answer |
| Restart mid-wake | Prefer resolve before Popen; don’t mark processed early (existing rule) |
| Prompt bloat | inline cap; path-only for large files |

### 8.1 Effort summary

| Phase | eng-days |
| --- | --- |
| P0 | 2–4 |
| P1 | 2–3 |
| P2 | 1–3 |
| **Total** | **~5–10 eng-days** |

---

## 9. Suggested PR slicing

| PR | Contents |
| --- | --- |
| PR1 | Fixtures + thumb skip + unit tests only |
| PR2 | Rehydrate guarantee + same-host download + image compose fixes |
| PR3 | reply_prompt inbound + contract test single bubble |
| PR4 | Documents + limits + typed errors |
| PR5 | PDF extract optional + prune + health + message-flow docs |

---

## 10. Definition of done

- [ ] NF-TP-05 P0 exit green  
- [ ] Live JPEG content answer once  
- [ ] NF-TP-05 P1 exit green  
- [ ] Flags documented in ops runbook when runtime merges  
- [ ] Usability + integration exit 0  
- [ ] Rollback path verified (`RC_ATTACH_ENABLED=0`)  
- [ ] This docs package remains accurate vs shipped flags  

---

## 11. Cross-links

- Research rationale: [research.md](./research.md)  
- Normative shalls: [spec.md](./spec.md)  
- Tests: [test-plan.md](./test-plan.md)  
- Bundle hub: [README.md](./README.md)  
- Parent index: [../README.md](../README.md)
