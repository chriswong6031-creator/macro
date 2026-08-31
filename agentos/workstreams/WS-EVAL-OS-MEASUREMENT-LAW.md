---
key: EVAL-OS-MEASUREMENT-LAW
title: Intelligence Evaluation OS — the measurement law wave (horizon clock, market ruler, promotion legality)
objective: >
  Make the qledger Universal Scoreboard measure what it says it measures: every claim
  declares its horizon UNIT, one resolver answers check_by/maturity/grading/render, the
  market ruler is the exchange the claim is priced on, promotion arithmetic is
  direction-correct and legality-gated, and forward-only registration starts a real
  evidence clock. Done when three desks are accruing prospective claims at their own
  declared rulers and no published promotion number is computed on a basis it was not
  measured on.
status: active
program: qualitative-intelligence
repos:
  - macro
owner: Eval-OS program (CEO Sol; bounded operator recovery lanes)
class: build
blast_radius: reversible
ambiguity: scoped
decisions:
  - "DEC:EVAL-OS-RECOVERY-ARCHITECTURE-FREEZE"
  - "DEC:EVAL-OS-DARK-WORKER-RECOVERY-2026-08-29"
waves:
  - id: W1
    title: Architecture + metric validity
    status: done
    next_action: "None — PR #5471 merged. The separate fleet-wide strict-hardening residue remains a later completion wave because the current CLI is still WARN-tier by default."
  - id: W2
    title: Horizon-clock contract + market ruler
    status: done
    next_action: "None — PRs #5559 then #5563 merged. #5563 fixed #5559's shape_is_decisive defect."
  - id: W3
    title: Promotion legality substrate
    status: done
    next_action: "None — #5519, #5573, #5572 and later clock-legality repairs landed. Unified final-path adversarial acceptance remains a separate continuation wave, not a reopening of these merges."
  - id: W4
    title: Append-only law + forward-only accrual
    status: done
    next_action: >
      None — natural-time forward accrual is now PROVEN_LIVE for all three focal desks. demand_chain
      started its general clock at 2026-08-19T08:10:37.995754+00:00; stock_desk started at
      2026-08-29T11:08:11.609328+00:00; thematic_desk started from intended scheduled daily run #295
      with accepted real claim 893057199f47d7d6 and durable write-once clock
      2026-08-31T05:01:42.762963+00:00. stock_desk matched-control remains truthfully NOT STARTED
      because no accepted stock claim has yet carried a valid governed control leg. The separate
      general-clock authority-cohort semantic gap is not solved by W4 completion and remains outside
      this wave's authority.
  - id: W5
    title: Control-leg decision
    status: done
    next_action: >
      None — P0d/#5609 resolved the CEO policy: benchmark is universal baseline; matched control
      is required only where governed policy names a defensible counterfactual. stock_desk and
      demand_chain are matched-control-required; thematic_desk is benchmark-only. #5665/#5672
      repaired demand-chain wiring/replay semantics.
next_action: >
  P1 promotion-integrity acceptance is the next measurement-law gate under frozen recovery
  architecture. Scope is frozen in records-only PR #6686 / operation
  eval-os-p1-promotion-integrity-acceptance-20260830-sol-001, preferred avenue CTO Sol,
  CAPACITY_SELECTABLE. Execution remains HELD_COLLISION_A1_PR_6651 while A1 PR #6651 is open and
  modifying engine/qledger.py + scripts/grade_qledger.py, and placement remains WAITING_CAPACITY /
  needs_placement until a lawful concrete receiver is supplied. Do not commission P1 until both
  gates clear. Preserve the OWNER_SEMANTIC_GAP boundary rather than silently inventing new
  cohort/promotion authority.
owns_paths:
  - engine/qledger.py
  - engine/qledger_validity.py
  - scripts/grade_qledger.py
  - research/EVAL_OS_*.md
  - research/PREREG_P0C1_*.md
discoveries:
  - DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG
landmines:
  - "engine/source_registry.py keeps its OWN _add_trading_days NYSE walker and grades narrative_source_call through its own exit. 'ONE resolver' is true only for claims that grade through qledger; do not overstate qledger scope."
  - "Current production track_record contains explicit and legacy bases and refuses pooling; future consumers must preserve this rather than reconstructing family statistics from raw mixed rows."
  - "data/qledger/control_evidence_clock_start/ is intentionally runner-local/untracked after #5970. A missing Git file is not proof a live clock is absent; production host/runtime truth must be read without inventing another canonical copy."
  - "All three focal general evidence clocks are now durable/proven, but a general evidence_clock_start is not itself an authority-cohort filter. Do not reinterpret W4 completion as solving the deferred cohort-authority semantic gap."
  - "The canonical nightly thematic path is daily engine -> cl_baskets -> build_baskets -> build_allocation -> _run_thematic_desk -> engine.thematic_desk.run. PR #6677 repaired the sub-quorum fail-soft seam; do not invent a second producer or scheduler."
do_not_redo:
  - "Do NOT re-propose 'the horizon fix is a one-line in_scope_horizons change'. The defect was missing unit declaration."
  - "Do NOT register retrospective claims for stock_desk/thematic_desk/demand_chain. The prior T9 adoption attempt was refused by 3/3 adversarial reviewers because rows were anchored/priced after the fact."
  - "Do NOT add a decorative `backfilled` provenance flag. A mixed store with a flag no authority reader enforces is worse than a small honest one."
  - "Do NOT extend GRADE_HORIZONS above 63 (LH-U6). >63 declared rulers remain check-by clocks, not own-horizon grades, until a separate explicit ruling."
  - "Do NOT re-derive a claim's market from ticker shape alone or provenance alone. Hard fact wins; inference must agree; provenance may decide only where shape is silent."
  - "Do NOT track/commit runner-local matched-control clock files merely to make them visible. #5970 intentionally removed that duplicate-state hazard."
  - "Do NOT re-mint or rewrite any focal desk's first general clock; demand_chain, stock_desk and thematic_desk now have immutable production receipts."
artifacts:
  - research/EVAL_OS_RECOVERY_ARCHITECTURE_FREEZE_2026-08-27.md
  - research/EVAL_OS_SITREP_2026-08-14.md
  - research/EVAL_OS_P0A_HORIZON_CLOCK.md
  - research/PREREG_P0C1_DIRECTION_CORRECT_CONTROL_HITS.md
  - research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md
  - agentos/handoffs/EVAL-OS-E1-THEMATIC-COHORT-RECOVERY-2026-08-29.md
  - agentos/handoffs/EVAL-OS-P1-PROMOTION-INTEGRITY-ACCEPTANCE-2026-08-30.md
---

## Reconciliation — 2026-08-27

The 2026-08-14 W4/W5 next actions were stale. #5534 (append-only), #5577 (forward-only desk
registration) and #5584 (legacy-clock authority firewall) are merged. P0d/#5609 plus
#5665/#5672 resolved the control-policy question. Real production evidence later showed that
`demand_chain` started its general prospective clock at `2026-08-19T08:10:37.995754+00:00` and
its matched-control clock at `2026-08-19T08:10:37.332100+00:00` with control `XLU`, while the
tracked general clock estate still had no `stock_desk` or `thematic_desk` start. Therefore W4
remained genuinely in progress for natural-time accrual, not for old PR merges; W5 was done.

This workstream owns measurement law, not a new promotion authority and not the engines that
produce claims. T1 remains the single derived engine-registry sibling and is already done under
its own bounded completion law.

## Recovery reconciliation — 2026-08-29

The original E1 child `eval-os-e1-clock-accrual-20260827` produced two accepted implementation
repairs before its worker dialogue went dark: #6598 fixed stock/thematic anchor-at-registration
without weakening the forward gate, and #6607 persisted qledger state from the stock-briefs
production lane. Canonical main then gained a real `stock_desk` clock receipt with
`first_prospective_registration_utc=2026-08-29T11:08:11.609328+00:00`, and qledger produced a
post-clock grading run. The stock general-clock sub-capability therefore became `PROVEN_LIVE`.

The successor recovery child later proved the US thematic zero-output branch was a model/provider/
parse/fail-soft suppression defect rather than an honest no-call. PR #6677 repaired only the
sub-quorum thematic panel fallback/logging seam and merged as
`3a6f20dd20589c7975f828b0a4705b98dc34dc95`. That child was terminally stopped after exact-head
CI/review; it did not fabricate a thesis or clock and did not change qledger/grader/promotion law.

The separate cohort finding was preserved as an authority boundary: current general
`evidence_clock_start` is not itself an authority-cohort filter. Matched-control cohort gating is a
separate mechanism. Any future semantic change belongs to its owning wave/authority, not to E1.

## Production closeout — 2026-08-31

Intended scheduled daily run #295 (`33345595359`) exercised the merged #6677 path in real
production. The US thematic desk naturally emitted source `us-2026-08-28-20260831050106-1`, which
registered accepted qledger claim `893057199f47d7d6` for `GDX`, direction `+1`, benchmark `SPY`,
horizon `20 trading_days`, with registration timestamp
`2026-08-31T05:01:42.723675+00:00`. Canonical
`data/qledger/evidence_clock_start/thematic_desk.json` now records
`first_prospective_registration_utc=2026-08-31T05:01:42.762963+00:00` and run head
`09cc2e0f465c5a27f7382b3656694b5d068ef00d`.

This receipt closes W4 truthfully: demand_chain, stock_desk and thematic_desk are all accruing from
real prospective general clocks under their declared rulers. It does **not** start stock_desk's
matched-control clock, does **not** reinterpret the deferred general-clock cohort-authority gap,
and does **not** authorize P1 by itself.

The next measurement-law dependency is P1 promotion-integrity acceptance, already frozen in PR
#6686. P1 remains held until active A1 PR #6651 reaches terminal release/merge disposition and a
lawful concrete CTO Sol receiver placement exists. No old E1 child/thread/watcher may be reopened or
reused to bridge that independent wave.
