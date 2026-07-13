# Adversarial Review: Lead-Peer Full Collab (NF-SPEC-10)

This document contains an adversarial review of the `lead_peer_full` collaboration protocol defined in `spec.md`, `implementation-plan.md`, and `test-plan.md`. The goal is to identify security vulnerabilities, logic flaws, privilege escalations, and edge cases.

**Reviewer:** AGY  
**Disposition date:** 2026-07-12  
**Spec revision after review:** **NF-SPEC-10 v1.1**

---

## Disposition summary

| # | Finding | Valid? | Disposition |
| --- | --- | --- | --- |
| 1 | Control plane hijacking via agent `!collab` | **Yes** | **Fixed** in spec §7.3 + FR-K1/K1a; tests TP-10-U-09f, C-40, K-11, X-05 |
| 2 | Footer spoofing / prompt injection | **Yes** | **Fixed** FR-F4–F8; tests U-54, U-55, B-32 |
| 3 | Trivial regex peer-bar bypass | **Yes** | **Fixed** FR-B30–B33 + `!collab trivial`; tests U-34* |
| 4 | `owned_paths` path traversal | **Yes** | **Fixed** FR-S4–S6; tests U-56, U-57, B-33, X-06 |
| 5 | Budget drain / agent dual-mention | **Yes** (partial) | **Fixed** default hop_budget **12**, FR-K4 clamp, table #11 Reject dual agent mentions; FR-P8 |
| 6 | Race / double epoch | **Yes** | **Fixed** FR-E7 lock-before-classify; test C-41 |
| 7 | REST identity cross-contamination | **Yes** | **Fixed** FR-ID1–ID4; tests B-01, B-01b |

All seven findings were treated as valid and addressed in documentation (normative shalls + tests + IP goal text). Runtime implementation still pending NF-IP-10 execution.

---

## 1. Control Plane Hijacking & Privilege Escalation

**Finding**: The `!collab` control plane may be vulnerable to agent spoofing.  
**Detail**: In `spec.md` Section 7.3 (Decision Table), Rule 1 evaluated `!collab` as `ControlPlane` *before* author checks. While FR-K1 stated principal-only, a prompt-injected agent could output `!collab complete` / `!collab budget 9999` if the handler only matched regex.  
**Recommendation**: Enforce `author == principal` before executing any `!collab` command; test agent rejection.

### Disposition — **Accepted / Fixed (v1.1)**

- Decision table reordered: **#0 allowlist → #1 agent control shape = Ignore → #2 principal only = ControlPlane**.  
- **FR-K1a**: grok/agy `!collab…` **shall not** mutate state.  
- **FR-K4**: budget clamped (max 50).  
- Tests: **TP-10-U-09f**, **TP-10-C-40**, **TP-10-K-11**, **TP-10-X-05**.  
- IP: GOAL-01, GOAL-14 updated.

---

## 2. Footer Spoofing & Prompt Injection

**Finding**: Machine footer can be spoofed by principal or injection.  
**Detail**: Blind trust of `---rc-collab---` could set `peer_substantive` / `status: done` from untrusted text.  
**Recommendation**: Only accept footer from expected agent identity at end of turn.

### Disposition — **Accepted / Fixed (v1.1)**

- **FR-F4**: parse footer **only** from current wake reply file + `WakeJob.target`.  
- **FR-F5/F7/F8**: ignore/strip footers in principal messages and inject history.  
- **FR-F6**: role must match target.  
- Substantive counting requires trusted footer path + non-LGTM body (FR-B20).  
- Tests: **TP-10-U-54**, **U-55**, **B-32**.  
- IP: GOAL-04 updated.

---

## 3. Peer Bar Bypass via Trivial Regex Match

**Finding**: Prefix `Fix` could mark huge tasks trivial.  
**Detail**: `trivial_bypass_patterns` alone is gameable (`Fix the world: build…`).  
**Recommendation**: Length limits and/or explicit `!collab trivial`.

### Disposition — **Accepted / Fixed (v1.1)**

- **FR-B30–B33**: default `trivial_requires_explicit=true`; principal `!collab trivial`; optional regex only with max chars + denylist.  
- Default hop budget lowered separately (cost).  
- Tests: **TP-10-U-34**, **U-34b**, **U-34c**.  
- IP: GOAL-03, GOAL-14 (`!collab trivial`).

---

## 4. Sandbox Escape via `owned_paths` Path Traversal

**Finding**: `apply_owned_paths` could write outside cwd.  
**Detail**: `../`, absolute paths, etc.  
**Recommendation**: Resolve and require descendant of cwd.

### Disposition — **Accepted / Fixed (v1.1)**

- **FR-S4–S6**: resolve + under-cwd only; reject escapes; propose-only fallback.  
- Profile: `owned_paths_must_be_under_cwd: true`.  
- Tests: **TP-10-U-56**, **U-57**, **B-33**, **X-06**.  
- IP: GOAL-04 includes `sanitize_owned_paths`.

---

## 5. Infinite Loops and Budget Draining

**Finding**: 30 hops still expensive; agent dual-mention ambiguous.  
**Recommendation**: Lower default budget; explicit dual-mention handling.

### Disposition — **Accepted / Fixed (v1.1)**

- Default **`hop_budget`: 12** (FR-P8); principal may raise; **FR-K4** clamp max 50.  
- Decision table **#11**: agent mentions **both** → **Reject** (not silent Ignore).  
- Note: deep collab may still need higher budget via `!collab budget` — intentional principal control, not silent 30.

---

## 6. Concurrency and Race Conditions

**Finding**: Rapid messages might open two epochs before lock.  
**Recommendation**: Queue/lock before epoch evaluation.

### Disposition — **Accepted / Fixed (v1.1)**

- **FR-E7**: lock-before-classify for collab rooms.  
- Test: **TP-10-C-41**.  
- IP: GOAL-10.

---

## 7. Identity Spoofing in REST Post

**Finding**: Shared token state could post as wrong user.  
**Recommendation**: Cache keyed by identity; concurrent isolation tests.

### Disposition — **Accepted / Fixed (v1.1)**

- **FR-ID1–ID4**: per-identity clients; no shared mutable current-token; tests required.  
- Tests: **TP-10-B-01**, **B-01b**.  
- IP: GOAL-06/07 remain the implementation home.

---

## Residual risks (accepted, not fully eliminable in docs)

| Risk | Residual |
| --- | --- |
| Model still “politely” burns 12 hops | Budget + pause; human `!collab pause` |
| Principal `!collab complete` overrides peer bar | Intentional supervisor power (FR-B14) |
| Symlink escape if OS follows links | FR-S5 “when detectable”; implement with `resolve` + samefile checks |
| Live model ignores inject | Peer bar still blocks Done without substantive peer |

---

## Verification for implementers

Before claiming NF-IP-10 security goals done, run at least:

- TP-10-U-09f, U-09g, U-34*, U-54…57  
- TP-10-C-40, C-41, C-42  
- TP-10-B-01, B-01b, B-32, B-33  
- TP-10-K-11, X-05, X-06  

Full matrix remains in [test-plan.md](./test-plan.md) v1.1.
