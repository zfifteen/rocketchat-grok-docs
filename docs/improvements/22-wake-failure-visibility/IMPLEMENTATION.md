# IMP-22 implementation notes

**Status:** Implemented 2026-07-16 (hermes)  
**Issue:** https://github.com/zfifteen/rocketchat-grok-docs/issues/4

## Docs-repo (this PR)

| Path | Role |
| --- | --- |
| `ops/rocketchat/wake/wake_denials.py` | Pure extract/redact/footer helpers |
| `ops/rocketchat/tests/test_wake_denials_imp22.py` | 6 pure tests |
| `docs/improvements/22-wake-failure-visibility/*` | Spec package |

## Live runtime (already applied on this Mac)

Copy/sync these into `~/.grok/agency/ops/rocketchat/wake/` on each host:

1. `wake_denials.py` (from this repo)
2. Patch `wake_telemetry.py`:
   - `format_final_err(..., denials=, mid_short=)`
   - `choose_final_body` extracts denials; FINAL_ERR includes `tools_blocked:`; FINAL_OK may append `Tools blocked:` footer (`RC_WAKE_DENIAL_FOOTER`, default on)
3. `rc_operator_agent.py`: pass `mid_short=mid[:8]` into `choose_final_body`
4. `hermes_reply_prompt.txt`: require naming denied tools in restricted mode

Restart operators after sync (launchd reload) so Python reloads modules.

## Env

| Env | Default | Meaning |
| --- | --- | --- |
| `RC_WAKE_DENIAL_FOOTER` | on | Append tools-blocked footer on FINAL_OK when denials parsed |

## Verify

```bash
python3 ops/rocketchat/tests/test_wake_denials_imp22.py
# expect 6/6 passed
```
