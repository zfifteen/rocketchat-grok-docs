# Requirements: Compose/secrets DRY + Mongo backup policy

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-15 |
| **Priority** | Medium |
| **Phase** | D |
| **Status** | Done (2026-07-10) |
| **Related** | [IMP-03](../03-single-config-surface/), [IMP-06](../06-network-exposure/) |

---

## Problem

Admin password and ROOT_URL duplicated in `secrets/rocketchat.env` and `ops/rocketchat/.env`. Mongo data volume has no documented backup. Image pin has no upgrade checklist.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Single source of truth for admin/root URL; compose env generated or env_file pointed at secrets subset. |
| R2 | Generation script never prints secrets; mode 600 on output. |
| R3 | Written backup procedure: `docker run`/`mongodump` or volume tar — choose one and script it. |
| R4 | Restore drill documented (empty host OK). |
| R5 | Upgrade notes: pin version, backup first, compose pull, smoke `/api/info` + login. |

---

## Acceptance criteria

- [x] Changing ROOT_URL in one place updates compose effective config.
- [x] Backup script produces non-empty artifact.
- [x] Docs linked from operations + filesystem map.

## Implementation notes (2026-07-10)

generate_compose_env.sh + backup_mongo.sh

## Skeptic fix (2026-07-10) — evidence-first

Gated by **`test_imp15_compose_secrets_dry`** in `tests/test_usability_contracts.py`:

- **T1** `generate_compose_env.sh` → mode 600, ROOT_URL match, password not on stdout
- **T2** `backup_mongo.sh` → non-empty tar against live `agency-rocketchat_mongodb_data`
- **T3** `operations.md` + `filesystem-map.md` link both scripts + upgrade smoke path

PASS evidence: scratch `rc_usability.log` line `imp15_compose_secrets_dry`.
