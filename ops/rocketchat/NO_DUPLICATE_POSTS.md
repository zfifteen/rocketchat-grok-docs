# NO DUPLICATE POSTS — standing RC rule

**Status:** HARD RULE (principal escalated 2026-07-10; also PGS 2026-07-10).  
**Do not treat as optional or “nice to have.”**

## What burned the principal

1. **Image path:** Calling `rooms.mediaConfirm` **twice** on the same `fileId` creates **two** image bubbles on RC 8.6 (not an idempotent no-op). Happened during Imagine upload probe (messages `WWRZpGsfrf…` + empty twin `PhgsT5Y8NC…`, latter deleted).
2. **PGS hourly path:** `activation_key` included `completed_at`, so rewriting `last_run.json` mid-hour looked like a new activation → second memo for the same hour.
3. **Process failure:** Saying “fixed” without a durable guard + continuity note, then repeating the class of bug on another surface.

## Mandatory behavior

| Surface | Rule |
| --- | --- |
| Chat answers | Operator owns **one** bubble: `Thinking...` → `chat.update` from reply file only. Never `chat.postMessage` for the answer. |
| Images / files | **Only** `ops/rocketchat/wake/rc_post_media.py` (idempotent ledger). Never hand-loop `rooms.mediaConfirm`. |
| Hourly PGS memos | `pgs_hourly_rocketchat_notify.py`: key = `job_id\|activated_at` only; claim-before-post + file lock. |

## Enforcement locations (must remain)

- `ops/rocketchat/wake/reply_prompt.txt` — **NO DUPLICATE POSTS** block (every wake).
- `ops/rocketchat/wake/rc_operator_agent.py` — inject line on every prompt.
- `ops/rocketchat/wake/rc_post_media.py` — single confirm + `~/logs/rocketchat-dm-wake/media-post-ledger.json`.
- `ops/rocketchat/tests/USABILITY_CONTRACTS.md` — contract §8.
- PGS: `scripts/pgs_hourly_rocketchat_notify.py` activation key + lock.
- Agency spine: `INVALIDATED.md` (do-not-revive) + this file.

## Do not revive

- “Just retry the confirm / post if unsure.”
- Probe loops that call confirm/post more than once.
- Manual `chat.postMessage` of the same answer after Thinking… already finalized.
- Re-running hourly notify with a reworded body for the **same** activation without `--force-same-activation` (emergency only).

## Verify

```bash
grep -n "NO DUPLICATE" ~/.grok/agency/ops/rocketchat/wake/reply_prompt.txt
test -f ~/.grok/agency/ops/rocketchat/wake/rc_post_media.py
python3 -c "
import importlib.util
from pathlib import Path
p=Path.home()/'IdeaProjects/prime-gap-structure/scripts/pgs_hourly_rocketchat_notify.py'
s=importlib.util.spec_from_file_location('n',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
a=m.activation_key({'job_id':'j','activated_at':'t','completed_at':None})
b=m.activation_key({'job_id':'j','activated_at':'t','completed_at':'x'})
assert a==b
print('ok')
"
```

*Last updated: 2026-07-10*
