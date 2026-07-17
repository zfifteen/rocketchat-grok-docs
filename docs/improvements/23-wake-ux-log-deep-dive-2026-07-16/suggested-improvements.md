# Suggested improvements — wake / response UX (log-backed)

**Status:** Wave 1 implemented 2026-07-16 (S1/S2/S4-lite/S7/S14); residual S3/S5/S6/S8/S10–S13 + live identity/note_429 hardening  
**Evidence:** [evidence.md](./evidence.md)  
**Package:** [IMP-23 README](./README.md) 

Prior art already tracked: **IMP-21 B1–B10** (partial), **IMP-22** (denial extract implemented; operators may need restart), phase-chrome plan, Heavy review H/M items. Items below are **new or re-prioritized from live logs** — not a rehash of “cap blast radius.”

---

## P0 — Fix what the phone user feels every busy session

### S1 — Global `chat.update` rate budget (implements IMP-21 **B4**, raises priority)

**Status:** Wave 1 partial — `RateLimitBackoff` + `final_cool_sleep_s` pure + live wire; residual: only call `note_429` on real 429s; full host-wide budget needs shared bucket (S4).

**Problem:** Across operators, logs show **hundreds of HTTP 429** failures on `update_message` (grok 491, hermes 235, agy 316 in current corpora). Stream thought flush + multi-bot concurrent finals still thrash Rocket.Chat. Evidence peaks at 10–24 failures **per minute**. Two historical finals landed `phase=FINAL_OK ok=False` (body never painted).

**Why still rough:** B4 has a solid spec (`B4-B5-SPEC.md`) but is **not implemented**. Default cool-down before final is still too weak under multi-operator load; thought flushes use `retries=0` and burn the budget.

**Do:**
1. Implement `StreamThrottle.final_cool_remaining` + `RC_FINAL_COOL_S` (≥3s default) before FINAL.
2. Lower mid-wake update cadence under pressure: if last update was 429, **back off flusher** for that bubble (exponential, shared with finalize).
3. Prefer **skip intermediate** rather than fail FINAL: drop thought paints when `seconds_since_last < min` or remaining budget < 2.
4. Optional: single-writer queue per `(identity, msgId)` so flusher and finalize never interleave.

**Acceptance:** 10 consecutive tool-heavy wakes, multi-bot room active → **zero** FINAL with `ok=False`; 429 count per wake ≤ 1; principal always sees final answer or FINAL_ERR.

**Maps to:** IMP-21 B4; phase-chrome “no 429 regression.”

---

### S2 — Cancelled + empty reply file is the Grok failure mode (implements **B5** + extends IMP-22)

**Status:** Wave 1 implemented — stronger salvage, trailing structured section, secret redaction, `should_skip_empty_reply_retry`; residual: Grok CLI always writing reply file.

**Problem:** Last 120 grok wake-runs: **~22 Cancelled** vs ~95 EndTurn. Operator scheduled **11 empty-reply recoveries**; ~4 still ended FINAL_ERR after retry. Anatomy of Cancelled runs often includes **streamed `text` chunks** and lots of `thought`, then `stopReason=Cancelled` with **no reply-file body** → bubble falls through to thin FINAL_ERR (body_len≈235).

**Honest root:** Not primarily “restricted tool deny” (IMP-22). Pattern looks like **CLI cancelled mid-turn** (user-cancel style end, permission friction, or session interrupt) while streaming partial answer to stdout **but not the reply file**.

**Do:**
1. On empty reply file: **salvage streamed `text` events** from wake-run log into FINAL_OK (or FINAL_PARTIAL) before empty-reply re-spawn.
2. Gate empty-reply retry: only if salvage empty **and** stopReason in allowlist (`Cancelled` clean, not MaxTurns / crash). Cap 1 retry (already) + **no retry** if salvage produced ≥N chars.
3. Surface stopReason + “salvaged stream text” in bubble (IMP-22 already helps denials; add **stream salvage** line).
4. Investigate Grok CLI: why Cancelled with text in stream but no reply write — prompt hardening (“always write reply file before exit”) is necessary but insufficient alone.

**Acceptance:** Fixture wake-run with Cancelled + text chunks → FINAL_OK body contains salvaged text, **no** second spawn. Live: empty-reply recovery rate drops ≥50% week-over-week.

**Maps to:** IMP-21 B5; IMP-22 adjacent; NO_DUPLICATE_POSTS still holds (same bubble).

---

### S3 — Agy FINAL_ERR rate is structurally high

**Status:** Residual (not Wave 1).

**Problem:** Agy logs: **33 FINAL_ERR vs 91 FINAL_OK** (~27% error finalize). Many recent Agency wakes end `FINAL_ERR body_len=173 stopReason=-` and **quality_gate suppress return-notify**. Collab looks “dead” to principal when agy is assigned.

**Do:**
1. Diff agy finalize path vs grok: missing stopReason, empty reply, cwd, timeout, CLI spawn.
2. Ensure agy gets same **stream salvage + denial extract + empty-reply policy** as grok.
3. FINAL_ERR body must name **backend=agy**, log basename, and human reason (not 173-char opaque template).
4. When quality_gate suppresses return-notify, post a **lead-visible** one-liner on the same bubble or a single lead ack (“agy hop failed — see bubble”) so collab does not stall silently.

**Acceptance:** Agy FINAL_ERR rate &lt; 5% on 50 consecutive Agency wakes; suppressed return-notify always leaves a visible lead cue.

---

### S4 — Multi-operator 429 is a **shared room** problem, not per-bot isolation

**Status:** Wave 1 pure helper done (`default_shared_update_bucket`); live must switch all operators off per-bot `LOG_DIR` buckets. Identity audit residual (some `COLLAB_GROK` hardcodes remain).

**Problem:** Spec B4 R4-4 assumed separate RC identities isolate rate limits. Live logs show **hermes/nie logging `update_message identity=grok failed … 429`** and all five operators hammering the same minutes (e.g. 2026-07-17 00:51–00:52). Either wrong identity in log, shared token misuse, or RC limits are **room/IP-global**.

**Do:**
1. Audit each operator’s REST auth: hermes must never call `chat.update` as grok.
2. If limits are global: add **cross-process update token bucket** (file lock or local Redis-less lease under `~/logs/rocketchat-shared/rc-update.bucket`) shared by all operators.
3. Stagger thought flush phase by operator (hash identity → offset ms).

**Acceptance:** Under 4-bot collab, no identity mis-attribution in logs; 429/minute room-wide &lt; 5.

---

## P1 — Reliability and queue honesty

### S5 — In-flight skip is silent (308× grok)

**Problem:** `enqueue skip in-flight mid=…` dominates skips. Principal edits / re-sends / duplicate WS deliveries vanish with **no reaction and no “busy” chrome** on the original bubble.

**Do:**
1. On in-flight duplicate: set reaction 👀 already present → optional 🔁 or update meta “still working on your previous ping.”
2. Coalesce: if new text differs, **queue follow-up** after current wake (per-room queue — IMP-10 was marked Done; verify it still applies under multi-operator).
3. Log at info with **user-visible mid** once per mid (dedupe log spam).

**Acceptance:** Re-@ while wake running → user sees busy state; second distinct ask runs after first finalize.

---

### S6 — Double-seen / duplicate log lines (IMP-21 **B6**)

**Problem:** `skip no_operator_mention` and many room events appear **twice within 1s** for the same mid (all operators). Suggests dual subscription paths or process double-handle (WS + catch-up).

**Do:** Deduplicate at enqueue key `(operator, mid)` with TTL; fix double subscribe if present; single log line per decision.

**Acceptance:** One decision log line per (operator, mid); no paired identical skips.

---

### S7 — Missing / invalid cwd must FINAL_ERR immediately (not exception)

**Status:** Wave 1 implemented (`validate_wake_cwd` + `format_missing_cwd_err`); residual: remove older duplicate missing-cwd block in live agent.

**Problem:** `process item failed … No such file or directory: …/math-research` (room pin to deleted path). stderr also shows operator start loops when RC down.

**Do:**
1. Before spawn: `Path(cwd).is_dir()`; else FINAL_ERR “cwd missing: …; use !cwd or pin.”
2. Clear stale room pins automatically when path gone (or mark invalid in state).
3. RC unreachable at start: exponential backoff without traceback spam (KeepAlive already restarts).

**Acceptance:** Fake pin to `/tmp/nope` → one bubble error, no traceback storm; no silent drop.

---

### S8 — Wire remaining IMP-21 predicates (B3 / B10 / B2 / B7)

**Problem:** Specs + pure tests exist; residual list says **not on launchd**. Logs still show dense multi-round traffic, quality_gate suppressions, and peer noise risk.

**Do (ops, not more docs):**
1. Agency-sync mirror gates for B2/B7.
2. Adopt `b3_b10_wake_predicates` into live `should_enqueue_llm_wake`.
3. Pass `room_id` into return-notify belt.
4. Restart all five operators after sync.

**Acceptance:** Activity/stream chrome does not wake peers; prose `@bot` in explanations does not re-wake; principal→peer solo does not collab-return (B1 already fixed — regression test live).

---

### S9 — Restart / deploy discipline for IMP-22

**Problem:** Denial extract is on disk; **operators not kickstarted** after merge (session blocked). health still old process until restart. Code present ≠ live.

**Do:** Document one `kickstart` script for all `com.velocityworks.rocketchat-*-operator`; run after every wake/ code sync; health.json shows pid change + `wake_denials` import ok probe.

**Acceptance:** After deploy, `python -c "import wake_denials"` under each operator cwd; one forced denial appears in FINAL_ERR live.

---

## P2 — UX polish that removes “is it stuck?”

### S10 — Always-on phase chrome (existing plan)

Stream-on still leaves long `…` with no elapsed heartbeat when thoughts are sparse. Implement phase-chrome plan: meta HB even when stream on; FINAL_ERR error-first.

**Acceptance:** 20s tool silence shows ticking chrome; Cancelled error not buried under thoughts.

---

### S11 — Tiny / low-signal FINAL_OK bodies

Logs show FINAL_OK with `body_len` 12–98 (acks, stubs). Quality-gate already blocks some collab returns; **principal** still sees near-empty success bubbles.

**Do:** If body_len &lt; threshold and no media, treat as weak success: append “_(short reply)_” or promote to FINAL_ERR if stopReason weird; optional second-pass “expand” only on explicit user ask (no auto double-wake by default).

---

### S12 — health.json truthfulness

Live sample: `ws_connected: true` but `last_event_at: null` while `last_wake_at` set. Weak for IMP-12 watchdog.

**Do:** Set `last_event_at` on any WS room event; expose per-operator health files (not only grok dm-wake); include `last_429_at`, `inflight_count`.

---

### S13 — Log retention / wake-run volume (ops)

`rocketchat-dm-wake` has **1000+** wake-prompt/run files; large outliers (235KB run). IMP-08 marked Done — verify retention still active; add wake-run gzip after 7d; drop prompt bodies after 48h if reply finalized.

---

### S14 — Cross-bot observability dashboard (lightweight)

**Status:** Wave 1 implemented — `scripts/rc_wake_digest.py` filters ISO-timestamped lines by `--hours` (not whole-file tail).

Five separate log dirs make “what just failed?” hard. Add `scripts/rc_wake_digest.py` → last 24h table: wakes, FINAL_ERR, 429, empty-reply, Cancelled, quality_gate suppress — print to stdout or Agency daily.

**Acceptance:** One command principal/agent can run after a bad session.

---

## Explicit non-goals (this pass)

- Moving off Rocket.Chat.
- Global YOLO on channels.
- New collab product features beyond reliability of current multi-round.
- Re-opening IMP-16 extract-to-project.

---

## Suggested implementation order

| Wave | Items | Outcome |
| --- | --- | --- |
| **1 (this week)** | S1, S2, S9 | Finals stick; fewer Cancelled empties; IMP-22 actually live |
| **2** | S3, S4, S7 | Agy trustworthy; rate limits real; no missing-cwd crashes |
| **3** | S5, S6, S8 | Queue honesty; dedupe; collab predicates on launchd |
| **4** | S10–S14 | Chrome, health, digest, retention |

---

## Relationship to existing backlog

| Existing | Action |
| --- | --- |
| IMP-21 B4/B5 | **Promote to active implementation** — highest leverage |
| IMP-21 B3/B10/B2/B7 | Finish **runtime wire** only |
| IMP-22 | Done in tree; **restart + live denial proof** |
| Phase-chrome plan | Schedule after S1 so chrome does not worsen 429 |
| IMP-10 per-room queue | Re-verify under 5 operators |
| Heavy review M1 agy parity | Fold into S3 |

---

## Acceptance for closing IMP-23 as “addressed”

Not every S* must ship, but Wave 1 + S3 must land with measured before/after from `rc_wake_digest` (or equivalent log scan):

1. 429/wake ↓ ≥70%  
2. empty-reply recovery/wake ↓ ≥50%  
3. Agy FINAL_ERR rate ↓ to &lt;5%  
4. No FINAL_OK with `ok=False` in a 48h window  
