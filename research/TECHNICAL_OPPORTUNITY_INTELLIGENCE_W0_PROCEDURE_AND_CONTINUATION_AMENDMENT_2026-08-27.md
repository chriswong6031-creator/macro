# Technical Opportunity Intelligence — W0 Procedure and Continuation Amendment

**Date:** 2026-08-27  
**Program:** `WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE`  
**Amends:** the W1 Evidence Census and W2-0 Data/Clock Archaeology commission packets  
**Original W0 authoring procedure pin:** `Mastermind@af43f356f4f7f34cb3514d1d1099b50444af8487`  
**Final-review and commission procedure pin at authoring time (2026-08-27):** `Mastermind@ac1c045ed4cdf0b2b87fbc81760effa909271436` — superseded for finalization by the pin in §8  
**Authority:** current protected `COMMISSION_WAVE.md` continuation-watch law; records only

---

## 1. Scope of this amendment

The original W0 architecture and research contracts remain substantively controlling. This amendment adds the continuation and transport discipline introduced by the current protected Sol Skillpack before W1 or W2-0 may be dispatched.

It does not authorize either wave to start before W0 is accepted and merged. It creates no worker, Job, Attempt, Wake, queue, Slack message, runtime, research result, or production capability.

For W1 and W2-0, document precedence is:

1. current protected Sol Skillpack at the exact dispatch pin;
2. the Technical Opportunity Intelligence architecture freeze;
3. this amendment;
4. the relevant W1 or W2-0 commission packet;
5. current DNR, owner contracts, Agent OS, GitHub, and source truth.

If a later protected Skillpack changes continuation procedure again, the dispatching Sol must re-pin it and apply the newer procedure without silently changing the accepted product or research architecture.

---

## 2. Stable operation and carrier bindings

### W1 — Evidence Census

- stable operation key: `TOI-W1-EVIDENCE-CENSUS-V1`
- one logical carrier/thread must be named at dispatch;
- no blind retry, duplicate session, or automatic transport failover;
- the carrier remains bound until a canonical `RESULT`, accepted terminal `BLOCKED`, explicit cancellation, or Sol reconciliation.

### W2-0 — Data and Clock Archaeology

- stable operation key: `TOI-W2-0-DATA-CLOCK-V1`
- one logical carrier/thread must be named at dispatch;
- no blind retry, duplicate session, or automatic transport failover;
- the carrier remains bound until a canonical `RESULT`, accepted terminal `BLOCKED`, explicit cancellation, or Sol reconciliation.

A branch, issue, Linear projection, Slack delivery, queue receipt, ACK, or generated plan is not evidence that a worker is executing.

---

## 3. Required worker ACK before modification

Before changing a repository or producing research artifacts, the worker must reply on the same carrier with an ACK that states:

1. the exact operation key;
2. that the entire architecture freeze, this amendment, and the relevant commission packet were read;
3. the current protected Skillpack pin used by the worker, when the worker is a Sol/Fable principal subject to that procedure;
4. the exact current repository base SHA or the reason no repository modification will occur;
5. the relevant current owner, open-PR, branch, worktree, and path-collision census;
6. the one carrier to which all later `BLOCKED`, `DECISION_REQUEST`, and `RESULT` returns will be posted;
7. the stop condition and explicit non-goals;
8. confirmation that W3 outcome testing, Prophet/Golden Confluence authority, a new data plane, and a duplicate registry remain out of scope.

An ACK proves receipt and declared understanding only. It does not prove live activity, progress, or completion.

---

## 4. Typed return contract

Every nontrivial return uses one of three top-level types.

### `BLOCKED`

Use when the mission cannot proceed safely under current authority or evidence. Include:

- operation key;
- exact carrier and current head, if any;
- blocker classification;
- evidence and commands;
- whether any modification may have occurred;
- whether the block is terminal or can be re-armed;
- exact action that would clear it;
- paths and work that must not be duplicated.

### `DECISION_REQUEST`

Use only for a real architecture, authority, rights, clock, scope, or evidence fork that the packet does not settle. Include:

- operation key;
- one precise question;
- alternatives and consequences;
- recommendation;
- evidence already gathered;
- work safely completed before the fork;
- work held pending decision.

The worker waits on the same carrier after posting. No self-resolution of a reserved Chairman/Sol decision.

### `RESULT`

Use only at the wave stop condition. Include:

- operation key and carrier;
- exact repository, branch, immutable head, and PR when applicable;
- changed files and artifact inventory;
- exact validation and CI receipts;
- findings, nulls, contradictions, rights/coverage gaps, and discovered collisions;
- capability-state delta using the canonical vocabulary;
- what the result proves and does not prove;
- unresolveds and falsifiers;
- required continuation handoff;
- exact next action and held downstream waves.

A `RESULT` is a return for Sol review, not automatic acceptance or permission to start W3.

---

## 5. Reciprocal continuation watching

When a dispatched W1 or W2-0 carrier is expected to return:

- Sol records the carrier and operation key and watches that exact carrier for typed returns;
- the worker remains available on the same carrier after `ACK`, `BLOCKED`, or `DECISION_REQUEST` until Sol responds or the commission expires/cancels;
- any temporary watcher is read-only and non-authoritative;
- a watcher may surface a return but may not interpret it as acceptance, reroute work, create a duplicate carrier, or modify canonical state;
- after a nonterminal return, continuation requires an explicit Sol re-arm on the same carrier;
- if no reliable watch mechanism is available, record `WATCH_UNAVAILABLE` and require deliberate manual polling. Do not pretend continuous monitoring exists.

The long-run Worker Presence/Wake architecture remains canonical. This temporary continuation discipline does not create another liveness or control plane.

---

## 6. Wave-specific watch expectations

### W1

Expected returns that require immediate Sol attention include:

- a primary-source or formula conflict that changes a P0/P1 candidate;
- an opaque/proprietary method whose mechanics or rights cannot be lawfully established;
- a DNR collision;
- evidence that two local implementations share a name but differ materially;
- a proposed passport/equivalence schema change after priorities or outcomes were inspected;
- a current carrier collision over W1 artifacts.

### W2-0

Expected returns that require immediate Sol attention include:

- unknown rights for research, derived storage, subscriber display, or public display;
- irreconcilable raw/adjusted price bases;
- material Terminal-versus-research 4H bar disagreement;
- an apparent need for a second feed, collector, store, identity plane, or correction authority;
- inability to define a point-in-time universe denominator;
- delisting or ticker-reuse contamination that makes the planned claim unreadable;
- a current carrier collision over the audited owner paths.

---

## 7. Dispatch and acceptance boundary

W1 and W2-0 may run in parallel only after W0 is merged and Sol has rechecked current owners, repository heads, open PRs, worktrees, rights, and path collisions.

Their carriers must be disjoint. Neither carrier may edit the other wave’s artifacts or broaden into W3.

No downstream claim is authorized merely because:

- a handoff was delivered;
- a worker ACKed;
- a branch or PR exists;
- CI is green;
- a queue says `QUEUED`;
- a report was generated;
- a watcher surfaced a message.

Sol reviews each returned exact head and evidence packet against the accepted mission. W3 remains held until both W1 and W2-0 are accepted and Sol freezes a new preregistration with exact species versions, clocks, targets, comparators, search-family size, and kill gates.

---

## 8. W0 finalization re-pin (2026-08-28, `technical-opportunity-w0-finalize-20260828-sol-001`)

The W0 carrier was finalized for Sol acceptance under a fresh protected-procedure pin. Earlier pins in this document and in the sibling W0 records are preserved as history and remain the pins under which their evidence was actually gathered; they are not retroactively rewritten.

- **Finalization procedure pin:** `Mastermind@038d1271b98e88b24e039c1ce4127d6503945845` (protected `master`; schema `mastermind.sol_skillpack.v1`, skillpack_version 1.0.1, minimum_bootstrap_major 1; `RECONCILE_STATE` and `COMMISSION_WAVE` re-read at this pin).
- **Reconciliation base:** Macro `main@ba270c60c1fe825f2e9fce1fcf507b7272a67b63`, merged into the carrier with zero conflicts; none of the 42 main commits since merge-base `463bb3b4` touched any W0 file, and no open PR other than #6570 touches the W0 records.
- **No architecture change:** the frozen two-queue law, Setup Species ownership, Live Entry Radar boundary, 4H evidence gate, wave scopes, and all DNR/do-not-redo entries are unchanged by this finalization. Only reconciliation and procedure-currency records were added.
- **Boundary for later pins:** per §1, a still-later protected Skillpack at W1/W2-0 dispatch time is re-pinned by the dispatching Sol at that moment; this section does not freeze procedure for downstream waves.
- **Continuation re-pin (2026-08-28, Sol REQUEST_REPAIR/RULING on the same operation):** the finalization above was forward-reconciled a second time after Sol's CONTINUE edge, under protected Skillpack `Mastermind@c4c39423f595cfe669961b871405eb2b13ff65c2` (v1.0.1) and then-current Macro main `9aa194c0f737d219b9dc4c169fef5108ea9e89fd` — again a zero-conflict merge with no W0 file touched by main and no frozen TOI owner path moved. The intervening Agent OS law change (optional closed-contract `wait` field on workstreams/waves) is additive and does not conflict with the frozen two-queue/species/Radar/4H boundary. Earlier pins in this section remain the history of the first finalization pass.
- **Second continuation re-pin (2026-08-28, Sol REQUEST_REPAIR on the same operation):** forward-reconciled again under protected Skillpack `Mastermind@801f8e5b1de0f4866414f670d5612d1dd45de208` (current master; Sol's stated pin `14056772` is a clean ancestor; v1.0.1) and then-current Macro main `9dc49a6e86b34dd79e14535c43aa3d9a85d3f1ed` — zero conflicts, 0 of the intervening main commits touch any W0 file, frozen TOI owner paths untouched, no semantic source-law collision.
