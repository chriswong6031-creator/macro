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
owner: Eval-OS program (CEO Sol; Fable COO execution lanes)
class: build
blast_radius: reversible
ambiguity: scoped
decisions:
  - "DEC:EVAL-OS-RECOVERY-ARCHITECTURE-FREEZE"
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
    status: in_progress
    next_action: >
      #5534/#5577/#5584 are already merged. Recover why stock_desk and thematic_desk have not
      minted their first real general evidence-clock files, preserve demand_chain's real start,
      start stock_desk's matched-control clock only from a valid future controlled claim, and
      verify demand_chain's current runner-local control clock without backdating or creating a
      second clock store.
  - id: W5
    title: Control-leg decision
    status: done
    next_action: >
      None — P0d/#5609 resolved the CEO policy: benchmark is universal baseline; matched control
      is required only where governed policy names a defensible counterfactual. stock_desk and
      demand_chain are matched-control-required; thematic_desk is benchmark-only. #5665/#5672
      repaired demand-chain wiring/replay semantics.
next_action: >
  Execute Eval OS E1 from research/EVAL_OS_RECOVERY_ARCHITECTURE_FREEZE_2026-08-27.md:
  obtain real forward clock starts for stock_desk and thematic_desk from an actual scheduled
  producer run, verify current demand_chain runner-local control-clock truth, and return the
  exact trigger rows/timestamps plus the next real grading receipt. No retrospective rows.
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
  - "Current production track_record now contains explicit and legacy bases and refuses pooling; future consumers must preserve this rather than reconstructing family statistics from raw mixed rows."
  - "data/qledger/control_evidence_clock_start/ is intentionally runner-local/untracked after #5970. A missing Git file is not proof a live clock is absent; production host/runtime truth must be read without inventing another canonical copy."
  - "Only demand_chain currently has a tracked general evidence_clock_start receipt; stock_desk/thematic_desk are not proven to have started prospective accrual."
do_not_redo:
  - "Do NOT re-propose 'the horizon fix is a one-line in_scope_horizons change'. The defect was missing unit declaration."
  - "Do NOT register retrospective claims for stock_desk/thematic_desk/demand_chain. The prior T9 adoption attempt was refused by 3/3 adversarial reviewers because rows were anchored/priced after the fact."
  - "Do NOT add a decorative `backfilled` provenance flag. A mixed store with a flag no authority reader enforces is worse than a small honest one."
  - "Do NOT extend GRADE_HORIZONS above 63 (LH-U6). >63 declared rulers remain check-by clocks, not own-horizon grades, until a separate explicit ruling."
  - "Do NOT re-derive a claim's market from ticker shape alone or provenance alone. Hard fact wins; inference must agree; provenance may decide only where shape is silent."
  - "Do NOT track/commit runner-local matched-control clock files merely to make them visible. #5970 intentionally removed that duplicate-state hazard."
artifacts:
  - research/EVAL_OS_RECOVERY_ARCHITECTURE_FREEZE_2026-08-27.md
  - research/EVAL_OS_SITREP_2026-08-14.md
  - research/EVAL_OS_P0A_HORIZON_CLOCK.md
  - research/PREREG_P0C1_DIRECTION_CORRECT_CONTROL_HITS.md
  - research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md
---

## Reconciliation — 2026-08-27

The 2026-08-14 W4/W5 next actions were stale. #5534 (append-only), #5577 (forward-only desk
registration) and #5584 (legacy-clock authority firewall) are merged. P0d/#5609 plus
#5665/#5672 resolved the control-policy question. Real production evidence later showed that
`demand_chain` started its general prospective clock at `2026-08-19T08:10:37.995754+00:00` and
its matched-control clock at `2026-08-19T08:10:37.332100+00:00` with control `XLU`, while the
tracked general clock estate still has no `stock_desk` or `thematic_desk` start. Therefore W4
remains genuinely in progress for **natural-time accrual**, not for old PR merges; W5 is done.

This workstream owns measurement law, not a new promotion authority and not the engines that
produce claims. T1 remains the single derived engine-registry sibling and is already done under
its own bounded completion law.
