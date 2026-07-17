# IMP-23 implementation notes

**Status:** Implemented 2026-07-16 (Wave 1 + S4/S7/S14 helpers)  
**Branch:** `feat/imp-23-wake-ux-s1-s2`  
**Package:** [README](./README.md) · [Suggested improvements](./suggested-improvements.md)

## What landed

| Item | Where |
| --- | --- |
| **S1** 429 non-final backoff | `wake_ux_imp23.RateLimitBackoff`; wired in `rc_operator_agent` thought/meta flush |
| **S1** final cool clamp | `final_cool_sleep_s` used in `finalize_thinking_message` |
| **S2** stronger Cancelled salvage | `is_salvageable_wake_text(..., stop_reason=)`; mid-length Cancelled OK; trailing structured section; multi-token secret redaction |
| **S2** skip empty-reply retry when stream salvageable / FINAL_OK | `should_skip_empty_reply_retry` + operator gate (`phase == FINAL_ERR` only) |
| **S4-lite** shared update gap | `cross_process_update_*` + **`default_shared_update_bucket()`** → `~/logs/rocketchat-shared/rc-update.bucket` (or `RC_UPDATE_BUCKET`). Live must use this path on **every** operator — per-bot `LOG_DIR/rc-update.bucket` is local-only and does **not** meet S4 acceptance. |
| **S4** correct update identity | thought/meta `chat.update` uses `OPERATOR`, not hardcoded grok (residual: some bubble post/finalize still `COLLAB_GROK` in live agent) |
| **S7** missing cwd FINAL_ERR | `validate_wake_cwd` before spawn; clears bad pin |
| **S8 note** drain log target | `target={OPERATOR}` in drain line (B8) |
| **S14** digest | `ops/rocketchat/scripts/rc_wake_digest.py` — counts **ISO-timestamped lines** with `ts >= now - hours` (not whole file tail) |

## Docs-repo mirror

| Path | Role |
| --- | --- |
| `ops/rocketchat/wake/wake_ux_imp23.py` | Pure helpers |
| `ops/rocketchat/tests/test_wake_ux_imp23.py` | 9 pure tests |
| `ops/rocketchat/scripts/rc_wake_digest.py` | Ops digest |

## Live runtime (principal Mac)

Copy/sync into `~/.grok/agency/ops/rocketchat/`:

```bash
cp ops/rocketchat/wake/wake_ux_imp23.py ~/.grok/agency/ops/rocketchat/wake/
# wake_telemetry.py + rc_operator_agent.py already patched on implement host
mkdir -p ~/.grok/agency/ops/rocketchat/scripts
cp ops/rocketchat/scripts/rc_wake_digest.py ~/.grok/agency/ops/rocketchat/scripts/
```

Restart operators (required for Python reload):

```bash
UID_NUM=$(id -u)
for label in operator hermes-operator agy-operator feynman-operator nie-operator; do
  launchctl kickstart -k "gui/${UID_NUM}/com.velocityworks.rocketchat-${label}"
done
```

## Verify

```bash
python3 ops/rocketchat/tests/test_wake_ux_imp23.py   # 9/9
python3 ops/rocketchat/tests/test_wake_telemetry_b4_b5.py
python3 ops/rocketchat/tests/test_wake_denials_imp22.py
python3 ops/rocketchat/scripts/rc_wake_digest.py
```

## Not in this PR (still residual)

S3 agy FINAL_ERR deep fix, S5 in-flight busy chrome, S6 double-seen, S8 B3/B10 launchd wire, S9 kickstart (ops), S10 phase-chrome, S11 short body quality, S12 health fields.

**Live wire residuals (agency `rc_operator_agent`, not fully mirrored):**
- Non-final update failures still call `note_429()` even when the failure is not HTTP 429 (over-backoff risk).
- Some bubble post/finalize/ack paths still hardcode `COLLAB_GROK` while thought flush uses `op_identity`.
- Dual S7 paths (early `validate_wake_cwd` vs older missing-cwd block) — keep until older block is removed.
- Shared bucket wire updated to `default_shared_update_bucket()` on the principal Mac; **restart operators** so processes reload the module + path.

## Env

| Env | Default | Meaning |
| --- | --- | --- |
| `RC_FINAL_COOL_S` | 3 | B4 cool before FINAL |
| `RC_429_BACKOFF_S` | 6 | Base non-final backoff after 429 |
| `RC_429_BACKOFF_MAX_S` | 32 | Cap backoff |
| `RC_WAKE_AUTO_RETRY` | on | Empty-reply retry (still gated by S2) |
| `RC_RETRY_COOLDOWN_S` | 60 | Per-room retry cool |
| `RC_UPDATE_BUCKET` | `~/logs/rocketchat-shared/rc-update.bucket` | Host-wide S4 chat.update gap file |
