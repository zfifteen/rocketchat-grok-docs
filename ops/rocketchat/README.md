# ops/rocketchat — Stage 2 (git canonical)

**Model (Stage 2 / Option 2):**  
**Git is the write source of truth** for integration code.  
**Live** (`~/.grok/agency/ops/rocketchat/`) is a **deploy target** only (launchd, secrets, state, logs, venv).

| Role | Path |
| --- | --- |
| **Canonical source (edit here)** | `rocketchat-grok-docs/ops/rocketchat/` |
| Live deploy target (do not edit day-to-day) | `~/.grok/agency/ops/rocketchat/` |
| Secrets (never in git) | `~/.grok/agency/secrets/rocketchat*.env` |
| Logs | `~/logs/rocketchat-*-wake/` |

**Option 3 (run operators from the docs repo):** off the table.  
**Emergency host edits:** allowed only with immediate `sync-mirror-from-live.sh` + commit (see below).

---

## Normal workflow (Stage 2)

```text
edit ops/rocketchat/  →  pure tests  →  commit / PR  →  merge main
        →  ./scripts/after-merge-deploy.sh   # deploy + parity + kickstart
```

```bash
cd /Users/velocityworks/IdeaProjects/rocketchat-grok-docs

# 1. Develop in git
# 2. Pure gates
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py
python3 ops/rocketchat/tests/test_wake_ux_imp23.py
python3 ops/rocketchat/tests/test_wake_denials_imp22.py
python3 ops/rocketchat/tests/test_multi_round_collab.py

# 3. After merge to main (or on main after commit)
./ops/rocketchat/scripts/after-merge-deploy.sh
```

`after-merge-deploy.sh` = `deploy-mirror-to-live.sh` + `check-mirror-parity.sh` + operator kickstart.

---

## What lives in git

- `wake/` — operator agent, wake_lib, telemetry, pure IMP-22/23 modules, prompts, playbooks, run scripts  
- `tests/` — unit/integration suites  
- `scripts/` — health, digest, compose env, deploy/sync/reclaim  
- `templates/` — launchd plist templates (IMP-11)  
- `call/`, `voice_room/` — retired Call/voice archive  
- Root docs: `MULTI_OPERATOR.md`, operator notes, `docker-compose.yml`, `config.example`, `.env.example`, `requirements.txt`  

## What never leaves the host

| Exclude | Why |
| --- | --- |
| `.env` | Real compose admin password |
| `.venv/` | Host rebuild via `setup-venv.sh` |
| `__pycache__/`, `.pytest_cache/` | Ephemeral |
| `wake/*_state.json`, locks | Live queue/session state |
| `~/.grok/agency/secrets/*` | Credentials |
| Installed LaunchAgents | Machine-specific after `install-launchd.sh` |

---

## Scripts

| Script | Stage 2 use |
| --- | --- |
| **`after-merge-deploy.sh`** | **Default:** deploy → parity check → kickstart |
| `deploy-mirror-to-live.sh` | Deploy only (`--kickstart` optional) |
| `check-mirror-parity.sh` | Fail if critical files drift |
| `sync-mirror-from-live.sh` | **Emergency only** — pull host edits back into git |
| `reclaim-stuck-wake-state.sh` | Clear zombie inflight / dead locks |
| `restore-pending-wakes.sh` | Opt-in restore of dropped pending |

```bash
# Emergency host hotfix path (discouraged)
# 1) edit live only if operators are on fire
# 2) immediately:
./ops/rocketchat/scripts/sync-mirror-from-live.sh
git add ops/rocketchat && git commit -m "sync: host emergency fix"
git push
# 3) treat git as truth again; next change starts in the repo
```

---

## Pure tests (no RC network)

```bash
cd /Users/velocityworks/IdeaProjects/rocketchat-grok-docs

python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py   # 22/22
python3 ops/rocketchat/tests/test_wake_ux_imp23.py          # 16/16
python3 ops/rocketchat/tests/test_wake_denials_imp22.py     # 6/6
python3 ops/rocketchat/tests/test_multi_round_collab.py     # 17/17
```

Live venv suites (after deploy):  
`~/.grok/agency/ops/rocketchat/.venv/bin/python tests/test_usability_contracts.py`

---

## Layout (high level)

```
ops/rocketchat/
├── README.md                 ← Stage 2 model (this file)
├── config.example
├── .env.example
├── docker-compose.yml
├── requirements.txt
├── install-launchd.sh
├── templates/*.plist.tmpl
├── wake/                     ← operators + pure policy
├── tests/
├── scripts/
│   ├── after-merge-deploy.sh   ← Stage 2 default
│   ├── deploy-mirror-to-live.sh
│   ├── check-mirror-parity.sh
│   ├── sync-mirror-from-live.sh  ← emergency only
│   ├── reclaim-stuck-wake-state.sh
│   └── …
├── call/                     ← retired
└── voice_room/               ← retired
```

---

## History

| Stage | Model |
| --- | --- |
| **0** | Code only under `~/.grok/agency` |
| **1** | Expanded reviewable mirror; live still co-edited |
| **2 (now)** | Git canonical; live = deploy target |
| **3** | Run from repo — **rejected** |
