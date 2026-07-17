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

**Run:** 2026-07-17 (Hermes, TP rev2)  
**Commands:**

```bash
python3 ops/rocketchat/tests/test_wake_inflight_ux_s5.py          # P 22/22
python3 ops/rocketchat/tests/test_wake_ux_imp23.py                 # R0a 16/16
python3 ops/rocketchat/tests/test_wake_denials_imp22.py            # R0b 6/6
python3 ops/rocketchat/tests/test_multi_round_collab.py            # R0c 17/17
python3 ops/rocketchat/scripts/rc_wake_digest.py --hours 6
# live: import wake_inflight_ux; health.json; post-kickstart log greps
```

| Date | Agent | Layer | Result | Notes |
| --- | --- | --- | --- | --- |
| 2026-07-17 | hermes | **P** | **PASS** | 22/22; no network imports in pure module |
| 2026-07-17 | hermes | **R0a** | **PASS** | 16/16 `test_wake_ux_imp23.py` |
| 2026-07-17 | hermes | **R0b** | **PASS** | 6/6 `test_wake_denials_imp22.py` |
| 2026-07-17 | hermes | **R0c** | **PASS** | 17/17 `test_multi_round_collab.py` |
| 2026-07-17 | hermes | **R1/R2** | SKIP | Optional agency usability not run |
| 2026-07-17 | hermes | **I2/I3/I6/I8/I9b/I11/I12/I13** | **PASS** | Live module policy smoke + agent wire static checks (no full RC mock harness) |
| 2026-07-17 | hermes | **I1/I4/I5/I7/I10** | SKIP | Need operator process harness / monkeypatch; waived for merge; pure covers policy |
| 2026-07-17 | hermes | **L1** | PARTIAL | Operators healthy `ws=true` all 5; recent FINAL_OK in 6h; post-S5 drain wake observed (Agency mid=`iynFogbw…`) — full 👀 chrome not screenshot-verified |
| 2026-07-17 | hermes | **L2** | **PASS** | Post-kickstart log: `enqueue busy_ack in-flight mid=iynFogbwPQkKLxZRf` (I2 primary + live) |
| 2026-07-17 | hermes | **L3** | NOT RUN | No controlled second distinct mid while in-flight after S5 deploy |
| 2026-07-17 | hermes | **L4** | RESIDUAL | `no_edit_stream` / not exercised; pure B/B2 still green |
| 2026-07-17 | hermes | **L5** | PARTIAL | `RC_WAKE_MAX_CONCURRENT` default **16** (not forced to 1); no post-S5 DM-vs-channel timing experiment |
| 2026-07-17 | hermes | **L6** | PARTIAL | Only 1 post-S5 busy_ack so far; pure P10 covers dedupe; historical pre-S5 `enqueue skip in-flight` still dominates older log tails |
| 2026-07-17 | hermes | **L7** | PARTIAL | Digest 6h has residual 429s (pre-existing S1 class); S5 adapter path has no `update_message` (I6) |
| 2026-07-17 | hermes | **L8** | NOT RUN | Peer-specific busy path not re-probed post-S5 (peers idle after kickstart) |

**Merge gate:** PASS (P + R0\*).  
**Live wire safe:** PASS (module import, 5 operators `ws_connected=true`, busy_ack live).  
**S5 Done gate:** NOT YET — hard L3 (+ ideally L1 full chrome, L5 timing) still open.

### Digest snapshot (6h, at test run)

| bot | FINAL_OK | FINAL_ERR | 429 | empty-reply | Cancelled |
| --- | ---: | ---: | ---: | ---: | ---: |
| grok | 8 | 0 | 12 | 0 | 0 |
| hermes | 6 | 0 | 8 | 0 | 0 |
| agy | 4 | 0 | 15 | 0 | 0 |
| nie | 4 | 0 | 12 | 0 | 0 |
| feynman | 4 | 0 | 19 | 0 | 0 |

### S5 residuals (after test run)

- Principal manual **L3** (new mid while busy → immediate 👀 + FIFO) still required for S5 Done
- **L4** edit stream residual if RC never redelivers edits
- **L5** cross-room timing experiment not run (config default 16 confirmed)
- Full monkeypatch I-harness optional
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
