# Technical Specification: Message reactions as wake ack

| Field | Value |
| --- | --- |
| **Spec ID** | **NF-SPEC-06** |
| **Version** | 1.0 |
| **Status** | Specification |
| **Date** | 2026-07-12 |
| **Enhancement list** | #11 |
| **Prior research** | [research.md](./research.md) |
| **Test plan** | [test-plan.md](./test-plan.md) (NF-TP-06) |
| **Implementation plan** | [implementation-plan.md](./implementation-plan.md) (NF-IP-06) |
| **Primary code** | `wake/rc_operator_agent.py`, RC REST `chat.react` |
| **Related** | NF-SPEC-02 streaming meta, NO_DUPLICATE_POSTS, IMP-01 |

---

## 1. Problem

Wakes need a lightweight, non-textual acknowledgment of start and terminal outcome without posting additional messages or violating single-bubble UX.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
| --- | --- |
| G1 | Principal sees a reaction when a wake starts (Thinking… posted). |
| G2 | Principal sees a distinct reaction for success vs failure at finalize. |
| G3 | No additional `chat.postMessage` for ack. |
| G4 | React failures are logged and ignored (wake still completes). |

### 2.2 Non-goals

- Reacting to principal messages.
- Custom emoji packs or server-side emoji admin.
- Replacing Thinking… / meta text (reactions are additive).

---

## 3. Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Env `RC_WAKE_REACT` (default `1`/`true`/`on`) enables feature; `0`/`false`/`off` disables all react calls. |
| R2 | After successful `post_thinking_placeholder`, operator SHALL call react API on that `msgId` with start emoji (default `eyes` / 👀). |
| R3 | On FINAL_OK finalize, operator SHALL clear start reaction (if API allows) and set success emoji (default `white_check_mark` / ✅). |
| R4 | On FINAL_ERR finalize, operator SHALL clear start reaction and set warning emoji (default `warning` / ⚠️). |
| R5 | Meta stream updates (`Working…`) SHALL NOT add new reactions (start + final only). |
| R6 | React calls use operator REST auth already held by the process; Grok wake process SHALL NOT call `chat.react`. |
| R7 | Any exception from react SHALL be logged (`react failed …`) and MUST NOT change finalize success/failure of the text bubble. |
| R8 | Collab / agy identity posts (if any) MAY share the same policy when they own the Thinking bubble. |

---

## 4. Non-functional requirements

| ID | Requirement |
| --- | --- |
| N1 | React round-trip budget &lt; 2s timeout; do not block wake start beyond fire-and-forget optional thread. |
| N2 | Preferred: non-blocking react (daemon thread) after Thinking post so wake spawn is not delayed. |
| N3 | Emoji defaults overridable via env: `RC_WAKE_REACT_START`, `RC_WAKE_REACT_OK`, `RC_WAKE_REACT_ERR` (RC shortnames). |

---

## 5. API contract (RC 8.6)

### 5.1 Add reaction

```
POST /api/v1/chat.react
{ "messageId": "<thinking_msg_id>", "emoji": "eyes" }
```

Exact field names MUST be verified against RC 8.6 docs/live probe in NF-TP-06 T0; if API uses `msgId` vs `messageId`, implement the live shape.

### 5.2 Remove reaction

If supported:

```
POST /api/v1/chat.react
{ "messageId": "...", "emoji": "eyes", "shouldReact": false }
```

If remove is unsupported, leave start react and add terminal react (document as degraded mode).

---

## 6. State machine

```
[Thinking posted] --react start--> [RUNNING]
[RUNNING] --FINAL_OK--> react OK
[RUNNING] --FINAL_ERR--> react ERR
[RUNNING] --react API fail--> log; continue (no throw)
```

---

## 7. Acceptance criteria

- [ ] With `RC_WAKE_REACT=1`, a live DM wake shows start reaction on Thinking message.
- [ ] Successful wake ends with success reaction.
- [ ] Forced wake failure ends with error reaction.
- [ ] `RC_WAKE_REACT=0` performs zero react HTTP calls (unit mock).
- [ ] No second text bubble created for ack.
- [ ] Usability contracts still pass (no postMessage for answer).

---

## 8. Security / privacy

- No secret material in reactions.
- Do not react on messages not authored by operator (only own Thinking bubble).
