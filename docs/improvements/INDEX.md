# Improvements index

**Last updated:** 2026-07-10  
**Parent project:** [rocketchat-grok-docs README](../../README.md)  
**Scope:** Suggested configuration and ops improvements for the live Rocket.Chat ↔ Grok stack (`~/.grok/agency/ops/rocketchat/` and related paths).

This folder is the **backlog package**: each item has a requirements document and a test plan. Items are ordered **most impactful first** (same ranking as the configuration deep dive). Status here is documentation only until work is implemented.

---

## How to navigate

| Want… | Go to |
| --- | --- |
| Full ranked list | Table below |
| One improvement’s goals / acceptance | `NN-*/requirements.md` |
| How to verify that improvement | `NN-*/test-plan.md` |
| System context | [Architecture](../architecture.md), [Filesystem map](../filesystem-map.md), [Operations](../operations.md) |
| Runtime runbook | `~/.grok/agency/ops/ROCKETCHAT.md` |

Each improvement folder links: **Index → Requirements ↔ Test plan**.

---

## Suggested implementation phases

| Phase | Items | Intent |
| --- | --- | --- |
| **A — safety** | [01](01-cap-blast-radius/), [02](02-wake-lock-ttl/), [07](07-secrets-prompt-hygiene/) | Stop damage and race classes |
| **B — ops truth** | [04](04-docker-healthcheck/), [05](05-cache-rest-auth/), [08](08-log-retention/), [17](17-sync-stale-docs/) | Trust status; quieter disk |
| **C — structure** | [03](03-single-config-surface/), [11](11-launchd-templates/), [13](13-venv-dependencies/), [09](09-align-turn-limits/) | Movable, consistent config |
| **D — polish** | [06](06-network-exposure/), [10](10-per-room-wake-queue/), [12](12-operator-health-watchdog/), [14](14-per-room-state-model/)–[16](16-extract-code-project/), [18](18-quarantine-poll-path/)–[20](20-pgs-bot-token/) | Scale, hygiene, optional |

---

## Ranked backlog

| # | Title | Impact | Phase | Requirements | Test plan | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | [Cap blast radius of phone-driven Grok](01-cap-blast-radius/) | Critical | A | [req](01-cap-blast-radius/requirements.md) | [test](01-cap-blast-radius/test-plan.md) | **Done** |
| 02 | [Fix wake-lock TTL vs wake timeout](02-wake-lock-ttl/) | Critical | A | [req](02-wake-lock-ttl/requirements.md) | [test](02-wake-lock-ttl/test-plan.md) | **Done** |
| 03 | [Single configuration surface + startup validation](03-single-config-surface/) | High | C | [req](03-single-config-surface/requirements.md) | [test](03-single-config-surface/test-plan.md) | **Done** |
| 04 | [Fix Docker healthcheck](04-docker-healthcheck/) | High | B | [req](04-docker-healthcheck/requirements.md) | [test](04-docker-healthcheck/test-plan.md) | **Done** |
| 05 | [Cache REST auth tokens](05-cache-rest-auth/) | High | B | [req](05-cache-rest-auth/requirements.md) | [test](05-cache-rest-auth/test-plan.md) | **Done** |
| 06 | [Network exposure (bind / 2FA / LAN)](06-network-exposure/) | High | D | [req](06-network-exposure/requirements.md) | [test](06-network-exposure/test-plan.md) | **Done** |
| 07 | [Secrets out of model prompt](07-secrets-prompt-hygiene/) | High | A | [req](07-secrets-prompt-hygiene/requirements.md) | [test](07-secrets-prompt-hygiene/test-plan.md) | **Done** |
| 08 | [Log and artifact retention](08-log-retention/) | Medium–high | B | [req](08-log-retention/requirements.md) | [test](08-log-retention/test-plan.md) | **Done** |
| 09 | [Align Grok turn-limit defaults](09-align-turn-limits/) | Medium | C | [req](09-align-turn-limits/requirements.md) | [test](09-align-turn-limits/test-plan.md) | **Done** |
| 10 | [Per-room / concurrent wake queue](10-per-room-wake-queue/) | Medium | D | [req](10-per-room-wake-queue/requirements.md) | [test](10-per-room-wake-queue/test-plan.md) | **Done** |
| 11 | [Generate launchd from templates](11-launchd-templates/) | Medium | C | [req](11-launchd-templates/requirements.md) | [test](11-launchd-templates/test-plan.md) | **Done** |
| 12 | [Operator health endpoint / watchdog](12-operator-health-watchdog/) | Medium | D | [req](12-operator-health-watchdog/requirements.md) | [test](12-operator-health-watchdog/test-plan.md) | **Done** |
| 13 | [Pinned venv dependencies (no runtime pip)](13-venv-dependencies/) | Medium | C | [req](13-venv-dependencies/requirements.md) | [test](13-venv-dependencies/test-plan.md) | **Done** |
| 14 | [Per-room state model cleanup](14-per-room-state-model/) | Medium | D | [req](14-per-room-state-model/requirements.md) | [test](14-per-room-state-model/test-plan.md) | **Done** |
| 15 | [Compose/secrets DRY + Mongo backup policy](15-compose-secrets-dry/) | Medium | D | [req](15-compose-secrets-dry/requirements.md) | [test](15-compose-secrets-dry/test-plan.md) | **Done** |
| 16 | [Extract integration code to a project](16-extract-code-project/) | Medium (long-term) | D | [req](16-extract-code-project/requirements.md) | [test](16-extract-code-project/test-plan.md) | **Won't do** |
| 17 | [Sync stale docs and dual runbooks](17-sync-stale-docs/) | Low–medium | B | [req](17-sync-stale-docs/requirements.md) | [test](17-sync-stale-docs/test-plan.md) | **Done** |
| 18 | [Quarantine or remove poll path](18-quarantine-poll-path/) | Low (high if re-enabled) | D | [req](18-quarantine-poll-path/requirements.md) | [test](18-quarantine-poll-path/test-plan.md) | **Done** |
| 19 | [Channel auto-create policy](19-channel-autocreate-policy/) | Low–medium | D | [req](19-channel-autocreate-policy/requirements.md) | [test](19-channel-autocreate-policy/test-plan.md) | **Done** |
| 20 | [PGS / bot auth via shared token surface](20-pgs-bot-token/) | Low | D | [req](20-pgs-bot-token/requirements.md) | [test](20-pgs-bot-token/test-plan.md) | **Done** |

---

## Folder layout

```
docs/improvements/
├── INDEX.md                 ← you are here
├── 01-cap-blast-radius/
│   ├── README.md            ← short entry + links
│   ├── requirements.md
│   └── test-plan.md
├── 02-wake-lock-ttl/
│   └── …
└── …
```

---

## Status values

| Status | Meaning |
| --- | --- |
| **Proposed** | Documented; not implemented |
| **In progress** | Implementation started |
| **Done** | Requirements met; test plan executed and recorded |
| **Won’t do** | Explicitly declined (note reason in that item’s requirements) |

Update the table when status changes.

---

## Related docs

- [Architecture](../architecture.md) — current design  
- [Message flow](../message-flow.md) — wake lifecycle  
- [Operations](../operations.md) — live checks  
- [Filesystem map](../filesystem-map.md) — paths  
- [Related systems](../related-systems.md) — PGS, ngrok, Twilio  
