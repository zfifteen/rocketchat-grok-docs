# ops/rocketchat — expanded reviewable mirror (Option 1)

**Model:** Git holds a **reviewable mirror** of the Rocket.Chat operator stack.
**Live runtime** remains: `~/.grok/agency/ops/rocketchat/` (launchd, secrets, state, logs, venv).

| Role | Path |
| --- | --- |
| Reviewable source (this tree) | `rocketchat-grok-docs/ops/rocketchat/` |
| Live deploy target | `~/.grok/agency/ops/rocketchat/` |
| Secrets (never in git) | `~/.grok/agency/secrets/rocketchat*.env` |
| Logs | `~/logs/rocketchat-*-wake/` |

**Option 2 later:** make this tree canonical and deploy *to* live only.
**Option 3 (run from repo):** off the table.

---

## What is mirrored

Reviewable code and examples:

- `wake/` — operator agent, wake_lib, telemetry, pure IMP-22/23 modules, prompts, playbooks, run scripts  
- `tests/` — unit/integration suites (some need live RC / `RC_TEST_RUNTIME`)  
- `scripts/` — health, digest, compose env, prune, backup  
- `templates/` — launchd plist templates (IMP-11)  
- `call/`, `voice_room/` — retired Call/voice archive (defaults off; see `VOICE_RETIRED.md`)  
- Root docs: `MULTI_OPERATOR.md`, operator notes, `NO_DUPLICATE_POSTS.md`, `docker-compose.yml`, `config.example`, `.env.example`, `requirements.txt`, install helpers  

## What is **never** mirrored (exclude list)

| Exclude | Why |
| --- | --- |
| `.env` | Real compose admin password |
| `.venv/` | Host rebuild via `setup-venv.sh` |
| `__pycache__/`, `.pytest_cache/`, `.benchmarks/` | Ephemeral |
| `wake/*_state.json`, `wake/state.json`, locks | Live queue/session state |
| Anything under `~/.grok/agency/secrets/` | Credentials |

Use `scripts/sync-mirror-from-live.sh` / `scripts/deploy-mirror-to-live.sh` so excludes stay consistent.

---

## Pure tests (no RC network) — run from docs repo

```bash
cd /Users/velocityworks/IdeaProjects/rocketchat-grok-docs

python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py   # IMP-23 S5 — expect 22/22
python3 ops/rocketchat/tests/test_wake_ux_imp23.py          # Wave 1 — expect 16/16
python3 ops/rocketchat/tests/test_wake_denials_imp22.py     # IMP-22 — expect 6/6
python3 ops/rocketchat/tests/test_multi_round_collab.py     # multi-round pure — expect 17/17
```

`POLICY_WAKE` prefers this mirror’s `wake/` when pure modules are present.

---

## Sync scripts

```bash
# After editing live host, pull reviewable files into git working tree
./ops/rocketchat/scripts/sync-mirror-from-live.sh

# After merging git changes, push reviewable files to live (does not touch secrets/state/venv)
./ops/rocketchat/scripts/deploy-mirror-to-live.sh

# Check critical file SHA parity (exit 1 if drift)
./ops/rocketchat/scripts/check-mirror-parity.sh

# Reclaim zombie in_flight_ids + dead room locks (backs up first)
./ops/rocketchat/scripts/reclaim-stuck-wake-state.sh
./ops/rocketchat/scripts/reclaim-stuck-wake-state.sh --drop-pending --kickstart

# Opt-in restore of dropped pending_wakes (LIST backups; does not auto-spam)
./ops/rocketchat/scripts/restore-pending-wakes.sh LIST
# ./ops/rocketchat/scripts/restore-pending-wakes.sh ~/logs/rocketchat-state-reclaim/<stamp>/state.json.pending_wakes.json

# Then restart operators so Python reloads:
UID_NUM=$(id -u)
for label in operator hermes-operator agy-operator feynman-operator nie-operator; do
  launchctl kickstart -k "gui/${UID_NUM}/com.velocityworks.rocketchat-${label}"
done
```

### Stage 1 habit (keep live ↔ mirror aligned)

| You edited… | Then… |
| --- | --- |
| Host (`~/.grok/agency/…`) | `sync-mirror-from-live.sh` → review `git diff` → commit |
| Git (`ops/rocketchat/`) | merge → `deploy-mirror-to-live.sh` → kickstart |
| Unsure | `check-mirror-parity.sh` |

Never commit `.env` or `*_state.json`.

---

## Layout (high level)

```
ops/rocketchat/
├── README.md                 ← you are here
├── config.example            ← env documentation (CHANGE_ME only)
├── .env.example              ← compose template (CHANGE_ME only)
├── docker-compose.yml
├── requirements.txt
├── install-launchd.sh
├── templates/*.plist.tmpl
├── wake/                     ← operators + pure policy
│   ├── rc_operator_agent.py  ← full agent (reviewable)
│   ├── wake_lib.py
│   ├── wake_telemetry.py
│   ├── wake_inflight_ux.py   ← IMP-23 S5 pure
│   ├── wake_ux_imp23.py
│   ├── wake_denials.py
│   └── …
├── tests/
├── scripts/
│   ├── sync-mirror-from-live.sh
│   ├── deploy-mirror-to-live.sh
│   └── rc_wake_digest.py
├── call/                     ← retired
└── voice_room/               ← retired
```

---

## Workflow (Option 1)

1. Prefer editing pure modules / docs in **this repo**; PR + review.  
2. Or edit live, then `sync-mirror-from-live.sh` and commit.  
3. After merge: `deploy-mirror-to-live.sh` + kickstart.  
4. Never commit `.env` or state JSON.

When Option 1 is stable, decide whether to implement **Option 2** (git canonical → deploy-only live).
