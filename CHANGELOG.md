# Changelog

## 2026-07-10

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
