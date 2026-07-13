# Technical Specification: DM health card

| Field | Value |
| --- | --- |
| **Spec ID** | **NF-SPEC-08** |
| **Version** | 1.0 |
| **Status** | Specification |
| **Date** | 2026-07-12 |
| **Enhancement list** | #15 |
| **Test plan** | [NF-TP-08](./test-plan.md) |
| **Impl plan** | [NF-IP-08](./implementation-plan.md) |
| **Primary code** | `wake/rc_commands.py`, `wake/rc_operator_agent.py` control-plane intercept |
| **Related** | NF-SPEC-03 phone control plane, IMP-12 health watchdog, IMP-01 |

---

## 1. Problem

Principal needs a fast, secret-free snapshot of integration health from Rocket.Chat DM.

---

## 2. Goals

| ID | Goal |
| --- | --- |
| G1 | `/health` (and `/ops`) returns one markdown card in &lt;2s typical. |
| G2 | No Grok CLI spawn for health. |
| G3 | Zero secrets, tokens, passwords, or full env dumps. |
| G4 | Works under restricted approval mode (control plane path). |

## 3. Non-goals

- Public unauthenticated health HTTP (see IMP-12 for process watchdog separately).
- Auto-remediation (restart Docker, etc.) without explicit later commands.
- Live packet capture / ngrok API keys in card.

---

## 4. Functional requirements

| ID | Requirement |
| --- | --- |
| R1 | Commands `/health` and `/ops` are known control-plane commands (prefix `/` or `!`). |
| R2 | Intercept **before** Thinking… enqueue (same as other control commands). |
| R3 | Card MUST include rows for at least: |
| | • Operator process: up / pid age if available |
| | • `RC_BASE` host (not credentials) |
| | • Public site URL host if configured (from non-secret config) |
| | • Approval mode (`restricted`/`admin`) |
| | • Watched room count + short name list (cap 8) |
| | • `pending_wakes` length |
| | • Last wake: age + rc if known from state/logs |
| | • Call: `RC_CALL_MEDIA_BACKEND` + call-lock present yes/no |
| | • Log dir free space (human MB/GB) |
| | • Autoreload flag if present |
| R4 | Overall status line: `GREEN` / `YELLOW` / `RED` from rules in §5. |
| R5 | Any probe failure becomes `n/a` or `error: &lt;short&gt;` — still return a card. |
| R6 | Optional `RC_HEALTH_DEEP=1`: also curl `RC_BASE/api/info` (timeout 3s). Default off or on — document; default **on** if cheap. |
| R7 | MUST NOT read or print `rocketchat.env` values into the card. |
| R8 | Response is a single bubble via control-plane post/update path used by other commands (not a second Grok answer bubble). |

---

## 5. Status rules (normative)

| Condition | Level |
| --- | --- |
| RC `/api/info` unreachable | RED |
| Wake lock stuck older than policy OR pending_wakes &gt; 5 | YELLOW |
| Last wake rc ≠ 0 within last hour | YELLOW |
| Call lock present &gt; max busy policy | YELLOW |
| Log disk free &lt; 500MB | YELLOW |
| Log disk free &lt; 100MB | RED |
| Else all probes ok | GREEN |

---

## 6. Card format (example)

```markdown
**RC health — GREEN**

| Check | Value |
| --- | --- |
| Operator | up · pid 12345 |
| Approval | restricted |
| Rooms | 5 · dm:principal, … |
| Pending | 0 |
| Last wake | 12m ago · rc=0 |
| Call backend | playwright · lock=no |
| Disk (logs) | 12 GB free |
```

---

## 7. Acceptance criteria

- [ ] `/health` from principal DM returns table without Grok spawn.
- [ ] Secrets file contents never appear in output (negative test with fake secret string not leaked).
- [ ] Forced RC down → RED overall.
- [ ] Unit tests for status rule matrix and card renderer pure functions.

---

## 8. Security

- Secret store paths may be **named** (`secrets/rocketchat.env` exists yes/no) but never contents.
- No auth tokens in card.
