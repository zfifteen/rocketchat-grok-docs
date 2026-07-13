# Test plan: AGY collab enablement

**Nav:** [README](./README.md) · [Spec](./spec.md)

| Field | Value |
| --- | --- |
| **ID** | **NF-TP-09** |
| **Requirements** | [NF-SPEC-09](./spec.md) |
| **Parent tests** | [NF-TP-04](../04-agy-rocketchat-collab/test-plan.md) |

---

## Preconditions

- `rc_collab.py` pure tests green (NF-TP-04).
- Unit: no live agy required for R1–R5 matrix.
- Live opt-in: `RC_LIVE_COLLAB=1`, users grok+agy+principal, private room.

---

## Test cases

### T1 — Master off

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `RC_COLLAB_MASTER=0`, room armed in state | classify → no agy target |

**Pass:** R1.

### T2 — Master on, room disarmed

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Master 1, room off | principal message → grok-only legacy path |

**Pass:** R2, R6.

### T3 — Arm commands principal-only

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Simulate non-principal `/collab on` | rejected |
| 2 | Principal `/collab on` | armed true in state |

**Pass:** R4–R5.

### T4 — Mention routing

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Armed + `@agy hello` | target agy |
| 2 | Armed + `@grok hello` | target grok |
| 3 | Agent posts without mention | no self-wake |

**Pass:** R7–R8.

### T5 — Hop budget exhaust

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Budget 2; force 2 handoffs | third blocked + stop card |

**Pass:** R9.

### T6 — Disarm restores baseline

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `/collab off` | `@agy` ignored |

**Pass:** G5, R2.

### T7 — Live smoke (opt-in)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Cutover checklist §6 in NF-SPEC-09 | ping/pong once each; no loop |

---

## Traceability

| Spec | Tests |
| --- | --- |
| R1–R5 | T1–T3 |
| R6–R10 | T2, T4–T6 |
| R15–R16 | T3 status; log assert unit |
