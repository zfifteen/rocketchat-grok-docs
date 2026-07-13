# Adversarial Review: Lead-Peer Full Collab (NF-SPEC-10)

*Update (Rev 1.1): This review has been updated to reflect the mitigations implemented in v1.1 of the specifications.*

This document contains an adversarial review of the `lead_peer_full` collaboration protocol defined in `spec.md`, `implementation-plan.md`, and `test-plan.md`. The goal is to identify security vulnerabilities, logic flaws, privilege escalations, and edge cases.

## Status of Findings in v1.1

All findings from the initial adversarial review have been successfully mitigated in v1.1 of the documentation package. 

### 1. Control Plane Hijacking & Privilege Escalation (Mitigated)
**Finding**: The `!collab` control plane may be vulnerable to agent spoofing.
**Mitigation in v1.1**: The decision table explicitly enforces `author != principal` for control commands in Rule 1, ensuring agents outputting `!collab` commands are ignored and do not mutate state (FR-K1/K1a). Tests `TP-10-U-09f` and `TP-10-C-40` enforce this contract.

### 2. Footer Spoofing & Prompt Injection (Mitigated)
**Finding**: The machine footer (`---rc-collab---`) can be spoofed by the principal or via prompt injection.
**Mitigation in v1.1**: `spec.md` now explicitly restricts footer parsing to the *reply file* of the *current wake* and mandates a role match (FR-F4, FR-F6). Furthermore, footers are stripped from untrusted prior history before being injected (FR-F7). This prevents spoofed footers from mutating state. Tested in `TP-10-U-54`, `TP-10-U-55`, and `TP-10-B-32`.

### 3. Peer Bar Bypass via Trivial Regex Match (Mitigated)
**Finding**: The `peer_bar` enforcement can be easily bypassed by prepending trivial keywords like "Fix".
**Mitigation in v1.1**: The `trivial_requires_explicit` flag is now `true` by default, requiring the principal to explicitly issue `!collab trivial`. In addition, regex gaming is prevented by limiting the goal character count (FR-B32) and restricting build-intent keywords. Tested in `TP-10-U-34..34c`.

### 4. Sandbox Escape via `owned_paths` Path Traversal (Mitigated)
**Finding**: The `apply_owned_paths` write scope could allow arbitrary file overwrites.
**Mitigation in v1.1**: Requirements FR-S4 through FR-S6 now enforce strict path sanitization. Any paths containing `..` segment escapes or absolute paths outside the `cwd` are explicitly rejected. Tested in `TP-10-U-56` and `TP-10-B-33`.

### 5. Infinite Loops and Budget Draining (Mitigated)
**Finding**: "Polite" ping-pong loops can still consume significant budget.
**Mitigation in v1.1**: 
- The default hop budget is reduced from 30 to 12, mitigating extensive API cost drains. 
- `!collab budget` commands are now clamped to a maximum limit of 50 (FR-K4). 
- An agent tagging both `@grok` and `@agy` now results in a deliberate `Reject` (Rule 11) rather than falling through to an ambiguous `Ignore`. Tested in `TP-10-U-09g` and `TP-10-C-42`.

### 6. Concurrency and Race Conditions (Mitigated)
**Finding**: Rapid successive messages might circumvent the serial lock.
**Mitigation in v1.1**: FR-E7 mandates "lock-before-classify", meaning the room's serial lock is acquired *before* determining whether to create a new epoch or append to an existing one. This prevents duplicate epoch creations under concurrent message events. Tested in `TP-10-C-41`.

### 7. Identity Spoofing in REST Post (Mitigated)
**Finding**: Lack of strict credential isolation could allow identity spoofing.
**Mitigation in v1.1**: FR-ID1 through FR-ID4 strictly require authentication caching to be keyed by identity (`grok` vs `agy`) preventing cross-identity token usage. Tested thoroughly via `TP-10-B-01` and `TP-10-B-01b`.

---
**Conclusion:** The updated v1.1 specifications securely address the identified adversarial vectors. The protocol is resilient against prompt injection, state manipulation, sandbox escapes, and cost/concurrency abuse.
