# Goal: Install/config refactor (local first) → public share

**Status:** Documented intent only — **not started**  
**Captured:** 2026-07-12  
**Owner:** Operator + principal (when resumed)  
**Related runtime:** `~/.grok/agency/ops/rocketchat/`  
**Related docs:** this repo (`rocketchat-agents`)

---

## Why this exists

The Rocket.Chat ↔ Grok Build integration is working and valued on the principal Mac (DM operator, control plane, attachments, Call experiments, etc.). Public web search (2026-07-12) found **no peer “Grok Build as always-on Rocket.Chat operator”** product; closest are thin Grok *API* automations and generic RC AI bots.

The principal wants to **share the integration with the general public** eventually. Doing that from the current home-lab layout is the wrong first move: dependencies and configuration are spread across agency secrets, launchd, Docker, logs, and hardcoded host assumptions. Sharing a dump of `~/.grok/agency` would leak personal structure and fail for other people.

**Agreed sequence:**

1. **Refactor/optimize install + configuration on this laptop first** and prove the stack still works.  
2. **Then** design packaging / public repo boundaries.  
3. Do **not** implement packaging until local install is clean and green.

This document is the durable handoff so the work can resume another day without re-deriving the strategy.

---

## Problem statement

| Pain | Today (illustrative) |
| --- | --- |
| Config sprawl | ~100 `RC_*` / `ROCKETCHAT_*` keys; secrets under `~/.grok/agency/secrets/`; compose `.env`; launchd env; `state.json`; channel maps |
| Path coupling | Defaults to `~/.grok/agency`, `IdeaProjects`, `com.velocityworks.*`, fixed log dirs |
| Scope fusion | Core DM operator fused with Call/LiveKit, collab, ngrok, agency policy, research channels |
| Prior extract decision | [IMP-16](../improvements/16-extract-code-project/) marked **Won't do** (2026-07-10) for full cutover of live KeepAlive into IdeaProjects — **revisit under this program**, not as a drive-by move |
| Partial config work | [IMP-03](../improvements/03-single-config-surface/) (`load_rc_config`) helped but did **not** produce a human-simple install or public product surface |

---

## North star (eventual public product)

**Name working title:** *Grok on Rocket.Chat* (operator bridge) — not “Velocity Works agency.”

### Tier A — ship target for any public v1 (minimal viable share)

- Bot user online (DDP)  
- Principal DM (and optional channel mention policy)  
- Headless Grok Build wake + session resume  
- Single-bubble Thinking → `chat.update`  
- Control plane with **`!` prefix** (RC steals `/`; document that hard)  
- Restricted approval default; secrets never in model prompt  
- Optional: inbound images / voice notes  

### Tier B — host ops

- One install path (macOS launchd *and/or* Linux systemd *and/or* foreground)  
- One config dir + one secrets file  
- `doctor` / smoke / health  

### Tier C — advanced (flags, not default)

- Call / LiveKit / Playwright media  
- ngrok / public HTTPS  
- Dual-agent collab  
- Multi-room project maps, auto-create projects  

**Public README sells Tier A.** Agency Mac may still run Tier C.

---

## Program phases (do in order)

### Phase 0 — This document (done when written)

- Capture goal, sequence, non-goals, success criteria, resume checklist.  
- Link from project README and agency continuity if useful.

### Phase 1 — Local install & config refactor (required before public)

**Goal:** On the principal Mac, a cold or semi-cold install story is understandable and the live stack stays green.

Suggested work (order flexible within phase):

1. **Inventory truth** — single table of every process, path, secret, env source (extend [filesystem-map](../filesystem-map.md) if stale).  
2. **Collapse human config** — one directory convention for *this* machine first, e.g. either keep agency layout but document one entrypoint, or migrate toward `~/.config/grok-rocketchat/` while agency remains a deployment consumer.  
3. **Hardcode purge** — no username-specific HOME in scripts; `com.velocityworks` names either parameterized or accepted as this-host only with a note.  
4. **Install / doctor** — one script or documented sequence: venv, config validate, launchd render, health check, PROBE-style DM smoke.  
5. **Regression** — existing `ops/rocketchat/tests/` + usability contracts + live DM smoke; max-turns / `!goal` / no-duplicate-posts still hold.  
6. **Write “what we run”** — short ops page: after refactor, where is truth?

**Exit criteria (Phase 1):**

- [ ] Principal can point a future session at one doc and reinstall/restart without tribal memory.  
- [ ] Operator healthy; DM wake works; control plane via `!` works.  
- [ ] Secrets still only in secret files; not in repo or prompts.  
- [ ] No regression on NO DUPLICATE POSTS.  
- [ ] Explicit list of remaining agency-only pins (channels, PGS, ngrok domain).

### Phase 2 — Packaging design (after Phase 1 green)

**Goal:** Decide public boundary without shipping yet.

- File cut line: what is product code vs agency deployment.  
- Revisit IMP-16 extract with Phase 1 layout as input.  
- License, security narrative, dependency matrix (RC, Grok CLI, Python, optional Docker).  
- Repo name / monorepo vs split (`grok-rocketchat` vs keep docs-only repo).  
- What never ships (principal secrets, personal ngrok, research channel maps).

**Exit criteria (Phase 2):**

- [ ] Written packaging plan with Tier A default and explicit non-goals.  
- [ ] Principal approval to open-source or otherwise publish.

### Phase 3 — Public release (only after Phase 2)

- Extract/publish, install docs, demo, support policy.  
- Agency Mac consumes the package (or a release tag), not the other way around.

---

## Non-goals (for this program as written)

- Immediate GitHub publish before Phase 1.  
- Requiring the public to use `~/.grok/agency` or IdeaProjects.  
- Shipping Call/LiveKit as required for v1.  
- Turning Phase A agency monetization into a hard dependency of this share (optional SKU later; not blocking the refactor).  
- Replacing Rocket.Chat with another chat host in the same effort.

---

## Design principles (carry into implementation)

1. **Local truth before public story** — laptop green first.  
2. **Agency is a deployment**, not the product source of truth long-term.  
3. **Tier A default** — advanced paths opt-in.  
4. **`!` not `/`** for control plane in Rocket.Chat clients.  
5. **Restricted wakes by default** (IMP-01).  
6. **One Thinking bubble; images via `rc_post_media` only** (NO DUPLICATE POSTS).  
7. **Config humans can read** — env remains power-user escape hatch.

---

## Related backlog (do not re-litigate blindly)

| Item | Relevance |
| --- | --- |
| [IMP-03 single config surface](../improvements/03-single-config-surface/) | Partial foundation (`rc_config`); Phase 1 extends human UX |
| [IMP-11 launchd templates](../improvements/11-launchd-templates/) | Host install piece |
| [IMP-13 venv](../improvements/13-venv-dependencies/) | Dependency isolation |
| [IMP-16 extract code project](../improvements/16-extract-code-project/) | Deferred cutover — **reopen under Phase 2**, not ad hoc |
| [NF-03 control plane](../../new-features/03-phone-control-plane/) | Product surface to preserve |
| [NF-06…09 next-wave specs](../../new-features/) | Optional product features; not blockers for install refactor |
| Runtime runbook | `~/.grok/agency/ops/ROCKETCHAT.md` |

---

## Session notes that motivated this (2026-07-12)

- Docs wake failed on **max turns 12** (not permissions); raised live default to **100**.  
- RC client steals `/…` (rocket.cat “No such command”); control plane works with **`!goal`** etc.; help/docs updated to prefer `!`.  
- Principal: integration is highly valued; wants public share path; agreed local refactor first, package later; **document goal now, implement another day**.

---

## Resume checklist (next session that picks this up)

1. Read this file end-to-end.  
2. Skim [filesystem-map](../filesystem-map.md) + `ops/ROCKETCHAT.md` for drift.  
3. Confirm live health: operator launchd, `health.json`, principal DM smoke.  
4. Choose Phase 1 first vertical slice (recommend: **config inventory + doctor command**, not extract).  
5. Do **not** open a public repo until Phase 1 exit criteria pass and principal re-approves Phase 2.

---

## Success definition (program complete)

1. Local install/config is boring and documented.  
2. A packaging plan exists that a stranger could follow for Tier A.  
3. Optionally, a public repo exists — only if principal still wants it after Phase 1–2.

Until then, **this goal is parked as documentation only.**
