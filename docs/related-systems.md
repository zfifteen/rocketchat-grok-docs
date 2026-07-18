# Related systems

**Last reviewed:** 2026-07-10

These touch Rocket.Chat or Grok messaging but are **not** the core operator
bridge. Documented so they are not confused with `ops/rocketchat/wake/`.

---

## Agency continuity

| Item | Path |
| --- | --- |
| Home | `~/.grok/agency/` |
| Bootstrap | `START_HERE.md` |
| Live state | `STATE.md` |

**Relationship:** DMs run Grok with `--cwd` set to the agency spine so messaging
can advance continuity work. Continuity files are the program source of truth;
Rocket.Chat is a transport.

---

## ngrok

| Item | Path |
| --- | --- |
| Ops notes | `~/.grok/agency/ops/NGROK.md` |
| Secrets mirror | `~/.grok/agency/secrets/ngrok.env` |
| Agent config | `~/Library/Application Support/ngrok/ngrok.yml` |
| launchd | `com.velocityworks.ngrok-rocketchat` |
| Script | `~/.grok/agency/ops/rocketchat/run_ngrok.sh` |

**Relationship:** Public HTTPS front door for mobile Rocket.Chat. Not involved
in local-only use of `http://localhost:3000`.

---

## Twilio / SMS (Path B partial)

| Item | Path |
| --- | --- |
| Scripts | `~/.grok/agency/ops/twilio/` |
| Secrets | `~/.grok/agency/secrets/twilio.env` |
| Inbox note | `~/.grok/agency/ops/SMS_INBOX.md` |

**Relationship:** Adjacent contact channel for the agency. Not the same as RC
voice notes (Path A) or Jitsi call bot (Path C).

---

## PGS hourly Rocket.Chat notify

| Item | Path |
| --- | --- |
| Notify script | `~/IdeaProjects/prime-gap-structure/scripts/pgs_hourly_rocketchat_notify.py` |
| Hourly shell | `…/scripts/pgs-hourly-advance.sh` |
| Contract | `…/research/00-index/continuity/HOURLY_RELAY_CONTRACT.md` |
| Format tests | `…/research/00-index/tests/test_hourly_rc_format.py` |
| Secrets | **same** `~/.grok/agency/secrets/rocketchat.env` |
| Target room | `#Prime-Gap-Structure` (as `grok`) |

**Relationship:** One-way research memo posting. Shares credentials and the
no-duplicate-posts discipline. Does **not** use the Thinking… operator path.
Research jobs must not post to RC themselves; the hourly EXIT trap owns notify.

**Backlog:** shared bot token surface — [IMP-20](improvements/20-pgs-bot-token/).

---

## Channel project folders

Any channel can cause creation of `~/IdeaProjects/<slug>/` with a small
auto-README (e.g. `agency/`, `general/`). Those folders are **workspaces**, not
integration code.

Overrides live only in:

`~/.grok/agency/ops/rocketchat/wake/channel_projects.json`

---

## Optional / product trees under agency

| Item | Path | Relationship |
| --- | --- | --- |
| Continuity products | `~/.grok/agency/products/` | Unrelated commercial packs |
| Moltbook ops | `~/.grok/agency/ops/moltbook/` | Peer-forum agent identity, not RC |
| Drafts / distribution docs | `ops/*.md` | Agency program, not RC runtime |

---

## This documentation project

| Item | Path |
| --- | --- |
| Docs home | `~/IdeaProjects/rocketchat-agents/` |

Pointers only — does not replace `ops/ROCKETCHAT.md` for live URLs/status.
When runtime moves, update both the live runbook and these docs.
