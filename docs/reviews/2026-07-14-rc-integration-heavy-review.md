# RC integration code review — findings backlog

**Date:** 2026-07-14  
**Mode:** Heavy effort (12 read-only specialists + leader synthesis)  
**Status:** Findings only — **not implemented**. Use this doc to drive later work.  
**Runtime code:** `~/.grok/agency/ops/rocketchat/`  
**Docs package:** this repo (`rocketchat-agents`)  
**Runbook:** `~/.grok/agency/ops/ROCKETCHAT.md`

**Related same-day context:**

- Auto-create policy flipped **default ON** (`RC_AUTO_CREATE_PROJECTS=1`); kill-switch is `0`.
- Grok path: missing project cwd finalizes FINAL_ERR instead of hanging on `…`.
- `#math-research` incident class: `no_create` + missing dir + `FileNotFoundError` (pre-flip).

---

## Purpose

Capture a durable, severity-ranked backlog of issues found in a full-stack review of the Rocket.Chat ↔ Grok operator, so remediations can be planned without re-deriving the analysis.

This is **not** an IMP-21+ formal package yet. Promote items into `docs/improvements/` (or runtime PRs) when work starts.

---

## Executive judgment

| Axis | Assessment |
| --- | --- |
| Happy path | Real and useful: WS wake, 👀, one activity bubble, reply-file truth, structured FINAL_ERR |
| Crash safety | Weak: dequeue-before-done, stuck `in_flight`, no boot drain |
| Multi-writer state | Weak: unlocked `state.json` RMW |
| Public security | Weak for voice mesh; RC is loopback+ngrok with 2FA forced off |
| Test confidence | Strong on queue/lock contracts; weak on media, empty-reply retry, missing-cwd, process exceptions |
| Product scope | Tier A is valuable; dual-identity collab / peer-bar / stream theater overbuilt for N=1 |

**Recommended engineering order (later):** crash recovery + state locking → media ledger lock → public voice auth → bubble publish lock → docs truth → collab only if arming.

**Recommended product freeze (later):** no new Tier-C collab/voice rewrites until Tier A reliability is boring-green.

---

## Severity-ranked findings

IDs are stable for tracking. Severity: **C** critical, **H** high, **M** medium, **L** low.

### Critical

| ID | Title | Where (runtime unless noted) | Notes |
| --- | --- | --- | --- |
| **C1** | Unauthenticated public voice mesh | `public_proxy.py` (`/Agency*`, `/ws`); `voice_room/server.py` join; default bind `0.0.0.0:8090` | Same public host as RC; no RC session/token on WS join |
| **C2** | Unlocked `state.json` RMW | `wake_lib.load_state` / `save_state`; all enqueue/drain/mark/bubble writers | Lost pending, lost pins, double-process; shared `state.tmp` |
| **C3** | Crash after dequeue loses mid | `rc_operator_agent._drain_pending_wakes` pop-before-process; no startup clear of `in_flight_ids`; no boot drain | Stuck `…`; orphan Grok child; mid never re-enqueued |
| **C4** | Force-clear room lock ~3s | Drain: 6×0.5s then `force_clear_wake_lock` without live-holder check | Can steal live concurrent wake; dual session/bubble risk |

### High

| ID | Title | Where | Notes |
| --- | --- | --- | --- |
| **H1** | Public RC + 2FA hard-disabled | `docker-compose.yml` `Accounts_TwoFactorAuthentication_Enabled=false` | Password leak ⇒ full workspace + wake power |
| **H2** | Attachment download SSRF gaps | `download_rc_file`: host-only match; redirects followed; auth on first hop | Re-validate host+port+scheme after redirects; path allowlist |
| **H3** | Media ledger races / bad claim | `rc_post_media.py` load/save ledger; `success:false` still claims `file_id` | Double image or permanent skip without `--force` |
| **H4** | Activity bubble last-writer race + second final | Thought flusher vs FINAL; finalize fail → `post_as_grok` | Breaks one-bubble / no-duplicate contract |
| **H5** | Process exception drops item + may kill drain | `_process_pending_item` raise after pop; re-raise exits drain loop | Not requeued; remaining queue starved until next enqueue |
| **H6** | “Restricted” still high power | `--permission-mode auto` on agency/IdeaProjects over public ngrok | Naming theater vs true tool allowlist |
| **H7** | Doc/runtime truth drift | e.g. `docs/operations.md` free ngrok domain; stream defaults; auto-create | See [Docs drift](#docs-drift) |

### Medium

| ID | Title | Where | Notes |
| --- | --- | --- | --- |
| **M1** | Agy collab parity gaps | `_process_agy_collab_item` | No in-flight; no missing-cwd FINAL_ERR; approval bypass; dormant when flags off |
| **M2** | Elevation steal on collab handoff | Grok path consumes `!admin once` for any author | If collab armed, bot hop can consume principal elevation |
| **M3** | Hop budget soft / high | `rc_collab` default 100; no clamp; resume doesn’t reset | Cost runaway when armed |
| **M4** | `RC_WAKE_MAX_CONCURRENT` ineffective | Global `_drain_lock` serializes all wakes | Docs/IMP-10 overclaim multi-room parallel |
| **M5** | Attachment/audio/call-media never pruned | `prune_log_artifacts` skips subdirs | Disk growth |
| **M6** | `video/mp4` treated as audio → Whisper | `wake_lib` type classification | Blocks drain up to STT timeout |
| **M7** | Sync STT on critical path | Operator drain | One voice note stalls all rooms |
| **M8** | Proxy + voice not in launchd installer | `install-launchd.sh` | Partial outages after reboot |
| **M9** | ngrok upstream port drift (3000 vs 9080) | `NGROK.md` vs `call/README.md` | Phone Call dead if wrong |
| **M10** | Empty-reply retry / missing-cwd / exception untested | `ops/rocketchat/tests/` | Green suite can miss known burns |
| **M11** | Map relative paths not confined under IdeaProjects | `resolve_project_cwd` + `ensure_project_dir` | `..` / absolute map escape |
| **M12** | Reconnect without catch-up for known rooms | Operator WS reconnect | Messages during outage lost |
| **M13** | Stream-default long `…` silence | Stream on → no meta heartbeat without thoughts | Looks hung on tool-heavy wakes |
| **M14** | Salvage prefers first bullet block | `wake_telemetry.extract_salvageable` | Can salvage wrong early thrash |
| **M15** | Secrets file mode not enforced at load | `load_env` / `load_rc_config` | Compose `.env` is hardened; secrets file may not be |
| **M16** | Exception / agy stderr may surface into RC | Drain error bubble; `format_agy_cli_error` | Paths / API noise in room |
| **M17** | `config.example` auto-create still `0` | `ops/rocketchat/config.example` | Re-arms kill-switch if copied |

### Low

| ID | Title | Notes |
| --- | --- | --- |
| **L1** | Soft-match slug collisions (`foo-bar` ↔ `foobar`) | Wrong IdeaProjects sibling |
| **L2** | Map key matching not fully case-insensitive | Casing rename fragility |
| **L3** | Thought markdown unsanitized for RC | Accidental bold/mentions |
| **L4** | Fixed 1s sleep before FINAL even when no mid-updates | Latency for no 429 benefit |
| **L5** | Health `rooms_count=0` / misleading fields | False ops picture |
| **L6** | Dead reason codes `special` / `agency_fallback` in docstring | Doc noise |
| **L7** | Dual entrypoint residual (`rc_dm_poll`) | Shared state if re-enabled |
| **L8** | DDP always password-login; PAT incomplete for WS | Token-only install still needs password |

---

## Priority fix order (when addressing)

Use this as the default implementation sequence unless a live incident forces otherwise.

| Order | Track | Finding IDs | Outcome |
| --- | --- | --- | --- |
| **1** | State + crash recovery | C2, C3, C4, H5, M4 | flock/mutex + unique tmp; startup reconcile in_flight/pending; never force-clear live holder; requeue-on-failure; real multi-room only if needed |
| **2** | Media + downloads | H2, H3, M5, M6 | Atomic ledger claim; fix success:false; redirect-safe download; prune caches; exclude full video from Path A Whisper |
| **3** | Public voice / edge | C1, H1, M8, M9 | Auth join or localhost-only voice; align ngrok→9080; launchd for proxy+voice; revisit 2FA |
| **4** | Bubble UX contract | H4, M13 | Serialize bubble publishes; re-check finalized before send; ban second final post (or label fallback) |
| **5** | Docs + config truth | H7, M17, M9 | Free domain, stream defaults/throttles, auto-create, public_proxy in maps |
| **6** | Tests P0 | M10 | See [P0 tests](#p0-tests-to-add) |
| **7** | Collab (only if arming) | M1–M3 | in-flight; no elevation steal; hop clamp; real tool scope |

---

## P0 tests to add

Add under `~/.grok/agency/ops/rocketchat/tests/` (isolated mocks; no live RC required).

1. **`test_empty_reply_retry_once`** — Cancelled+empty → interim + requeue once with same bubble; second empty → FINAL_ERR, no third.
2. **`test_missing_cwd_finalizes_without_wake`** — kill-switch/missing dir → no `wake_grok`, FINAL_ERR body, mid processed.
3. **`test_process_item_exception_surfaces_and_queue_policy`** — assert disposition (today: not requeued + re-raise); prefer fixing policy then testing it.
4. **`test_media_confirm_idempotent`** — ledger skip same bytes; claim on HTTPError; no double confirm; success:false does not permanent-skip without clear policy.

**P1:** in_flight blocks re-enqueue; finalize-fail posts at most once; hop-budget drain pause.

---

## Edge-case scorecard

| Case | Status | Main impact |
| --- | --- | --- |
| New channel before 60s rescan | Partial | Delayed watch; catch-up last 12 msgs |
| Principal edits message | Unhandled after process | Mid-idempotent |
| Message deleted mid-wake | Unhandled | Ghost reply; no cancel |
| Grok hang / timeout | Handled | Default 600s → kill + FINAL_ERR |
| Disk full / log unwritable | Partial | Queue/state risk |
| Mongo/RC restart mid-wake | Partial | No catch-up for known rooms |
| Concurrent multi-room | Partial | Serial drain |
| Unicode/markdown in thoughts | Partial | UTF-8 ok; RC markup unsafe |
| Huge attachment | Handled | 20 MiB + max files |
| Resume session invalid | Handled | One fresh-session retry |
| Operator crash, child running | **Partial / worst residual** | Orphan Grok; stuck `…`; mid lost |
| Clock skew / ts ordering | Partial | Locks skew-safe if pid live |

---

## What is solid (do not regress)

- Principal-only intake; mark processed after wake attempt (Grok path).
- Reply file → salvage → structured FINAL_ERR (`choose_final_body`).
- Missing-cwd FINAL_ERR for Grok; auto-create default ON (2026-07-14).
- Empty Cancelled one-shot recovery design.
- Loopback RC bind; domain pin refuses `*.ngrok-free.dev`; compose `.env` mode 600.
- List-argv wakes (no shell injection); basename sanitization + inbound size caps (happy path).
- Collab master **default off** (`RC_AGY_COLLAB=0`).
- Usability contracts §1–§3 (queue / lock / enqueue-during-drain) with real drain tests.

---

## Docs drift

Concrete mismatches to fix when doing H7:

| Topic | Wrong / stale | Truth (code/live) |
| --- | --- | --- |
| Public URL in `docs/operations.md` | `cash-scalded-enhance.ngrok-free.dev` | `velocityworks-rc.ngrok.app` (forbidden free domain) |
| Auto-create | IMP-19 requirements/CHANGELOG/`config.example` often **off** | Default **on** (`1`); kill-switch `0` |
| `RC_WAKE_STREAM` | Feature tables often default **0** | Code default **1** |
| Stream throttle | Docs 800 ms / 40 updates | Code ~2000 ms / 12 |
| Phone Call path | Docs emphasize LAN `:8090` | Production phone needs ngrok + **proxy `:9080`** |
| `RC_WAKE_MAX_TURNS` notes | Some still 12 | Live **100** |
| NF-10 / lead-peer | Docs + REVIEW “mitigated” | **Not implemented** in Python runtime |
| IMP-17 “Done” | Claims no contradictory public URL | Broken by operations free-domain URL |

Canonical intent for auto-create: [19-channel-autocreate-policy/README.md](../improvements/19-channel-autocreate-policy/README.md) (superseded default 2026-07-14).

---

## Collab posture

| Mode | Assessment |
| --- | --- |
| Production today | Collab **dormant** (master off, no `mode=agy-collab` profiles) — low live risk |
| If armed | Dual-agent live: agy outside IMP-01 approval, elevation steal, hop budget soft, double-wake race |
| NF-SPEC-10 lead_peer_full | Documentation only — do not treat as runtime-hardened |

---

## Contrarian product notes (for prioritization)

Captured so scope debates do not re-litigate from scratch:

1. Real product is **N=1 principal → one bubble → Grok on a Mac**.
2. Dual-identity collab + peer-bar/footer FSM is multi-agent cosplay on one host.
3. Streaming thoughts are throttled REST edits; FINAL_OK still comes from the reply file.
4. “Restricted” + `auto` is not a multi-tenant safety story.
5. Prefer nested optional assist over dual RC bots; freeze Tier C until Tier A is boring.

---

## Specialist coverage (audit trail)

Heavy review used **12/12** successful read-only specialists (2026-07-14). Roles:

| Slot | Focus |
| --- | --- |
| 1 | Security / auth / secrets |
| 2 | Wake lifecycle correctness |
| 3 | Project cwd / auto-create |
| 4 | Streaming / telemetry / UX |
| 5 | Collab dual-identity |
| 6 | Attachments / media / voice notes |
| 7 | State / concurrency / persistence |
| 8 | Ops / launchd / docker / network |
| 9 | Tests / contracts / coverage gaps |
| 10 | Docs / architecture drift |
| 11 | Contrarian / overengineering |
| 12 | Edge cases / failure injection |

Raw specialist output is not stored in-repo; this document is the durable synthesis.

---

## How to use this later

1. Pick a track from [Priority fix order](#priority-fix-order-when-addressing).
2. Optionally open an IMP-style folder under `docs/improvements/` (21+) with requirements + test plan.
3. Implement in `~/.grok/agency/ops/rocketchat/`; keep this doc’s IDs in commit/PR messages (`fix C3`, `test H3`).
4. When an ID is fully addressed, mark it **Done** in a short table at the bottom of this file (append-only status section).

### Status tracker (append as work lands)

| ID | Status | Date | Notes |
| --- | --- | --- | --- |
| — | open | 2026-07-14 | Initial findings dump; no remediations in this pass |

---

## Out of scope for this document

- Live secret values or credential dumps
- Implementing fixes (documentation only)
- Re-running the 12-specialist review (re-open only if large code moves)
