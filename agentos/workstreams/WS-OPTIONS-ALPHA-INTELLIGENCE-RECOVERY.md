---
key: OPTIONS-ALPHA-INTELLIGENCE-RECOVERY
title: Options Alpha — intraday options intelligence recovery
objective: >
  Recover Options Alpha from a display-only shadow/readiness surface into a live,
  point-in-time research-candidate and prospectively calibrated options intelligence
  product without creating a second collector, event/campaign lifecycle, score-control
  plane, or Issue Desk. Done = real untouched RTH options evidence flows through the
  canonical ThetaData/live-flow and existing episode/campaign owners into a deployed
  bilingual/mobile Terminal candidate workflow with exact clocks, healthy abstention and
  degraded states, prospective outcomes, separately earned statistical authority, and an
  exact-option operator-review path where evidence warrants it.
status: awaiting_review
program: options-intelligence
repos: [macro, terminal]
owner: ceo-sol
class: design
blast_radius: reversible
ambiguity: specified
waves:
  - id: OA-0
    title: Recovery archaeology + ownership/data/experience architecture freeze
    status: in_progress
    next_action: >
      Chairman reviews the written architecture spec on the single OA-0 records carrier.
      Until written-spec approval, do not create an implementation plan, commission Fable/
      Codex, mutate Terminal/Macro runtime, run a new scoring family, or arm any options lane.
  - id: OA-1T-MACRO
    title: Measured trade+NBBO microstructure on the canonical live event and Flow ML path
    status: todo
    depends_on: [OA-0]
    next_action: >
      CLOSED until the written spec is approved and a bounded implementation plan is
      accepted. Entrance gate must census live_flow.event_stage/v1 consumers before an
      additive event-shape change and must preserve the existing collector/event identity.
  - id: OA-1T-TERMINAL
    title: Render measured microstructure and separate Attention from probability
    status: todo
    depends_on: [OA-1T-MACRO]
    next_action: >
      CLOSED. At action time reconcile all open PRs touching the shared Flow resolver/stream,
      including Terminal PR #422 while open. Do not ship a second score semantics.
  - id: OA-1C-MACRO
    title: Derived options.alpha_candidate_feed/v1 research-candidate composer
    status: todo
    depends_on: [OA-1T-MACRO]
    next_action: >
      CLOSED. Requires written-spec approval, the OA-1T measured evidence path, a
      preregistered candidate-formation policy, and production-accepted AD-1T2 EOD consumer/
      availability evidence before settled EOD context can participate in candidate formation.
  - id: OA-1C-TERMINAL
    title: Live Options Alpha candidate stream, detail, abstention and degraded workflow
    status: todo
    depends_on: [OA-1C-MACRO, OA-1T-TERMINAL]
    next_action: >
      CLOSED. Reuse the current Options Alpha mount for the first vertical; do not widen into
      a navigation redesign before the real candidate path is production-proven useful.
  - id: OA-2
    title: Complete the existing FS-5 unsigned flow-event calibration gauntlet
    status: todo
    depends_on: [OA-1T-MACRO]
    next_action: >
      CLOSED. Preserve the existing unsigned target and preregistered population. Correctly
      populated event-time features are an entrance requirement; code existence is not
      promotion evidence.
  - id: OA-3
    title: Exact-option NBBO lifecycle and outcome contract under existing owners
    status: todo
    depends_on: [OA-1C-MACRO]
    next_action: >
      CLOSED. Must extend the existing episode/outcome/lifecycle owner with a new reviewed
      contract version; no mid, EOD, intrinsic or underlying-return substitute for missing NBBO.
  - id: OA-4
    title: Preregister and evaluate a separate right-conditioned directional family
    status: todo
    depends_on: [OA-2, OA-3]
    next_action: >
      CLOSED. The existing unsigned FS score may not be relabeled directional. Any bearish
      or bullish probability requires a new lawful prospective/OOS family and exact horizon.
  - id: OA-5
    title: Promoted signal to existing Options Issue Desk operator workflow
    status: todo
    depends_on: [OA-1C-TERMINAL, OA-4]
    next_action: >
      CLOSED. Reuse options.issue_desk/v1; do not create a parallel issue queue, trade manager,
      automatic portfolio authority or brokerage path.
decisions:
  - "DEC:OPTIONS-ALPHA-CAMPAIGN-CALIBRATION-ARCHITECTURE"
  - "DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA"
discoveries:
  - "DSC:OPTIONS-ALPHA-DEAD-UI-MASKS-LIVE-EVIDENCE-ESTATE"
landmines:
  - >
    The existing options.prophet_shadow/v1 surface is deliberately unable to invent score,
    probability, direction, contract or lifecycle. Do not call that producer broken and add
    authority inside it; the new candidate view is a separately reviewed derived contract.
  - >
    Do not treat the Terminal fixed-weight flowScore.ts heuristic as alpha probability. Its
    lawful role is Attention/Salience only; calibrated probability belongs to a governed Macro
    statistical family after promotion.
  - >
    No synthetic Chain Heat ask-share proxy (~buy=0.80/~sell=0.20/mixed=0.50) may enter Alpha
    training or calibrated candidate evidence as measured NBBO truth.
  - >
    AD-1T2 remains owned by WS:ADVANCED-DATA-OPTIONS. OA-1C depends on its production-accepted
    EOD consumer/availability result; do not duplicate AD-1T2 inside this workstream.
  - >
    Existing options.signal_episode/v1 and options.signal_campaign/v2 are canonical evidence
    owners. Preserve old rows and identities; do not fork them to simplify the new UI.
  - >
    Current DNR law remains binding: KILL-LLM-ORIGINATION, KILL-FUSED-COMPOSITE,
    KILL-POSITIONING-FUSION, HOLD-THETA-TAPE, KILL-DOI-FAMILY, KILL-SKEW-DECELERATION,
    KILL-CHARM-NARRATIVES and KILL-OFFHORIZON-VERDICTS.
do_not_redo:
  - "Another options collector, ThetaData Terminal instance, live-flow store, event identity, campaign ledger, outcome ledger, Issue Desk, rank/gate/sizing control plane, or generic Options super-score."
  - "Re-running stale MomoEdge research as activity; use the frozen benchmark and current product/source evidence."
  - "Reopening AD-1T1; it is PROVEN_LIVE and the next AD product wave is AD-1T2."
  - "Promoting FS-4 merely because trainer/scorer code exists or because missing features can be NaN-filled."
  - "Backfilling later-settled OI/NBBO into an earlier live decision as though it was knowable then."
artifacts:
  - docs/superpowers/specs/2026-08-27-options-alpha-intelligence-recovery-design.md
  - research/momoedge/MOMOEDGE_COMPLETION_BENCHMARK_PREREG_2026-08-11.md
  - research/FLOW_SIGNAL_ML_MASTERPLAN_BY_FABLE.md
  - research/OPTIONS_ALPHA_FLOW_SCORE_AMENDMENT.md
  - data/flow_signals/gate.json
  - data/options_signal_campaign/checkpoint.json
next_action: >
  Chairman reviews docs/superpowers/specs/2026-08-27-options-alpha-intelligence-recovery-design.md
  on the single OA-0 records carrier and either requests corrections or explicitly approves
  the written spec. Do not transition to implementation planning until that approval exists.
---

## Context

OA-0 was opened because the Terminal Options Alpha surface remained practically dead despite
substantial work across intraday flow, MomoEdge parity, Flow ML, options episodes/campaigns,
EOD options intelligence and Issue Desk infrastructure.

The recovered architecture found a convergence problem rather than a blank-slate problem:
substantial prospective evidence exists, but the primary UI still consumes a deliberately
weak shadow projection. The Chairman approved the campaign+calibration architecture and exact
experience/contract freeze in chat; the architectural workflow now requires review of the
written spec before implementation planning.

Operation key for this records carrier: `oa0-architecture-freeze-20260827-sol-001`.
