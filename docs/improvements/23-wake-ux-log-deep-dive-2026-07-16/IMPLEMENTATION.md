# IMP-23 implementation notes

**Status:** Wave 1 (2026-07-16) + **S5 in-flight busy chrome** (2026-07-17)  
**Branches:** `feat/imp-23-wake-ux-s1-s2` (merged) · `feat/imp-23-s5-inflight-busy-chrome`  
**Package:** [README](./README.md) · [Suggested improvements](./suggested-improvements.md) · [S5 test plan](./test-plan-s5.md)

## What landed

| Item | Where |
| --- | --- |
| **S1** 429 non-final backoff | `wake_ux_imp23.RateLimitBackoff`; wired in `rc_operator_agent` thought/meta flush |
| **S1** final cool clamp | `final_cool_sleep_s` used in `finalize_thinking_message` |
| **S2** stronger Cancelled salvage | `is_salvageable_wake_text(..., stop_reason=)`; mid-length Cancelled OK; trailing structured section; multi-token secret redaction |
| **S2** skip empty-reply retry when stream salvageable / FINAL_OK | `should_skip_empty_reply_retry` + operator gate (`phase == FINAL_ERR` only) |
| **S4-lite** shared update gap | `cross_process_update_*` + **`default_shared_update_bucket()`** → `~/logs/rocketchat-shared/rc-update.bucket` (or `RC_UPDATE_BUCKET`). Live must use this path on **every** operator — per-bot `LOG_DIR/rc-update.bucket` is local-only and does **not** meet S4 acceptance. |
| **S4** correct update identity | thought/meta `chat.update` uses `OPERATOR`, not hardcoded grok (residual: some bubble post/finalize still `COLLAB_GROK` in live agent) |
| **S5** in-flight busy + follow-up | `wake_inflight_ux.decide_enqueue` / `apply_decision_to_pending`; live `_enqueue_pending` adapter; immediate 👀; busy react; edit follow-up `#fu1`; pending text update; log dedupe; `in_flight_texts` |
| **S7** missing cwd FINAL_ERR | `validate_wake_cwd` before spawn; clears bad pin |
| **S8 note** drain log target | `target={OPERATOR}` in drain line (B8) |
| **S14** digest | `ops/rocketchat/scripts/rc_wake_digest.py` — counts **ISO-timestamped lines** with `ts >= now - hours` (not whole file tail) |

## S5 details (2026-07-17)

### Pure module

| Path | Role |
| --- | --- |
| `ops/rocketchat/wake/wake_inflight_ux.py` | Decision matrix + apply + log dedupe |
| `ops/rocketchat/tests/test_wake_inflight_ux_s5.py` | **22/22** pure tests (TP rev2 P*) |

### Live wire (agency `rc_operator_agent.py`, not fully mirrored)

- `_enqueue_pending` → pure policy when import ok; legacy silent-skip fallback otherwise
- Immediate `schedule_principal_ack` on new enqueue; busy `schedule_react` (`RC_WAKE_REACT_BUSY`, default `repeat`)
- `acked_on_enqueue` suppresses double 👀 at process start
- Process path uses `source_mid` for follow-ups; `_set_in_flight(..., text=)` fills `in_flight_texts`
- Agy collab process path respects `source_mid` / `acked_on_enqueue`

### Deploy

```bash
cp ops/rocketchat/wake/wake_inflight_ux.py ~/.grok/agency/ops/rocketchat/wake/
# ensure live rc_operator_agent.py has S5 wire
UID_NUM=$(id -u)
for label in operator hermes-operator agy-operator feynman-operator nie-operator; do
  launchctl kickstart -k "gui/${UID_NUM}/com.velocityworks.rocketchat-${label}"
done
python3 -c "import sys; sys.path.insert(0,'$HOME/.grok/agency/ops/rocketchat/wake'); import wake_inflight_ux as m; print(m.__file__)"
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py  # 22/22
```

### Env (S5)

| Env | Default | Meaning |
| --- | --- | --- |
| `RC_WAKE_REACT_BUSY` | `repeat` | Busy / follow-up-noted reaction shortname |
| `RC_INFLIGHT_LOG_TTL_S` | `60` | Decision log dedupe window |

### S5 test execution record

| Date | Agent | Layer | Result | Notes |
| --- | --- | --- | --- | --- |
| 2026-07-17 | hermes | P | PASS | 22/22 |
| 2026-07-17 | hermes | R0a–c | PASS | 16/16, 6/6, 17/17 |
| 2026-07-17 | hermes | I | partial | live import + ast parse; full mock harness not run |
| 2026-07-17 | hermes | L | partial | kickstart all 5 ops; live log shows `enqueue busy_ack in-flight mid=…` on grok (A path live) |

### S5 residuals

- Live L1–L8 principal acceptance not yet recorded
- RC may not redeliver message edits (L4 soft residual `no_edit_stream`)
- Some process bubble post paths still hardcode `COLLAB_GROK` identity (pre-existing)

---

## Docs-repo mirror (Wave 1 + S5)

| Path | Role |
| --- | --- |
| `ops/rocketchat/wake/wake_ux_imp23.py` | Wave 1 pure helpers |
| `ops/rocketchat/wake/wake_inflight_ux.py` | S5 pure helpers |
| `ops/rocketchat/tests/test_wake_ux_imp23.py` | Wave 1 tests |
| `ops/rocketchat/tests/test_wake_inflight_ux_s5.py` | S5 tests |
| `ops/rocketchat/scripts/rc_wake_digest.py` | Ops digest |

## Live runtime (principal Mac)

Copy/sync into `~/.grok/agency/ops/rocketchat/`:

```bash
cp ops/rocketchat/wake/wake_ux_imp23.py ops/rocketchat/wake/wake_inflight_ux.py \
  ~/.grok/agency/ops/rocketchat/wake/
# wake_telemetry.py + rc_operator_agent.py patched on implement host
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
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py  # 22/22
python3 ops/rocketchat/tests/test_wake_ux_imp23.py
python3 ops/rocketchat/tests/test_wake_denials_imp22.py
python3 ops/rocketchat/tests/test_multi_round_collab.py
python3 ops/rocketchat/scripts/rc_wake_digest.py
```

## Not closed (still residual)

S3 agy FINAL_ERR deep fix, S6 double-seen, S8 B3/B10 launchd wire residual, S10 phase-chrome, S11 short body quality, S12 health fields. **S5 code landed; live L* acceptance still open.**

**Live wire residuals (agency `rc_operator_agent`, not fully mirrored):**
- Non-final update failures still call `note_429()` even when the failure is not HTTP 429 (over-backoff risk).
- Some bubble post/finalize paths still hardcode `COLLAB_GROK` while thought flush uses `op_identity`.
- Dual S7 paths (early `validate_wake_cwd` vs older missing-cwd block) — keep until older block is removed.
- Shared bucket wire updated to `default_shared_update_bucket()` on the principal Mac; **restart operators** so processes reload the module + path.

## Env (Wave 1 + S5)

| Env | Default | Meaning |
| --- | --- | --- |
| `RC_FINAL_COOL_S` | 3 | B4 cool before FINAL |
| `RC_429_BACKOFF_S` | 6 | Base non-final backoff after 429 |
| `RC_429_BACKOFF_MAX_S` | 32 | Cap backoff |
| `RC_WAKE_AUTO_RETRY` | on | Empty-reply retry (still gated by S2) |
| `RC_RETRY_COOLDOWN_S` | 60 | Per-room retry cool |
| `RC_UPDATE_BUCKET` | `~/logs/rocketchat-shared/rc-update.bucket` | Host-wide S4 chat.update gap file |
| `RC_WAKE_REACT_BUSY` | `repeat` | S5 busy reaction |
| `RC_INFLIGHT_LOG_TTL_S` | `60` | S5 decision log dedupe |
