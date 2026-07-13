# Technical Specification: AGY collab enablement

| Field | Value |
| --- | --- |
| **Spec ID** | **NF-SPEC-09** |
| **Version** | 1.0 |
| **Status** | Specification |
| **Date** | 2026-07-12 |
| **Enhancement list** | #16 |
| **Parent** | [NF-SPEC-04](../04-agy-rocketchat-collab/spec.md) |
| **Test plan** | [NF-TP-09](./test-plan.md) |
| **Impl plan** | [NF-IP-09](./implementation-plan.md) |
| **Primary code** | `wake/rc_collab.py`, `wake/rc_operator_agent.py`, local `agy` CLI |
| **Related** | NF-SPEC-03 control plane, IMP-01 approval modes |

---

## 1. Problem

Dual-peer collab (Grok + Antigravity/`agy`) must be **opt-in per room**, budgeted, and free of self-wake loops. NF-SPEC-04 defines protocol; this spec defines **production enablement gates**.

---

## 2. Goals

| ID | Goal |
| --- | --- |
| G1 | Default production: collab **disarmed** everywhere. |
| G2 | Principal can arm/disarm a room via control plane. |
| G3 | Armed rooms route `@grok` / `@agy` (configurable) without infinite ping-pong. |
| G4 | Hop budget exhaust produces a clear stop message, not silent failure. |
| G5 | Collab off restores single-operator principal→grok behavior. |

## 3. Non-goals

- Public multi-tenant agent forums.
- Auto-arming on channel create.
- Replacing NF-SPEC-04 protocol details (inherit them).

---

## 4. Functional requirements

### 4.1 Master and room flags

| ID | Requirement |
| --- | --- |
| R1 | Env `RC_COLLAB_MASTER=0` (default) disables all collab routing regardless of room state. |
| R2 | Env `RC_COLLAB_MASTER=1` allows per-room arming only. |
| R3 | Room arm state stored in operator `state.json` under collab room map (see NF-SPEC-04 helpers). |
| R4 | Principal-only commands (DM or armed room): `/collab on`, `/collab off`, `/collab status`, `/collab budget &lt;n&gt;`. |
| R5 | Non-principal MUST NOT arm rooms. |

### 4.2 Routing (when master on + room armed)

| ID | Requirement |
| --- | --- |
| R6 | Messages without agent mention: **no dual wake** (optional: principal-only grok as today if policy says so — document chosen default: **principal text still wakes grok only**). |
| R7 | `@grok` → grok wake; `@agy` → agy CLI path; both mentions → ordered handoff per NF-SPEC-04. |
| R8 | Agent must not wake itself on its own messages (self-wake filter). |
| R9 | Hop budget decrements on each agent→agent handoff; at 0, post stop card and pause FSM. |
| R10 | `/collab pause` / `/collab resume` map to NF-SPEC-04 pause FSM. |

### 4.3 Identity and process

| ID | Requirement |
| --- | --- |
| R11 | RC user `agy` (or configured `RC_AGY_USER`) exists and is joined to collab rooms before arm. |
| R12 | agy path uses local CLI helper (no MCP agy_* in operator) per NF-SPEC-04. |
| R13 | Grok wakes in collab rooms use collab inject template (`profiles/grok-rc-collab.inject.md` or successor). |
| R14 | Approval: collab does not elevate past IMP-01; channels remain restricted unless policy explicitly changes. |

### 4.4 Observability

| ID | Requirement |
| --- | --- |
| R15 | Log lines include `collab=True/False target=grok|agy hop=…`. |
| R16 | `/collab status` shows armed, budget remaining, pause state, last hop. |

---

## 5. Non-functional

| ID | Requirement |
| --- | --- |
| N1 | Disarmed path CPU cost ≈ single-operator baseline. |
| N2 | Default hop budget 20 (override env `RC_COLLAB_HOP_BUDGET`); principal may lower. |
| N3 | No secrets in collab status cards. |

---

## 6. Cutover checklist (ops)

1. Create/join RC user `agy`; verify login.  
2. Set `RC_COLLAB_MASTER=1` on operator launchd.  
3. Kickstart operator.  
4. In private test room: `/collab on` as principal.  
5. `@agy ping` / `@grok pong` smoke.  
6. Confirm hop budget decrements; at 0 stops.  
7. `/collab off` restores baseline.  

---

## 7. Acceptance criteria

- [ ] Master off → `@agy` does not spawn agy.  
- [ ] Master on + room off → same.  
- [ ] Master on + room on → mention routing works once each.  
- [ ] Self-message does not re-enqueue same agent.  
- [ ] Budget 0 → stop message; no further agent wakes until principal resets.  
- [ ] NF-TP-04 pure tests still pass; NF-TP-09 enablement tests pass.

---

## 8. Security / cost

- Principal-only arm.  
- Private rooms recommended.  
- Budget caps cost.  
- Restricted approval remains default for both agents’ tool surfaces.
