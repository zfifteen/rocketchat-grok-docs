# Evidence notes — IMP-23 log deep dive

**Captured:** 2026-07-16 / 2026-07-17 (local Mac)  
**Primary paths:**
- `~/logs/rocketchat-dm-wake/operator-agent.log` (grok)
- `~/logs/rocketchat-hermes-wake/operator-agent.log`
- `~/logs/rocketchat-agy-wake/operator-agent.log`
- `~/logs/rocketchat-nie-wake/operator-agent.log`
- `~/logs/rocketchat-feynman-wake/operator-agent.log`
- `~/logs/rocketchat-dm-wake/wake-run-*.log`

## Operator event mix (grok)

Top event tokens from `operator-agent.log` (~9k lines): stream, refresh_watch_rooms, wake, health, room, subscribed, waking, drain, update_message, finalize, enqueue, skip, multi-round, websocket, reconnect.

Finalize phases (parsed): FINAL_OK 299 · FINAL_ERR 4 (full-history phase= tokens; broader FINAL_ERR string count 15 including other lines).

stopReason on finalize path: EndTurn 308 · Cancelled 42.

## 429

- Grok update_message HTTP 429: **388+** structured failures; broader 429 token count **491**.
- Hot minutes: 2026-07-14 22:56 (24), 22:49 (13), 2026-07-15 02:13 (13), … **86** distinct minutes with 429.
- Stream thought: ok=True 948 · ok=False 88.
- Lost finals (body ready, update failed):
  - `2026-07-13T22:33:35Z` FINAL_OK ok=False body_len=881 room=Prime-Gap-Structure (429 immediately prior)
  - `2026-07-13T22:35:26Z` FINAL_OK ok=False body_len=1303 room=dm:principal

## Empty-reply / Cancelled

- `empty-reply recovery scheduled`: **11** (grok). Outcomes: ok_after≈7, err_after≈4.
- Last 120 wake-runs: stopReason EndTurn 95 · Cancelled 22; true BLOCKED-style lines rare (~3).
- Sample Cancelled run `wake-run-1784249030.log`: types thought=100, text=32, end=1 — stream had text but recovery still scheduled (reply file empty).
- Thought text in `wake-run-1784236001.log` explicitly discusses “User cancelled the execution” / Cancelled stopReason.

## Queue / mention

- enqueue skip in-flight: grok 308, hermes 177, agy 187.
- skip no_operator_mention: often **duplicate pairs** same mid ≤1s (all bots).
- health.json (grok): ws_connected true, last_event_at **null**, last_wake_at set, approval_mode restricted.

## Collab quality gate

Examples of suppressed return-notify:
- FINAL_ERR quality_gate (PGS, dm:principal, grok-build)
- FINAL_OK rc=-6 quality_gate (PGS)
- hermes FINAL_OK rc=1 quality_gate
- agy FINAL_ERR quality_gate (Agency, multiple on 2026-07-16 evening)

## Agy

- finalize_ok 91 · finalize_err **33**
- Recent Agency FINAL_ERR body_len=173 stopReason=- thought_updates=0

## Identity anomaly

Hermes/nie/feynman logs contain lines:
`update_message identity=grok failed … 429`
while also logging identity=hermes|nie|feynman failures. Needs auth-path audit (S4).

## Missing cwd

- `process item failed …/IdeaProjects/math-research` (2026-07-14)
- stderr: FileNotFoundError same path; operator config invalid when RC port closed (restart loop noise)

## Wake lock

Early corpus (2026-07-09): `wake lock held — skip wake (no canned ack posted)` during tests — mostly historical; in-flight skip is the modern analogue.

## Note on false positives

Naive grep for “permission” / “denial” on wake-run logs hits every cmd line (`--permission-mode auto`). Counts for true tool denials must use BLOCKED / User denied / structured extract (IMP-22).
