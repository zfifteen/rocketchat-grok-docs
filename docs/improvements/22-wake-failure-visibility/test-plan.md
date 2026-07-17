# Test plan: IMP-22 Wake failure visibility

**Nav:** [Index](../INDEX.md) · [Folder](./README.md) · [Requirements](./requirements.md)

| Field | Value |
| --- | --- |
| **ID** | IMP-22-TP |
| **Status** | Proposed |

---

## Unit / pure tests (no live RC)

| ID | Case | Expect |
| --- | --- | --- |
| T1 | Fixture log with Hermes-style tool denial | `extract_tool_denials` returns ≥1 line containing tool name |
| T2 | Fixture log with Grok Cancelled + no denial strings | FINAL_ERR still has stopReason=Cancelled; denials empty |
| T3 | Log contains secret-looking token | Redacted in denial lines |
| T4 | More than 3 denials | Cap at N=3, stable order |
| T5 | `format_final_err` + denials | Error block order: one-liner, denials, stopReason, rc, mode, hint, log |
| T6 | Non-empty reply + denials + footer on | Footer present; answer still first |
| T7 | Agy argv builder restricted | Still includes skip-permissions (R12) |

## Operator integration (mock finalize)

| ID | Case | Expect |
| --- | --- | --- |
| I1 | Empty reply file + Cancelled log with denial | Bubble FINAL_ERR includes denial tool |
| I2 | Empty reply, auto-retry once, second empty | No third wake; final still has denials if present in last log |
| I3 | Missing cwd path | Existing missing-cwd FINAL_ERR unchanged (no false denials) |

## Live (optional, principal gate)

| ID | Case | Expect |
| --- | --- | --- |
| L1 | Channel Hermes restricted: force a denied tool (if policy allows) | Bubble names tool or clear partial |
| L2 | Channel Grok restricted normal research wake | No spurious FINAL_ERR regression |
| L3 | DM admin hermes write in project | Completes with yolo; no false denial spam |

---

## Definition of done

- [ ] R1–R4 implemented with pure tests green  
- [ ] At least I1 mock path green  
- [ ] Ops doc matrix R9 updated  
- [ ] No secrets in sample FINAL_ERR fixtures  
- [ ] This IMP status flipped to Done in INDEX  
