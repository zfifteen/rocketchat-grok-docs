# Rocket.Chat operator — usability contracts

These are **user-visible** invariants. If any fail in the wild, testing was insufficient.

## Contracts

1. **Principal LLM wake policy (mode-aware).**  
   - **`RC_REQUIRE_MENTION=0` (legacy):** a handleable principal message always gets a wake attempt (or stays queued).  
   - **`RC_REQUIRE_MENTION=1` + scope `channels` (dual-operator default):** channel/group (`c`/`p`) messages wake only when they **@mention this operator** (`grok` or `hermes`); **DMs free-wake** without a tag. Untagged channel messages must not enqueue and must not be marked processed as answered.  
   - **Control plane** (`!` / `/` from principal) stays mention-exempt. Videoconf Call stays principal-only system path.  
   Never mark `processed_ids` before the wake runs when a wake *is* enqueued.  
   *Caught failure: channel messages silently ignored while lock held; dual free-wake with Hermes.*

2. **Stuck `wake.lock.d` must not drop work.**  
   Stale reclaim (≤3 min) + force-clear on drain.  
   *Caught failure: lock from 16:25 blocked all wakes.*

3. **Queue race:** items enqueued while a drain is finishing must still run.  
   Drain re-checks `pending_wakes` after unlock.

4. **No canned chat replies** (no “Got it…”, “fast path”, “On it…”).

5. **Same room → same Grok session** (`--resume` + `grok_sessions`).

6. **Only DMs use `~/.grok/agency`.** Channels map to `~/IdeaProjects/<slug>` (create if missing).

7. **Principal 👀 + single activity bubble finalization**  
   - On wake start: react **👀** on the **principal** message (kept after done).  
   - Post one agent activity bubble (initial `…`; live **thought** stream when `RC_WAKE_STREAM` on).  
   - On wake end: `chat.update` **that same** `msgId` with  
     RC-safe `*Thoughts*` + thought stream + unicode rule line + final answer  
     (`compose_final_with_thoughts`). Markdown `---` is **not** used (RC does not
     render horizontal rules). If no thoughts were streamed, final answer only.  
   - **No second** `chat.postMessage` for the answer.  
   - Grok writes body to a reply file; operator owns RC publish.  
   *Verified live on RC 8.6: `chat.update` works for grok editing own messages.*

8. **No duplicate posts**  
   - Never `rooms.mediaConfirm` the same `fileId` twice (RC creates two bubbles).  
   - Image posts go through `wake/rc_post_media.py` (idempotent ledger).  
   - PGS hourly notify: activation_key = `job_id|activated_at` only; claim-before-post + file lock.  

8. **Tests must not poison production.**  
   - Usability tests isolate `STATE_PATH` / `LOCK_DIR`.  
   - Live post smoke is opt-in (`RC_LIVE_SMOKE=1`) and must not post by default.  
   - Live Thinking/update probe: `RC_LIVE_THINKING=1`.

## Feature implementation pattern (mandatory for future work)

1. **Write the usability contract + automated test first** (isolated mocks).  
2. **Implement** the feature so that test passes.  
3. **Register** the test in `test_usability_contracts.py` / suite entrypoint.  
4. Optional live probe only behind env flag.

## Run

```bash
# Fast, isolated contracts (preferred CI)
python3 ~/.grok/agency/ops/rocketchat/tests/test_usability_contracts.py

# Broader suite (includes contracts; live post disabled by default)
python3 ~/.grok/agency/ops/rocketchat/tests/test_rc_integration.py
```
