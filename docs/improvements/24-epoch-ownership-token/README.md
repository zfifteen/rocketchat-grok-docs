# 24 — Epoch ownership token (sharper multi-round lead)

**Nav:** [Improvements index](../INDEX.md) · [Z-map](./z-map.md) · [Project home](../../../README.md)  
**Status:** proposed (nie peer delivery, collab epoch hermes-lead 2026-07-18)  
**Parent ask:** one high-leverage multi-round protocol improvement with falsifiable check  
**Related:** hermes lead hypothesis (configurable session lead); issue #2 multi-round hardening; `ops/rocketchat/wake/rc_multi_round_collab.py`

## One sentence

Do not only add `RC_COLLAB_LEAD=env`. Bind DONE authority, epoch open, principal multi-@ lead identity, post-DONE lead short-circuit, and return-notify fallback to a **per-room epoch ownership token** claimed at open.

## Why not plain "configurable lead"

Hermes is right that `GROK_LEAD = "grok"` blocks hermes-led trials. An env swap is classical process config. It still leaves **one global identity** for all rooms and ignores state the code already almost has:

- `open_collab_epoch(..., opened_by=op)` stores `opened_by` but no gate reads it as lead.
- Operator after-wake only marks DONE / opens epoch when `op == MR_GROK_LEAD` (`rc_operator_agent.py` multi-round block).
- `resolve_return_notify_target` already takes `lead=` but callers pass the constant.
- `principal_multi_mention_lead_only` already takes `lead=` but defaults to grok.

Three mechanical privileges are **fused to a compile-time username**, not to the open collab epoch:

| Privilege | Today | Should key on |
| --- | --- | --- |
| Who may open/reuse epoch on peer `@` assigns | only grok | epoch owner (or claim on first assign) |
| Who may set `lead_done` from DONE language | only grok | epoch owner |
| Fallback return-notify + principal multi-@ "lead" + post-DONE LLM skip | grok constant | epoch owner (pre-epoch: claim rule / default) |

## Proposed protocol object

**`rooms[room_id].lead`** (ownership token), set once per active epoch:

1. **Principal sole-tags** one operator as session lead (and that operator later assigns peers) → that operator is lead when epoch opens.
2. **First valid open:** any operator in `ALL_OPERATORS` who posts open peer assigns while no active epoch may claim lead (`opened_by` becomes `lead`), unless principal already fixed lead via sole-tag seed state.
3. **Default residual:** if no claim yet, `lead = GROK_LEAD` (or future `RC_MULTI_ROUND_DEFAULT_LEAD`) for pre-epoch principal multi-@ suppress and fallback notify.

On `lead_done` clear / fresh epoch (`force` or after DONE), clear or re-claim `lead` with the new open.

Playbook: "Lead = grok" becomes "Lead = epoch owner (default grok)". Inject can print `EPOCH_LEAD: hermes` when set.

## Falsifiable check (same bar as hermes, stricter object)

After a principal seed that only tags `@hermes` with "lead this collab…", then hermes assigns `@nie` (or any peer):

1. Peer completion return-notify targets **hermes** (assigner path, and fallback if assigner missing is still hermes while epoch open).
2. Hermes DONE language sets durable `lead_done` (today only grok process can).
3. Principal multi-@ `hermes`+peer (no grok) does **not** race all peers under lead-only mode.
4. Hermes can `open_collab_epoch` on peer assigns (today epoch open is grok-only).

**Kill:** if after wiring `rooms[].lead` any of (1)–(4) still requires chat-only theater, the token is incomplete. If a pure env `DEFAULT_LEAD` already passes (1)–(4) without per-epoch field for multi-room different leads, then env is enough and this item collapses to residual "global default only".

## Residual if we do not implement yet

Hermes-led epochs remain prose-only. Mechanical gates stay grok-shaped (`GROK_LEAD` constant). Return-notify assigner path already works when hermes is the **assigner** of a hop; it fails for fallback, DONE mark, epoch open, principal multi-@ lead identity, and post-DONE lead short-circuit. That residual is **honest**: partial continuity without ownership.

## Implementation sketch (not done this hop)

1. `get_room_lead(room_id) -> str` reading `rooms[rid].lead` else default.
2. Replace `op == MR_GROK_LEAD` DONE/epoch-open/skip-LLM checks with `op == get_room_lead(rid)`.
3. Pass `lead=get_room_lead(rid)` into `resolve_return_notify_target` and `principal_multi_mention_lead_only`.
4. On epoch open: set `entry["lead"] = normalize(opened_by or prior claim or default)`.
5. Unit tests: hermes-lead seed matrix for the four checks above.
6. Playbook v3.3: Lead = epoch owner; default grok.

## Explicit non-goals this item

- Full NF-SPEC-10 untagged intake in every room.
- Intentional-mention classes (social `@` vs handoff) as the primary fix (partially exists via open-assign regex).
- Close-out phase enum (`open|closing|closed`) alone without ownership (anti-loop already partially shipped as `lead_done` bool).
