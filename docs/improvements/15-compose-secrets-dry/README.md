# 15 — Compose/secrets DRY + Mongo backup policy

**Impact:** Medium · **Phase:** D · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Generate compose `.env` from the single secrets source; document Mongo volume backup/restore and RC image upgrade notes.

## Implementation notes (2026-07-10)

generate_compose_env.sh + backup_mongo.sh
