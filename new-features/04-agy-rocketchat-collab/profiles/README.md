# Profiles — RC dual-peer collab identity for `agy` and `grok`

**Status:** Research drafts only — **not installed** into live Antigravity or operator wake paths  
**Parent research:** [../research.md](../research.md) §4.0  
**Date:** 2026-07-10

## Why these files exist

Long-horizon Grok↔agy collaboration on Rocket.Chat needs a **stable social contract** in the model context, not only a one-line wake prompt.

| Identity | Without a profile | With a profile |
| --- | --- | --- |
| **`agy`** (Gemini via Antigravity CLI) | Treats each print as a generic coding task; may not @grok, may impersonate synthesis, may edit freely | Knows it is RC peer `agy`, how to hand off, long-horizon norms, read-only default |
| **`grok`** (existing operator) | Generic `reply_prompt.txt`; may nest `agy` CLI and double-speak Gemini | Knows dual-account mode; tags `@agy`; does not impersonate Gemini |

Project-level `AGENTS.md` (e.g. PGS Lead Scientist) remains **domain** law. These profiles are the **RC collab transport + peer protocol** layer.

## Files

| File | Form | Intended consumer |
| --- | --- | --- |
| [agy-rc-collab.agent.md](./agy-rc-collab.agent.md) | Antigravity custom `agent.md` (frontmatter + body) | `agy --agent rc_collab` (after install under `.agents/agents/rc_collab/`) |
| [agy-rc-collab.AGENTS.md](./agy-rc-collab.AGENTS.md) | Directory rules (no frontmatter) | Copy/symlink as `.agents/rules/rc-grok-collab.md` or merge notes into collab cwd |
| [grok-rc-collab.inject.md](./grok-rc-collab.inject.md) | Operator inject fragment | Prepended when room profile is `agy-collab` and target is `grok` |

## Install options (later — not done here)

1. **Named agent (recommended operator path):** install `agy-rc-collab.agent.md` → project or global `.agents/agents/rc_collab/agent.md`; operator always passes `--agent rc_collab` on collab wakes.  
2. **Auto rules:** install `agy-rc-collab.AGENTS.md` content under the collab `cwd` so every `agy` in that tree inherits it.  
3. **Both:** named agent for explicitness + rules file for interactive desktop sessions.  
4. **Grok:** wire `grok-rc-collab.inject.md` into operator inject when collab room + target `grok`.

## Layering (do not collapse)

```
L1  Project AGENTS.md          → domain (PGS, claim labels, …)
L2  These profiles             → RC dual-peer long-horizon social contract
L3  Per-turn operator inject   → this message, hop count, write scope, UUIDs
```

## Non-goals of this draft folder

- Creating the production RC user `agy`  
- Patching live `reply_prompt.txt` or launchd  
- Installing into `~/.gemini/antigravity-cli`  
- Replacing project `AGENTS.md` Lead Scientist sections  
