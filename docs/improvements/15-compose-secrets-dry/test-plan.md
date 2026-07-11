# Test plan: Compose/secrets DRY + Mongo backup policy

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-15-TP |
| **Requirements** | [IMP-15](./requirements.md) |

---

## Test cases

### T1 — DRY generate

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Generate compose env from secrets | Keys match; modes 600 |
| 2 | `docker compose config` / file contents | ROOT_URL equals secrets public/root |

**Pass:** R1, R2.

### T2 — Backup

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Run backup script to temp path | Artifact size > 0 |
| 2 | Optional restore to disposable volume | RC starts (heavy — optional) |

**Pass:** R3, R4.

### T3 — Upgrade doc review

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Read upgrade section in operations docs | Mentions backup, pin, smoke tests |
| 2 | Filesystem map lists both scripts | Paths present |

**Pass:** R5.

---

## Execution record (2026-07-10, evidence-first)

Harness: **`test_imp15_compose_secrets_dry`** (shipped scripts via subprocess).

| Case | Result | Evidence |
| --- | --- | --- |
| T1 generate_compose_env.sh | **PASS** | mode `0o600`, ROOT_URL match, password absent from stdout |
| T2 backup_mongo.sh | **PASS** | `backup_bytes≈34_700_521` against `agency-rocketchat_mongodb_data` |
| T3 docs | **PASS** | `operations.md` + `filesystem-map.md` include both scripts + upgrade (backup → pin → smoke `/api/info`) |

Suite log: `{SCRATCH}/rc_usability.log` — line `[PASS] imp15_compose_secrets_dry`.  
Also: first-run probe under `{SCRATCH}/imp15_probe/`, full suite exit 0.

**Do not** treat “scripts exist on disk” as a gate; only the harness PASS above.
