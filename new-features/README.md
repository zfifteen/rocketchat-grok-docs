# New features — documentation index

**Created:** 2026-07-10  
**Last reviewed:** 2026-07-12 (feature **10** full chain: SPEC + IP + TP)  
**Status:** Documentation package — runtime may partially exist for some items; each bundle states status  
**Project:** `~/IdeaProjects/rocketchat-grok-docs`  
**Live integration:** `~/.grok/agency/ops/rocketchat/`

This folder is the **entry index** for product-level feature documentation. Each feature lives in its **own numbered subfolder** (a documentation bundle). Features **1–3** and **5–9** have a full four-layer chain (research · spec · test plan · impl plan); feature **4** has research + NF-SPEC-04 + NF-TP-04 + profiles (impl plan deferred; **09** covers enablement); feature **10** has **NF-SPEC-10** + **NF-IP-10** + **NF-TP-10** (research optional / inherited from 04).

For the working system as deployed today, start at the project [README](../README.md) and [docs/](../docs/).

---

## How to navigate

1. **This index** — pick a feature below.  
2. Open the feature **bundle README** (hub for that feature).  
3. Follow the chain (where present): research → spec → test plan → implementation plan.  
4. Return here via each bundle’s “Parent index” / “All features” link.

### Layout (one folder per feature)

```
new-features/
├── README.md                          ← you are here (top-level index)
├── 01-true-voice-in-rc-call/          ← full chain
│   ├── README.md
│   ├── research.md
│   ├── spec.md
│   ├── test-plan.md
│   └── implementation-plan.md
├── 02-streaming-thinking-telemetry/   ← full chain
├── 03-phone-control-plane/            ← full chain
├── 04-agy-rocketchat-collab/          ← research + spec + test plan + draft profiles
│   ├── README.md
│   ├── research.md
│   ├── spec.md                        ← NF-SPEC-04
│   ├── test-plan.md                   ← NF-TP-04
│   └── profiles/
└── 05-reading-attachments/            ← full chain
    ├── README.md
    ├── research.md
    ├── spec.md                        ← NF-SPEC-05
    ├── test-plan.md                   ← NF-TP-05
    └── implementation-plan.md         ← NF-IP-05
```

### Layer roles (do not conflate)

| Layer | File (features 1–3) | Answers | Authority |
| --- | --- | --- | --- |
| Research | `research.md` | Why / options / recommendation | Rationale |
| Spec (`NF-SPEC-*`) | `spec.md` | What **shall** be true | **Normative** requirements & flags |
| Test plan (`NF-TP-*`) | `test-plan.md` | How to prove it | Validation cases |
| Impl plan (`NF-IP-*`) | `implementation-plan.md` | How to build & ship it | Sequencing, PRs, rollback |

If layers disagree: **update the other layers to match the Spec**, or add an **explicit open decision** (do not leave silent drift).

---

## Features

| # | Feature | Bundle | Layers | One-line intent |
| --- | ---: | --- | --- | --- |
| **1** | ~~**True voice-in-RC Call**~~ **RETIRED** | [01-true-voice-in-rc-call/](./01-true-voice-in-rc-call/) | Archive only | **WONTFIX 2026-07-17** — no voice/Call product; see `VOICE_RETIRED.md` |
| **2** | **Streaming Thinking + telemetry** | [02-streaming-thinking-telemetry/](./02-streaming-thinking-telemetry/) | [research](./02-streaming-thinking-telemetry/research.md) · [spec](./02-streaming-thinking-telemetry/spec.md) · [test plan](./02-streaming-thinking-telemetry/test-plan.md) · [impl plan](./02-streaming-thinking-telemetry/implementation-plan.md) | One-bubble stream phases; structured `stopReason` failures |
| **3** | **Phone control plane** | [03-phone-control-plane/](./03-phone-control-plane/) | [research](./03-phone-control-plane/research.md) · [spec](./03-phone-control-plane/spec.md) · [test plan](./03-phone-control-plane/test-plan.md) · [impl plan](./03-phone-control-plane/implementation-plan.md) | `/help` `/status` `/model` `/effort` `/goal` `/new` `/admin once` `/cancel` + elevation tokens |
| **4** | **Antigravity (agy) collab via RC channel** | [04-agy-rocketchat-collab/](./04-agy-rocketchat-collab/) | [research](./04-agy-rocketchat-collab/research.md) · [spec](./04-agy-rocketchat-collab/spec.md) (NF-SPEC-04) · [test plan](./04-agy-rocketchat-collab/test-plan.md) (NF-TP-04) · [profiles](./04-agy-rocketchat-collab/profiles/) · *(IP deferred)* | Long-horizon Grok↔`agy` collab: dual accounts, @mention handoffs, many-turn durable sessions |
| **5** | **Reading attachments** | [05-reading-attachments/](./05-reading-attachments/) | [research](./05-reading-attachments/research.md) · [spec](./05-reading-attachments/spec.md) · [test plan](./05-reading-attachments/test-plan.md) · [impl plan](./05-reading-attachments/implementation-plan.md) | Principal photo/file attach → operator download → Grok `read_file` (images + docs) |
| **6** | **Message reactions as ack** (#11) | [06-message-reactions-ack/](./06-message-reactions-ack/) | [research](./06-message-reactions-ack/research.md) · [spec](./06-message-reactions-ack/spec.md) · [test plan](./06-message-reactions-ack/test-plan.md) · [impl plan](./06-message-reactions-ack/implementation-plan.md) | 👀 / ✅ / ⚠️ on Thinking bubble; no second text post |
| **7** | **Outbound Imagine single path** (#13) | [07-outbound-imagine-single-path/](./07-outbound-imagine-single-path/) | [research](./07-outbound-imagine-single-path/research.md) · [spec](./07-outbound-imagine-single-path/spec.md) · [test plan](./07-outbound-imagine-single-path/test-plan.md) · [impl plan](./07-outbound-imagine-single-path/implementation-plan.md) | Only `rc_post_media.py`; ledger idempotency; no double confirm |
| **8** | **DM health card** (#15) | [08-dm-health-card/](./08-dm-health-card/) | [research](./08-dm-health-card/research.md) · [spec](./08-dm-health-card/spec.md) · [test plan](./08-dm-health-card/test-plan.md) · [impl plan](./08-dm-health-card/implementation-plan.md) | `/health` ops card; no Grok spawn; no secrets |
| **9** | **AGY collab enablement** (#16) | [09-agy-collab-enablement/](./09-agy-collab-enablement/) | [research](./09-agy-collab-enablement/research.md) · [spec](./09-agy-collab-enablement/spec.md) · [test plan](./09-agy-collab-enablement/test-plan.md) · [impl plan](./09-agy-collab-enablement/implementation-plan.md) | Principal-gated arm; hop budget; on top of NF-SPEC-04 |
| **10** | **Lead–peer full collab** | [10-lead-peer-full-collab/](./10-lead-peer-full-collab/) | [spec](./10-lead-peer-full-collab/spec.md) (**NF-SPEC-10**) · [impl plan](./10-lead-peer-full-collab/implementation-plan.md) (**NF-IP-10**) · [test plan](./10-lead-peer-full-collab/test-plan.md) (**NF-TP-10**) | Purpose-created channel; untagged → Grok lead; AGY full peer + peer bar; dual identity serial wakes |

### Bundle hubs (recommended entry per feature)

| # | Bundle README |
| --- | --- |
| 1 | [01-true-voice-in-rc-call/README.md](./01-true-voice-in-rc-call/README.md) **RETIRED** |
| 2 | [02-streaming-thinking-telemetry/README.md](./02-streaming-thinking-telemetry/README.md) |
| 3 | [03-phone-control-plane/README.md](./03-phone-control-plane/README.md) |
| 4 | [04-agy-rocketchat-collab/README.md](./04-agy-rocketchat-collab/README.md) |
| 5 | [05-reading-attachments/README.md](./05-reading-attachments/README.md) |
| 6 | [06-message-reactions-ack/README.md](./06-message-reactions-ack/README.md) |
| 7 | [07-outbound-imagine-single-path/README.md](./07-outbound-imagine-single-path/README.md) |
| 8 | [08-dm-health-card/README.md](./08-dm-health-card/README.md) |
| 9 | [09-agy-collab-enablement/README.md](./09-agy-collab-enablement/README.md) |

---

## Canonical env flags (features 1–3, 5)

| Flag | Feature | Pre-cutover default | Notes |
| --- | --- | --- | --- |
| `RC_CALL_MEDIA_BACKEND` | 1 voice | `playwright` | Flip to `livekit` at V4 |
| `RC_VOICE_MAX_DURATION_S` / `RC_VOICE_IDLE_TIMEOUT_S` | 1 voice | e.g. 1800 / 120 | OD-V5 exact values |
| `RC_WAKE_STREAM` | 2 streaming | `0` | Partials off until fixture stable |
| `RC_STREAM_MIN_INTERVAL_MS` / `MAX_UPDATES` / `MAX_CHARS` | 2 streaming | 800 / 40 / 3500 | Throttle |
| `RC_CONTROL_PLANE` | 3 control | `1` after soak | Master off = legacy wakes |
| `RC_ELEVATION` | 3 control | `1` | Disable `/admin*` only |
| `RC_ADMIN_CONFIRM_S` / `RC_ADMIN_TTL_S` | 3 control | 60 / 900 | Confirm / TTL |
| `RC_ATTACH_ENABLED` | 5 attachments | `1` after P0 | Master inbound pipeline |
| `RC_ATTACH_IMAGE` / `RC_ATTACH_DOCS` | 5 attachments | `1` / `1` (docs after P1) | Type gates |
| `RC_ATTACH_MAX_BYTES` / `MAX_FILES` | 5 attachments | 20 MiB / 5 | Caps |
| `RC_ATTACH_PDF_EXTRACT` | 5 attachments | `0` | Optional P2 |
| `RC_WAKE_APPROVAL_MODE` (existing) | all wakes | `restricted` | Live: restricted → `--permission-mode **auto**` (not `acceptEdits`) |

### Live stack facts (keep docs aligned)

- **Voice/Call RETIRED (2026-07-17):** no Call product; Path C/D archive only. See `~/.grok/agency/ops/rocketchat/VOICE_RETIRED.md`.  
- Restricted wake CLI: `--permission-mode auto` (`wake_lib` + `ops/ROCKETCHAT.md`); `acceptEdits` is **historical failure mode** only.  
- Single-bubble answers: Thinking… → reply file → `chat.update` only (`NO_DUPLICATE_POSTS.md`).

---

## How each research document is structured

Every feature research file covers, in substance:

1. **Problem framing** against this deployment (not generic chatbot theory)  
2. **Current baseline / gaps** with real components and paths  
3. **Candidate technical approaches** with trade-offs  
4. **Integration points** with operator / wake / call (and related IMP work)  
5. **Risks and failure modes**  
6. **Open questions**  
7. **Recommended direction** + success signals  
8. **Sources / primary interfaces** (in-repo + external)

---

## Relationship to existing docs

| Existing doc | Relationship |
| --- | --- |
| [docs/research-voice-media-path.md](../docs/research-voice-media-path.md) | Prior full voice path research; Feature 1 **extends** it into a feature design — does not delete or replace the file |
| [docs/architecture.md](../docs/architecture.md), [message-flow.md](../docs/message-flow.md) | Baseline stack description used for grounding |
| [docs/improvements/](../docs/improvements/) | Mostly **ops/safety** backlog (many Done); this package is **product-level** next features |
| `~/.grok/agency/ops/ROCKETCHAT.md` | Runtime runbook; still authoritative for URLs/restart |

---

## Explicit non-goals of this package

- Implementing Feature 1–5 in Python/launchd/Docker  
- Changing production secrets, ngrok, or RC admin settings  
- Marketing pages or UI mockups as deliverables  
- Replacing the CLI-only `agy-cli-collab` skill with MCP  

---

## Suggested reading order

1. This index  
2. Feature **2** bundle (trust / telemetry) — full chain  
3. Feature **3** bundle (phone control) — full chain  
4. Feature **5** bundle (reading attachments) — full chain  
5. Feature **1** bundle (voice Call) — full chain  
6. Feature **4** [research](./04-agy-rocketchat-collab/research.md) + [spec](./04-agy-rocketchat-collab/spec.md) + [test plan](./04-agy-rocketchat-collab/test-plan.md) (agy collab) — impl plan deferred  

Ship order for implementation (when runtime work begins): **2 → 5 → 3 → 1**; feature **4** after NF-IP-04 (or lab acceptance of NF-SPEC-04 / NF-TP-04). Feature **5** is high phone-trust ROI and largely local to the operator attach path.

Chain per full-chain feature: **research → spec → test plan → implementation plan**.

---

## Document review log

| Date | Action |
| --- | --- |
| 2026-07-10 | Initial research / specs / test plans / impl plans for features 1–3 |
| 2026-07-10 | **Harden review:** forward links on research→spec→TP→IP; canonical flags table; Path C / `auto` vs `acceptEdits` facts; FR-C0 + TP-C-00 master-switch; `RC_CALL_MEDIA_BACKEND` pre-cutover default clarified; layer-role authority rule |
| 2026-07-10 | **Layout reorg:** features 1–3 co-located in per-feature subfolders (`research.md` / `spec.md` / `test-plan.md` / `implementation-plan.md`); this file is the navigable top-level index; global layer trees removed |
| 2026-07-11 | Feature 4 gains [test-plan.md](./04-agy-rocketchat-collab/test-plan.md) (NF-TP-04) inside its bundle; index updated |
| 2026-07-11 | Feature **5** [05-reading-attachments/](./05-reading-attachments/) full chain (research · NF-SPEC-05 · NF-TP-05 · NF-IP-05); inbound image/doc literacy |
