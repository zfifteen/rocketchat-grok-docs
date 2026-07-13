# Test plan: DM health card

**Nav:** [README](./README.md) · [Spec](./spec.md)

| Field | Value |
| --- | --- |
| **ID** | **NF-TP-08** |
| **Requirements** | [NF-SPEC-08](./spec.md) |

---

## Test cases

### T1 — Parser recognizes commands

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Parse `/health`, `!health`, `/ops` | control command kind health |
| 2 | Parse `/help` | not health |

**Pass:** R1.

### T2 — Status rule matrix (pure)

| Inputs | Expected overall |
| --- | --- |
| RC ok, pending 0, disk high | GREEN |
| RC fail | RED |
| pending 6 | YELLOW |
| disk 50MB free | RED |

**Pass:** R4, §5.

### T3 — Card renderer omits secrets

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Inject fake password into env of renderer context | password not in output string |

**Pass:** R7, §8.

### T4 — Intercept no Grok spawn (mock)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | handle_principal `/health` | wake_grok not called; one reply path |

**Pass:** G2, R2, R8.

### T5 — Live (opt-in)

| Step | Action | Expected |
| --- | --- | --- |
| 1 | Principal `/health` in DM | table visible &lt;3s |

---

## Traceability

| Spec | Tests |
| --- | --- |
| R1–R2 | T1, T4 |
| R3–R5 | T2 |
| R7 | T3 |
