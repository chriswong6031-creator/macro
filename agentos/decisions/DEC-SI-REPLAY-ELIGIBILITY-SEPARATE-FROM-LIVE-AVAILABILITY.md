---
key: SI-REPLAY-ELIGIBILITY-SEPARATE-FROM-LIVE-AVAILABILITY
question: >
  After W3A Attempt-1 failed because historical eligibility was represented by an
  unlawful generic source-era proxy, should recovery assume one deployment-date
  availability clock for both retrospective W2 replay and future live use, or first
  validate whether historical replay eligibility and live/prospective availability are
  separate clocks under the original W2 source law?
answer: >
  Validate the two clocks separately before any new calibration draw. Historical replay
  eligibility may exist only through the exact already-registered W2 ledger, recompute,
  or locked-spec backcast method with required PIT inputs; live/prospective availability
  remains the real deployment/known-at clock. This decision authorizes the W3AR source-law
  audit only and does not declare any R/B family historically eligible or authorize P2.
rationale: >
  W2 deliberately registered stored-ledger extraction, era-pinned recomputation and
  Class-B locked-spec backcasts while keeping Class-P families prospective-only. The
  failed W3A implementation instead used generic spec-hash existence as source-era proof;
  the later fail-closed repair then exposed a semantic ambiguity between retrospective
  research reconstructibility and actual live deployment. Re-reading P1 is forbidden, so
  the only lawful recovery is to resolve that ambiguity upstream, outcome-free, before a
  fresh evidence epoch is even proposed.
alternatives:
  - option: Treat live deployment/source availability as the sole clock for all historical replay.
    why_not: >
      This may erase W2's explicitly registered recompute and Class-B backcast substrate without
      first adjudicating whether those constructions are lawful retrospective research objects.
  - option: Treat all W2 Class-R/B specs as historically available whenever price history exists.
    why_not: >
      This repeats Attempt-1's overreach. A spec is not date coverage; required PIT source/context/
      identity support must be proven family by family, and ledger-only families cannot be backcast
      unless W2 registered a separate recompute path.
  - option: Re-read SI-SEALED-CAL-P1 after the availability repair.
    why_not: >
      P1's one-time PR-3 look was consumed before population-determining code changed. A second
      read would violate the accepted one-time seal law and contaminate the scientific record.
evidence:
  - "research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md: W2 explicitly distinguishes ledger extraction, registered historical recomputation, Class-B locked-spec backcast, and Class-P prospective-only families."
  - "research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md G-4/§9: historical events come from stored ledgers or era-pinned leak-tested replay; families with no legitimate history accrue prospectively only."
  - "PR #6638 closed unmerged at f0b265f82cc7066a4e8d0b87a8fd62a64dd10177 after Sol rejected the P1 PR-3 seal population and denied a second seal under the one-time-look law."
  - "research/stock_identity/W3AR_REPLAY_ELIGIBILITY_P2_RECOVERY_CHARTER_2026-08-29.md freezes an outcome-free source-law audit and STOP-before-P2-draw boundary."
affects:
  - WS:STOCK-IDENTITY
  - research/stock_identity/W3AR_REPLAY_ELIGIBILITY_P2_RECOVERY_CHARTER_2026-08-29.md
  - agentos/handoffs/STOCK-IDENTITY-2026-08-29-W3AR-REPLAY-ELIGIBILITY-P2.md
confidence: medium
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-29
---

# Decision

W3A recovery must not use one overloaded `family_first_available` concept for both retrospective research replay and live/prospective availability.

The recovery wave must validate a two-clock model against the original frozen Stock Identity contract and W2 source law:

1. **historical replay eligibility** — whether an already-registered W2 family can be lawfully reconstructed for a historical instrument/date/grain from PIT inputs under its exact registered ledger/recompute/locked-spec method, with no outcomes and no firing-based fallback;
2. **live/prospective availability** — when the real family/source became knowable and usable in live operation; this governs Radar/W7 forward evaluation and never permits historical backfill for Class-P families.

This record does **not** yet declare every R/B family historically eligible. W3AR must audit each family. Class P remains historically ineligible by design. Unknown required source/input/era support fails closed.

# Why

Attempt-1 failed after the implementation used generic `spec_hash` existence as historical source/era proof. The subsequent repair correctly failed those rows closed under the then-current Sol ruling, but the audit exposed a deeper semantic mismatch: W2 itself deliberately registered historical ledger extraction, era-pinned recomputation and Class-B locked-spec backcasts. Treating actual software deployment date as the only possible historical availability clock risks deleting the registered W2 research substrate rather than enforcing it.

The correct recovery is not to weaken availability until the old constants work. It is to separate the epistemic clocks, reconcile them to authoritative W2 law, and test feasibility on untouched names without reading outcomes.

# Frozen consequences

- PR #6638 Attempt-1 remains rejected and closed unmerged; no P1 re-read.
- No P2 may be drawn before Sol accepts the W3AR feasibility/prereg packet.
- No fire occurrence, localization metric, outcome, per-name rank or P1 constant value may determine historical replay eligibility.
- `spec_postdates_history` remains explicit on legitimate backcasts.
- Ledger-only families cannot be backcast unless W2 already registered a lawful recompute method.
- Class-P / structurally non-reconstructable families remain prospective-only.
- W7 uses the live/prospective clock, never the retrospective replay clock.
- Any new data/source authority returns to Sol; no second availability/evidence/data plane.

# Falsifier

If the source-law audit shows that current authoritative W2/family contracts do not support an outcome-independent historical replay-eligibility interpretation, or if the untouched clean pool has insufficient lawful replay support for nondegenerate A2/B1 calibration, W3AR returns `NO_GO_CALIBRATION_RECOVERY` or `BLOCKED_NEW_SOURCE_LAW`. It must not draw P2 to find out.
