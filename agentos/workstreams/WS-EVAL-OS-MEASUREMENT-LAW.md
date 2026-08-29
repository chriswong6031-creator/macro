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
    status: in_progress
    next_action: >
      stock_desk general forward accrual is now PROVEN_LIVE from a real production registration:
      data/qledger/evidence_clock_start/stock_desk.json starts at
      2026-08-29T11:08:11.609328+00:00 for 20 trading days. stock_desk matched-control remains
      truthfully NOT STARTED because the accepted stock receipts did not carry a valid governed
      control. thematic_desk still has no durable general clock. The old E1 worker child was
      terminally stopped for stale worker continuity after its effects were reconciled. A fresh
      bounded E1 recovery child must classify why the already-wired real US thematic nightly path
      yielded no registrable thesis/claim, produce the first lawful thematic prospective claim +
      clock when the underlying desk actually makes one (or repair only a proven blocking defect),
      and return explicit real grader/cohort proof that pre-clock rows are excluded.
  - id: W5
    title: Control-leg decision
    status: done
    next_action: >
      None — P0d/#5609 resolved the CEO policy: benchmark is universal baseline; matched control
      is required only where governed policy names a defensible counterfactual. stock_desk and
      demand_chain are matched-control-required; thematic_desk is benchmark-only. #5665/#5672
      repaired demand-chain wiring/replay semantics.
next_action: >
  Place and execute fresh child eval-os-e1-thematic-cohort-recovery-20260829-sol-001 under the
  current protected Skillpack. Do not redo the stock repair or stock general-clock start. Close the
  remaining E1 truth gap: classify the real US thematic zero-output path, obtain the first lawful
  thematic_desk prospective clock from real production without manufacturing a thesis, and prove
  the real grader/cohort excludes pre-clock rows. Preserve demand_chain's runner-local control law
  and stock matched-control NOT STARTED state until real governed evidence changes it.
owns_paths:
  - engine/qledger.py
  - engine/qledger_validity.py
  - scripts/grade_qledger.py
  - research/EVAL_OS_*.md
  - research/PREREG_P0C1_*.md
discoveries:
  - DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG
  - DSC:E1-STOCK-CLOCK-PROVEN-THEMATIC-STILL-NO-CLAIM
landmines:
  - "engine/source_registry.py keeps its OWN _add_trading_days NYSE walker and grades narrative_source_call through its own exit. 'ONE resolver' is true only for claims that grade through qledger; do not overstate qledger scope."
  - "Current production track_record contains explicit and legacy bases and refuses pooling; future consumers must preserve this rather than reconstructing family statistics from raw mixed rows."
  - "data/qledger/control_evidence_clock_start/ is intentionally runner-local/untracked after #5970. A missing Git file is not proof a live clock is absent; production host/runtime truth must be read without inventing another canonical copy."
  - "stock_desk now has a durable real general clock; thematic_desk is the only focal desk still missing a tracked general evidence_clock_start receipt."
  - "The canonical nightly thematic path is already wired daily engine -> cl_baskets -> build_baskets -> build_allocation -> _run_thematic_desk -> engine.thematic_desk.run. Do not invent a second producer or misclassify the remaining gap as a generic scheduler absence."
do_not_redo:
  - "Do NOT re-propose 'the horizon fix is a one-line in_scope_horizons change'. The defect was missing unit declaration."
  - "Do NOT register retrospective claims for stock_desk/thematic_desk/demand_chain. The prior T9 adoption attempt was refused by 3/3 adversarial reviewers because rows were anchored/priced after the fact."
  - "Do NOT add a decorative `backfilled` provenance flag. A mixed store with a flag no authority reader enforces is worse than a small honest one."
  - "Do NOT extend GRADE_HORIZONS above 63 (LH-U6). >63 declared rulers remain check-by clocks, not own-horizon grades, until a separate explicit ruling."
  - "Do NOT re-derive a claim's market from ticker shape alone or provenance alone. Hard fact wins; inference must agree; provenance may decide only where shape is silent."
  - "Do NOT track/commit runner-local matched-control clock files merely to make them visible. #5970 intentionally removed that duplicate-state hazard."
  - "Do NOT re-mint or rewrite stock_desk's first general clock; it is durable evidence now."
artifacts:
  - research/EVAL_OS_RECOVERY_ARCHITECTURE_FREEZE_2026-08-27.md
  - research/EVAL_OS_SITREP_2026-08-14.md
  - research/EVAL_OS_P0A_HORIZON_CLOCK.md
  - research/PREREG_P0C1_DIRECTION_CORRECT_CONTROL_HITS.md
  - research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md
  - agentos/handoffs/EVAL-OS-E1-THEMATIC-COHORT-RECOVERY-2026-08-29.md
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
production lane. Current canonical main now contains a real `stock_desk` clock receipt with
`first_prospective_registration_utc=2026-08-29T11:08:11.609328+00:00`, and current qledger
`run_status.json` is a post-clock real grading run (`generated_at=2026-08-29T14:56:46.111593Z`,
264 grades that run). The stock general-clock sub-capability is therefore `PROVEN_LIVE`.

No current `thematic_desk.json` evidence-clock receipt exists. The authoritative nightly path was
observed executing through the existing basket/allocation/thematic-desk chain, so the remaining
question is downstream of generic scheduling: current US state may lawfully yield no thesis, a
proxy/scorability gate may refuse it, the model/parse/fail-soft path may suppress output, or a real
product/policy defect may exist. The successor must classify that branch before modifying anything.
It may never fabricate a thematic thesis merely to start a clock.

The old E1 child received terminal `SOL CLOSED / STOP` on Slack thread
`C0BSBM78V1N/1787896831.113919` at message `1788024583.456369`; its temporary watcher was ordered
disarmed. The parent Eval OS program remains active. A fresh recovery child is required for the
remaining thematic + cohort proof rather than silently moving the old worker/session.