---
id: DEC:SI-REPLAY-ELIGIBILITY-SEPARATE-FROM-LIVE-AVAILABILITY
title: Stock Identity historical replay eligibility and live availability are separate clocks
status: proposed_for_recovery_validation
date: 2026-08-29
owner: sol
workstream: WS:STOCK-IDENTITY
authority_ref: research/stock_identity/W3AR_REPLAY_ELIGIBILITY_P2_RECOVERY_CHARTER_2026-08-29.md
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
