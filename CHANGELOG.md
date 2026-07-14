# Changelog

## 2026-07-14

- **Multi-agent integration guide:** [docs/agent-integration-guide.md](docs/agent-integration-guide.md) — step-by-step for other agents to create an RC user, isolated secrets/state/logs, parallel operator + launchd, tag-to-talk, backend notes (Grok/Hermes), verification checklist, pitfalls. Runtime pointer: `~/.grok/agency/ops/rocketchat/AGENT_INTEGRATION_GUIDE.md`. Linked from README Start here.
- **Heavy code review findings documented:** [docs/reviews/2026-07-14-rc-integration-heavy-review.md](docs/reviews/2026-07-14-rc-integration-heavy-review.md) — severity-ranked backlog (C1–C4, H1–H7, medium/low), priority fix order, P0 tests, edge-case scorecard, docs drift, collab posture. Linked from README + improvements INDEX. Findings only; remediations not implemented in this pass.
- **Auto-create default ON** (runtime, same day): `RC_AUTO_CREATE_PROJECTS=1` in code/launchd/template; IMP-19 README notes supersede default-off acceptance. Related to review H7/M17.
- **Antigravity backend formally documented:** `agent-integration-guide.md` updated to list `agy` as a first-class supported backend. Runtime `rc_commands.py` patched to support global `RC_WAKE_MODEL` override via launchd environment variables (enabling dedicated secondary operators like `claude`).

## 2026-07-13

- **README hero banner:** geometric brand mark (candidate 4) at `docs/assets/hero-banner.jpg`; candidates retained under `docs/assets/banner-candidates/`.

## 2026-07-12

- **NF-SPEC-10 + NF-IP-10 + NF-TP-10 — Lead–peer full collab.** [new-features/10-lead-peer-full-collab/](new-features/10-lead-peer-full-collab/) — full documentation chain: protocol spec, `!goal` implementation ladder (GOAL-00…22), meticulous [test-plan.md](new-features/10-lead-peer-full-collab/test-plan.md) (L0–L6, AC traceability, per-GOAL gates, live opt-in).
- **NF-SPEC-10 v1.1 — adversarial review mitigations.** [REVIEW.md](new-features/10-lead-peer-full-collab/REVIEW.md) (AGY): all 7 findings accepted — control-plane principal gate order, footer trust boundary, trivial anti-gaming, owned_paths sandbox, hop default 12, agent dual-mention Reject, lock-before-classify, REST identity isolation. SPEC/IP/TP updated.
- **Program goal (parked): install refactor → public share.** [docs/goals/install-refactor-then-public-share.md](docs/goals/install-refactor-then-public-share.md) — local install/config cleanup first, packaging only after laptop green; Tier A product sketch; Phase 0–3; resume checklist. Linked from README. No implementation this day.
- **NF-06…09 docs packs** under [new-features/](new-features/) (reactions, outbound Imagine path, DM health card, agy collab enablement) from principal enhancement list #11/#13/#15/#16.
- **Operator defaults:** `RC_WAKE_MAX_TURNS` raised 12 → **100** (code, launchd, live). Control plane help/docs prefer **`!` prefix** (Rocket.Chat steals `/` via rocket.cat).
- **NF-05 runtime shipped (permanent inbound attachments):** Live operator now rehydrates with retries, downloads images/docs under policy (same-host, size cap, thumb skip), injects local paths into the wake prompt, and `reply_prompt.txt` requires `read_file` before “I can’t view attachments.” Runtime: `~/.grok/agency/ops/rocketchat/wake/{wake_lib,rc_operator_agent,reply_prompt}.txt`; tests: `ops/rocketchat/tests/test_nf05_reading_attachments.py` (13 passed). Docs: [message-flow §F](docs/message-flow.md), [feature 05](new-features/05-reading-attachments/). Operator launchd restarted.

## 2026-07-11

- **New feature 05 (reading attachments):** [new-features/05-reading-attachments/](new-features/05-reading-attachments/) full documentation chain — research, **NF-SPEC-05**, **NF-TP-05**, **NF-IP-05**. Covers inbound Rocket.Chat pictures/files: rehydrate → download under policy → path inject → Grok `read_file`; grounded in live operator code + 2026-07-11 DM attach evidence (caption-only prompt, thumb download, partial image pipeline). Structural tests: `tests/test_feature5_reading_attachments.py`. Index/README updated; ship-order note **2 → 5 → 3 → 1**.

## 2026-07-10

- **New-features layout reorg:** each feature is its own subfolder under [new-features/](new-features/README.md) (`01`–`03` full chain co-located; `04` research-only). Top-level index is navigable; structural tests assert bundle layout.
- **New feature research (4):** [new-features/04-agy-rocketchat-collab/](new-features/04-agy-rocketchat-collab/) — long-horizon Grok↔Antigravity collab via Rocket.Chat; dual account **`agy`** + @mention handoffs; many-turn durability; draft **[`profiles/`](new-features/04-agy-rocketchat-collab/profiles/)** AGENTS/agent identity for collab. Research only. Structural tests: `tests/test_feature4_agy_collab_research.py`.
- **NF-SPEC-04:** [new-features/04-agy-rocketchat-collab/spec.md](new-features/04-agy-rocketchat-collab/spec.md) — meticulous dual-peer @mention collab technical specification (documentation only; bundle layout).
- **NF-TP-04:** [new-features/04-agy-rocketchat-collab/test-plan.md](new-features/04-agy-rocketchat-collab/test-plan.md) — thorough test plan for dual-peer collab (documentation only).
- **IMP-15 evidence-first:** `test_imp15_compose_secrets_dry` runs shipped
  `generate_compose_env.sh` (mode 600) + live `backup_mongo.sh` (non-empty tar) +
  operations/filesystem-map upgrade docs; usability PASS records `backup_bytes`.
- **Voice Call T2 PASS:** lobby-free `voice_room` server + Jitsi domain → LAN `:8090`; dual-peer preflight `remote_rms≈0.28`. launchd `com.velocityworks.rocketchat-voice-room`. Tests: `tests/test_voice_room_path.py`.  
- Preflight deep T2 earlier **FAIL** root cause was public meet.jit.si lobby; protocol + research retained.  
- Added/updated **[docs/research-voice-media-path.md](docs/research-voice-media-path.md)**: hard requirement = voice calls **in Rocket.Chat**. **Recommendation:** RC Call → agent-capable SFU (LiveKit) → Grok Voice participant; demote Path C.
- **Skeptic fix:** wired `load_rc_config` into operator/media/call mains; PGS
  `resolve_operator_auth` token path; `config.example` + `.env.example` +
  launchd `templates/*.plist.tmpl`; honest tests imp03/imp11/imp20.
- Added **[docs/implementation-plan-voice-calls.md](docs/implementation-plan-voice-calls.md)**: Path C-oriented plan (partially superseded for production media choice by research doc).
- Linked voice docs from `README.md`; Path C failure status in `docs/message-flow.md` / architecture.
- **IMP-02…20 closed** (Done or Won't do for IMP-16 extract cutover): wake-lock TTL+PID,
  secrets prompt hygiene, Docker healthcheck (healthy on 127.0.0.1), REST auth cache,
  log prune, single config loader, turn limits, launchd installer, venv, health.json,
  per-room locks/state v2, compose env generator + mongo backup scripts, poll quarantine,
  channel auto-create default off, bot token auth path. Suites: integration+usability exit 0.
- **IMP-01 implemented:** wake approval modes (`restricted` default / `admin` opt-in);
  tests green; launchd + `ROCKETCHAT.md` updated; operator kickstarted.
- Added **improvements package**: `docs/improvements/INDEX.md` plus 20 items
  (each with `README.md`, `requirements.md`, `test-plan.md`), linked from
  project README, architecture, and operations.
- Initial documentation project created.
- Captures live layout: agency ops tree, secrets, launchd, logs, IdeaProjects
  channel mapping, PGS notify adjacency.
