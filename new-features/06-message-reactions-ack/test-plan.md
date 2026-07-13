# Test plan: Message reactions as wake ack

**Nav:** [README](./README.md) · [Spec](./spec.md)

| Field | Value |
| --- | --- |
| **ID** | **NF-TP-06** |
| **Requirements** | [NF-SPEC-06](./spec.md) |
| **Type** | Unit (mocks) + optional live (`RC_LIVE_REACT=1`) |

---

## Preconditions

- Operator code under `~/.grok/agency/ops/rocketchat/`.
- Unit tests: no live RC required.
- Live: principal↔grok DM, operator online, `RC_LIVE_REACT=1`.

---

## Test cases

### T0 — Discover API shape (live, once)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Login as grok | success |
| 2 | Post temp message | msgId |
| 3 | Try `chat.react` variants | Document working JSON body |
| 4 | Delete temp message | cleanup |

**Pass:** R5 API fields recorded in impl notes.

### T1 — React helper unit

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Mock HTTP; call `react_message(mid, emoji)` | One POST with correct body |
| 2 | Mock 500 | Returns False; no exception |

**Pass:** R6–R7.

### T2 — Disabled by env

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `RC_WAKE_REACT=0` | No HTTP calls from drain hooks |

**Pass:** R1.

### T3 — Start + OK path (mock drain)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Fake post Thinking → id `t1` | react start on `t1` |
| 2 | Finalize OK | react OK; optional unreact start |

**Pass:** R2–R3, R5.

### T4 — ERR path

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Wake fails empty reply | react ERR |

**Pass:** R4.

### T5 — Live smoke (opt-in)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Principal: `RC_PROBE_react` | Thinking shows 👀 then ✅ |
| 2 | History | No extra grok text bubbles for ack |

**Pass:** Acceptance in spec §7.

### T6 — Regression

| Step | Action | Expected |
| --- | --- | --- |
| 1 | `test_usability_contracts.py` | All pass; no second postMessage for answer |

---

## Traceability

| Spec | Tests |
| --- | --- |
| R1 | T2 |
| R2–R4 | T3–T4, T5 |
| R5 | T3 |
| R6–R7 | T1 |
| N1–N3 | T1 timeout mock; env override unit |
