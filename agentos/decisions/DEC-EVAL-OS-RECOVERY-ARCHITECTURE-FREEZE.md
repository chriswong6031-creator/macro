---
key: EVAL-OS-RECOVERY-ARCHITECTURE-FREEZE
question: >
  After reconciling stale Eval OS records against current Agent OS, GitHub, Linear, Slack,
  qledger production evidence and the current Personal-Pro Executive transport state, what is
  the one completion architecture and which prior unresolveds are actually still unresolved?
answer: >
  Preserve the original thin joining-layer architecture: T1 is the only engine registry;
  qledger and owner-native ledgers remain the canonical scored-record substrates; existing
  gauntlet/species/qual-ladder owners remain promotion authority; T4 is a pure derived health
  view over T1+Synapse+existing evidence providers; T7/T8 extend the existing read-only admin
  Intelligence OS surface; T12 may derive a required evidence tier but Agent OS remains the
  router. No second engine registry, score store, health monitor/store, promotion service,
  clock database, Prophet evaluation ledger, replay framework, contradiction detector, rubric
  or work queue may be created. Reconcile the stale control-leg blocker as RESOLVED by P0d:
  benchmark is universal baseline; matched control is required only for governed families with
  a defensible counterfactual (currently stock_desk and demand_chain), while thematic_desk is
  benchmark-only. The critical first gaps are real stock/thematic forward clock starts, stock
  matched-control clock start/current demand control-clock host verification, T4 deployed proof,
  unified promotion/clock-laundering adversarial acceptance and T7/T8. The complete program also
  retains explicit T0-T12 closure obligations: T2 Prophet benchmark/MFE/MAE is not built under
  the old contract, T5 taxonomy is not built, T6 has only one pre-existing benchmark case,
  T3/T9 remain partial, and T10/T11/T12 remain unbuilt unless a current canonical owner is
  explicitly proven to satisfy/supersede the old capability.
rationale: >
  Current main proves substantial substrate landed after the 2026-08-14 handoffs: T1 was later
  reconciled done; #5534/#5577/#5584 already merged; P0d/#5609 and #5665/#5672 resolved control
  law; T4 merged as #5721 after adversarial repair; qledger is actively grading real claims.
  But only demand_chain has a tracked general forward evidence-clock start, its historical
  runner control-clock receipt is the only proved matched-control clock, metric-validity is
  still warn-tier by default, T4 lacks accepted production-browser proof, T7/T8/T12 remain
  plan-only, current prophet.ledger/v1 lacks the old T2 benchmark/excess/MFE/MAE fields, the T5
  failure vocabulary is spec-only, and no 20-case golden library exists. Calling the program
  complete would therefore confuse merged infrastructure and neighboring programs with governed
  real use. The freeze keeps one canonical system, makes natural-time measurement/health proof
  first, and requires every original T0-T12 capability to receive an explicit terminal evidence
  disposition rather than disappear by architectural drift.
alternatives:
  - option: resume the old W4/W5/T4 branch next-actions literally
    why_not: >
      They are stale. The named PRs merged, the old T4 branch is gone, T4 merged through #5721,
      and the control policy received a later explicit CEO ruling and implementation.
  - option: create a new Eval OS score/health/promotion database to unify everything
    why_not: >
      This would be the seventh evaluation/control plane the original architecture explicitly
      forbids and would duplicate qledger, T1, T4 and existing promotion owners.
  - option: blindly implement the old T2/T5/T6 file lists now
    why_not: >
      Prophet, Metabolism and Neural-Web architectures evolved after the plan. The original
      capability remains owed, but current owner archaeology must determine whether to extend a
      newer canonical owner or record an evidence-backed replacement; old implementation shape
      has no authority to create a parallel ledger/replay/taxonomy plane.
  - option: mark the program done because current qledger is actively grading and T4 merged
    why_not: >
      Real focal desk clocks are incomplete, T4 is not production-proven, illegal-promotion
      acceptance is not unified, the L4 human answer layer is not built, and multiple original
      T0-T12 capabilities remain partial or not built.
evidence:
  - "Protected Sol Skillpack pin: mastermindx-market-intelligence/Mastermind@d508e30c865bd2425bb551650b71381b7eb6d4f8."
  - "Macro recovery base: d84468e41f40f8dfb2404b2f51be557aade8f0ec."
  - "T1 #5620 / d13259abc51c; lifecycle closeout #6392 / MAS-131."
  - "T4 #5721 / a77d874a1c23c7e4e2db0000db75164fcc56bcc2; old claude/eval-os-t4-output-health ref no longer exists."
  - "demand_chain general evidence clock: 2026-08-19T08:10:37.995754+00:00; 126 trading days."
  - "demand_chain historical matched-control clock: 2026-08-19T08:10:37.332100+00:00; control XLU; #5970 intentionally made control clock runner-local/untracked."
  - "2026-08-27 qledger run_status: 1,250 grades in run; zero promotion-ready families; radar@21d approaching."
  - "Current metric-validity CLI documents WARN-tier default; --strict remains an explicit mode."
  - "Current prophet.ledger/v1 header and schema contain no benchmark/sector excess, MFE or MAE fields required by old T2."
  - "engine/neuralweb/eval contains one benchmark case; data/golden_cases does not exist."
  - "Current #sol-runtime contains the Executive Relay bot but no MMX/SOL_STATE_V1 frame, so current Executive lifecycle/admission truth is not readable from Personal-Pro."
affects:
  - "WS:EVAL-OS-MEASUREMENT-LAW"
  - "WS:EVAL-OS-OUTPUT-HEALTH"
  - "WS:EVAL-OS-T1-ENGINE-REGISTRY"
  - qualitative-intelligence
  - engine/qledger.py
  - engine/intelligence_registry.py
  - engine/output_health.py
  - admin/intelligence_os.py
  - data/prophet/ledger.jsonl
  - engine/neuralweb/eval
confidence: high
reversibility: hard
supersedes:
  - "WS:EVAL-OS-MEASUREMENT-LAW stale W4 next-action merge list"
  - "WS:EVAL-OS-MEASUREMENT-LAW stale W5 unresolved-control-ruling blocker"
  - "WS:EVAL-OS-OUTPUT-HEALTH stale old-branch/PR next action"
  - "Any inference that unmentioned original T0-T12 items became complete merely because newer neighboring programs landed"
decided_by: ceo-sol
decided_at: 2026-08-27
---

Full capability ledger, no-rebuild boundaries, `PROVEN_LIVE` law and bounded continuation waves
are frozen in `research/EVAL_OS_RECOVERY_ARCHITECTURE_FREEZE_2026-08-27.md`.
