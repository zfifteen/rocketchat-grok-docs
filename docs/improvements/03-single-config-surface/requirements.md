# Requirements: Single configuration surface + startup validation

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Test plan](./test-plan.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-03 |
| **Priority** | High |
| **Phase** | C — structure |
| **Status** | Done (2026-07-10) |
| **Touches** | `secrets/rocketchat.env`, `ops/rocketchat/.env`, operator/call/poll, launchd, PGS notify consumer |
| **Related** | [IMP-11](../11-launchd-templates/), [IMP-15](../15-compose-secrets-dry/), [IMP-16](../16-extract-code-project/) |

---

## Problem

Configuration is split across:

- `~/.grok/agency/secrets/rocketchat.env`
- `ops/rocketchat/.env` (compose)
- Hardcoded `Path.home() / ".grok" / "agency"` in Python
- launchd absolute paths
- Sparse `RC_*` / `GROK_BIN` env overrides

Public URLs are currently consistent but only by manual discipline.

---

## Goals

1. One schema of record for RC+Grok integration settings.
2. Every path used by operator/call/media overridable without code edits.
3. Startup validation fails fast with clear errors.
4. Secrets remain mode 600 and out of git.

---

## Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Define a config schema (env file, TOML, or layered: defaults < file < env). Document all keys in this docs project and/or `config.example`. |
| R2 | Required keys include at least: RC base URL, public URL, operator credentials ref, secrets path, agency path, IdeaProjects path, log dir, Grok bin, wake timeout, approval mode (IMP-01). |
| R3 | Operator, call bot, `rc_post_media`, and (if practical) PGS notify read the **same** loader library. |
| R4 | On operator start: validate secrets file exists; login works; `GET /api/info` succeeds; optional check public URL matches workspace if configured. |
| R5 | Validation failure exits non-zero and logs a single actionable message (no password dump). |
| R6 | Provide `config.example` / `.env.example` with placeholders only. |

---

## Acceptance criteria

- [x] No production Python module hardcodes only `~/.grok/agency` without env override.
- [x] Startup with missing secrets fails clearly.
- [x] Startup with RC down fails clearly.
- [x] Example config checked into docs or code repo (no secrets).

---

## Non-goals

- Cloud secret managers.
- Encrypting secrets at rest beyond OS file modes.

## Implementation notes (2026-07-10)

wake/rc_config.py load_rc_config + validate_config_startup; env path overrides.

**Skeptic fix:** operator `apply_runtime_config` in `main()` (fail-fast); media/call load_rc_config; `config.example` + `.env.example` shipped..

**Skeptic fix:** `rc_operator_agent.apply_runtime_config` called from `main()` (fail-fast);
`rc_post_media.apply_media_config` + call `apply_call_config`; `config.example` and
`.env.example` shipped under ops/rocketchat/.