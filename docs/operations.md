# Operations

**Last reviewed:** 2026-07-10

Authoritative short runbook for URLs and phone setup remains:

`~/.grok/agency/ops/ROCKETCHAT.md`

This page is a durable checklist aligned with that runbook.

**Suggested config fixes (requirements + test plans):**  
[docs/improvements/INDEX.md](improvements/INDEX.md)

---

## Prerequisites (phone path)

- Mac **awake**
- **Docker Desktop** running
- Compose stack up (`agency-rocketchat`)
- **ngrok** launchd agent running
- **Operator** launchd agent running
- Secrets present at `~/.grok/agency/secrets/rocketchat.env`

---

## Status checks

```bash
# Public edge (skip ngrok browser warning header)
curl -s -H 'ngrok-skip-browser-warning: 1' \
  https://cash-scalded-enhance.ngrok-free.dev/api/info | head -c 120; echo

# Tunnel agent
launchctl print gui/$(id -u)/com.velocityworks.ngrok-rocketchat | head -15

# Operator agent
launchctl print gui/$(id -u)/com.velocityworks.rocketchat-operator | head -20

# Containers
cd ~/.grok/agency/ops/rocketchat && docker compose ps

# Recent operator log
tail -n 40 ~/logs/rocketchat-dm-wake/operator-agent.log
```

Local only:

```bash
curl -s http://127.0.0.1:3000/api/info | head -c 120; echo
```

---

## Restart

```bash
# Tunnel
launchctl kickstart -k gui/$(id -u)/com.velocityworks.ngrok-rocketchat

# Operator
launchctl kickstart -k gui/$(id -u)/com.velocityworks.rocketchat-operator

# Rocket.Chat stack
cd ~/.grok/agency/ops/rocketchat && docker compose up -d
```

Conference / Jitsi settings (admin API):

```bash
~/.grok/agency/ops/rocketchat/enable_conference_calls.sh
```

---

## Tests

```bash
python3 ~/.grok/agency/ops/rocketchat/tests/test_rc_integration.py
python3 ~/.grok/agency/ops/rocketchat/tests/test_usability_contracts.py
```

Notes: `tests/README.md`, contracts: `tests/USABILITY_CONTRACTS.md`.

---

## Logs to open when debugging

| Symptom | Look at |
| --- | --- |
| No replies | `~/logs/rocketchat-dm-wake/operator-agent.log` |
| Operator not starting | `…/operator-agent.stderr.log`, launchd stderr |
| Phone cannot connect | `~/logs/ngrok-rocketchat/`, `docker compose ps` |
| Duplicate images | `…/media-post-ledger.json`, `NO_DUPLICATE_POSTS.md` |
| Call fails | `…/call-bot.log`, `call-bot.spawn.log` |
| Voice note fails | `…/audio/`, Whisper install / `RC_WHISPER_*` |

---

## Common fixes

| Problem | Likely fix |
| --- | --- |
| Public URL dead | Restart ngrok launchd; confirm Hobbyist domain in secrets / NGROK.md |
| Localhost dead | `docker compose up -d` in `ops/rocketchat` |
| Thinking… forever | Grok CLI/API; check wake prompt dumps; operator log |
| Wrong project files edited | Check `channel_projects.json` and room slug → IdeaProjects |
| Double posts | Stop manual confirm/post loops; use only `rc_post_media.py` for media |
| New channel ignored | Wait ≤60s for room refresh, or restart operator after invite |

---

## Compose env + Mongo backup / upgrade (IMP-15)

Scripts live under `~/.grok/agency/ops/rocketchat/scripts/`:

| Script | Purpose |
| --- | --- |
| **`generate_compose_env.sh`** | Build compose `.env` (mode **600**) from `secrets/rocketchat.env` — single source of admin/ROOT_URL |
| **`backup_mongo.sh`** | Tar the Docker Mongo volume `agency-rocketchat_mongodb_data` to a path you pass |

```bash
# Generate compose .env from secrets (does not print passwords)
RC_SECRETS_PATH=~/.grok/agency/secrets/rocketchat.env \
  ~/.grok/agency/ops/rocketchat/scripts/generate_compose_env.sh \
  ~/.grok/agency/ops/rocketchat/.env

# Backup Mongo data volume (non-empty .tar.gz)
~/.grok/agency/ops/rocketchat/scripts/backup_mongo.sh \
  ~/backups/rocketchat-mongo-$(date +%Y%m%d).tar.gz
```

### Upgrade Rocket.Chat image (smoke path)

1. **Backup** with `backup_mongo.sh` (artifact size must be > 0).  
2. **Pin** the image tag in `docker-compose.yml` (e.g. `rocket.chat:8.6.0` → next pin).  
3. `docker compose pull && docker compose up -d` in `ops/rocketchat`.  
4. **Smoke:** `curl -s http://127.0.0.1:3000/api/info` and operator login / one DM Thinking… cycle.  

Do not upgrade without step 1. See also [IMP-15](improvements/15-compose-secrets-dry/).

---

## Do not

- Commit or paste `rocketchat.env` / compose `.env` / ngrok authtoken.
- `chat.postMessage` a second final answer after Thinking… exists.
- Call `rooms.mediaConfirm` twice on the same `fileId`.
- Treat PGS notify failure as a research failure (ops-only).
