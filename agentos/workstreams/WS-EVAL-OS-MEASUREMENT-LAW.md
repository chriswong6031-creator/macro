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
owner: Eval-OS session (COO Fable lane)
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - id: W1
    title: Architecture + metric validity
    status: done
    next_action: "None — PR #5471 merged (five docs + engine/qledger_validity.py V1/V2/V3 + guard + 16 tests)."
  - id: W2
    title: Horizon-clock contract + market ruler
    status: done
    next_action: "None — PRs #5559 then #5563 merged. #5563 fixed #5559's own shape_is_decisive defect."
  - id: W3
    title: Promotion legality
    status: done
    next_action: "None — #5519 (no pooled signed excess), #5573 (direction-correct control_only), #5572 (own-ruler grading <=63) merged."
  - id: W4
    title: Append-only law + forward-only accrual
    status: in_progress
    next_action: "Merge #5534, #5577 and the P0c-2 PR, then confirm the first nightly writes the evidence-clock files."
  - id: W5
    title: Control-leg decision
    status: todo
    next_action: "Await the CEO ruling in research/EVAL_OS_SITREP_2026-08-14.md §11; see DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG. (Wave status is `todo`, not `blocked` — the wave enum has no blocked state; the blocker is recorded in the workstream's own status and in the sitrep.)"
next_action: >
  Merge #5534, #5577 and the P0c-2 PR; then confirm the first nightly writes
  data/qledger/evidence_clock_start/<family>.json for stock_desk, thematic_desk and
  demand_chain, and record those three timestamps as the real evidence-clock start.
owns_paths:
  - engine/qledger.py
  - engine/qledger_validity.py
  - scripts/grade_qledger.py
  - research/EVAL_OS_*.md
  - research/PREREG_P0C1_*.md
discoveries:
  - DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG
landmines:
  - "engine/source_registry.py keeps its OWN _add_trading_days NYSE walker and grades narrative_source_call through its own exit. 'ONE resolver' is true only for claims that grade through qledger."
  - "source_registry's family hit_rate and scripts/report_importance_duel.py::_slice_stats both pool grade rows across clock bases. Single-basis TODAY (no explicit-clock grade row exists yet); the fuse is the first night new claims mature."
  - "A legacy-only family is promotable on the default path pre-P0c-2. _authority_clock_basis returns the sole basis when len(bases)==1, and for every live family today that basis IS CLOCK_LEGACY."
do_not_redo:
  - "Do NOT re-propose 'the horizon fix is a one-line in_scope_horizons change'. That was the 2026-08-12 diagnosis and it was wrong about the cause; the defect was the missing unit declaration. Superseded sitrep: PR #5512 (closed)."
  - "Do NOT register retrospective claims for stock_desk/thematic_desk/demand_chain. Branch claude/eval-os-t9-adoption tried it and was refused by 3/3 adversarial reviewers: rows were anchored and priced 1-4 completed sessions in the past."
  - "Do NOT add a `backfilled` provenance flag as a compromise. Nothing reads it (blocker B3); a mixed store with a decorative flag is worse than a small honest one."
  - "Do NOT extend GRADE_HORIZONS above 63 (LH-U6). P0b adds the OWN ruler only when <=63; >63 stays on the [5,21,63] ladder."
  - "Do NOT re-derive a claim's market from ticker shape alone, or from provenance alone. Five rounds each failed that way; the rule is hard-fact-wins / inference-must-agree / silent-shape-lets-provenance-decide."
artifacts:
  - research/EVAL_OS_SITREP_2026-08-14.md
  - research/EVAL_OS_P0A_HORIZON_CLOCK.md
  - research/PREREG_P0C1_DIRECTION_CORRECT_CONTROL_HITS.md
---

## Scope note

This workstream owns the **measurement law** — what a number means and whether it may be
published — not the engines that produce claims. Registering a new desk is in scope only
insofar as it must be forward-only and must declare a real ruler.

T1 (the 378-engine derived registry) is a **sibling** task, parked with its own cold-start
handoff at `research/EVAL_OS_T1_CONTINUATION_HANDOFF_2026-08-12.md`. It was deliberately
not restarted in this wave.
