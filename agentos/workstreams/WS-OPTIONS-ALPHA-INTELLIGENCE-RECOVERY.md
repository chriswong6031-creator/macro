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
status: active
program: options-intelligence
repos: [macro, terminal]
owner: ceo-sol
class: design
blast_radius: reversible
ambiguity: specified
waves:
  - id: OA-0
    title: Recovery archaeology + ownership/data/experience architecture freeze
    status: done
    pr: 6573
    next_action: >
      ACCEPTED/MERGED 2026-08-27 as d84468e41f40f8dfb2404b2f51be557aade8f0ec
      after Chairman written-spec approval plus exact-head fences #14056 and CI #13809
      SUCCESS. Records/source law only; OA-0 armed no runtime, UI, model, signal or
      execution authority. Do not reopen OA-0 without a direct architecture/source-law
      contradiction or new Chairman ruling.
  - id: OA-1T-MACRO
    title: Measured trade+NBBO microstructure on the canonical live event and Flow ML path
    status: in_progress
    depends_on: [OA-0]
    pr: 6585
    next_action: >
      BUILT_NOT_PROVEN — natural-RTH production proof OWED. Implementation MERGED
      2026-08-30 as dbd654edb0fb47449b969b7dcb4fbafc2e0fe3ef (squash of carrier head
      77f400630d8a47402f0fd71a8c23eec3d6822356, 8 files +1284/-2, patch-identity proven
      byte-identical against the pre-merge blobs), under Sol conditional-adoption ruling
      #6585 comment 5459823114 after C3 gates A6 PASS / A2 SAFE_UNDER_FREEZE / A3 green
      + MERGEABLE / A4 scripts/** authority acknowledged. Status is NOT done: the capability
      moves BUILT_NOT_PROVEN -> PROVEN_LIVE only on a natural RTH session emitting a real
      measured event. Do NOT manufacture that proof — historical `--once --date` is
      explicitly forbidden as a proof path by the live-flow runbook. Consumer census is
      CLOSED, not owed: no current live_flow.event_stage/v1 consumer hard-enumerates nested
      event keys, so no v2 adjudication is required (both episode schemas carry zero
      additionalProperties:false; the poller/episode consumers read via .get() and their
      "strict" JSON loaders reject duplicate keys only). FS-4 remains frozen with
      scoring.enabled=false and the FS-5 kill switch intact; this wave armed no scoring,
      ranking or sizing authority. Two disclosed non-blocking defects carried forward for a
      separate bounded child, NOT repaired here: _coerce_int is not Infinity-safe on
      source_print_count/nbbo_valid_print_count (uncaught OverflowError can abort a harvest
      run), and vol_gt_oi_ratio is the one published measurement with no finite/rounding
      gate at the producer.
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
      CLOSED. Requires the OA-1T measured evidence path, a preregistered candidate-formation
      policy, and production-accepted AD-1T2 EOD consumer/availability evidence before settled
      EOD context can participate in candidate formation.
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
      CLOSED. Preserve the existing unsigned target and exact preregistered population;
      do not add new OI/GEX/positioning fusion features under this wave. Correctly populated
      event-time features are an entrance requirement and code existence is not promotion
      evidence. Any product-probability promotion must be separately reviewed against current
      DNR:KILL-FUSED-COMPOSITE scope; ambiguity requires explicit DNR adjudication, not inference.
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
      A family that would fuse OI/GEX/other positioning keys into a predictive score requires
      an explicit DNR:KILL-POSITIONING-FUSION scope ruling before the test begins.
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
    statistical family only after the statistical gate and current DNR authority review.
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
    KILL-CHARM-NARRATIVES and KILL-OFFHORIZON-VERDICTS. OA-0 created no implicit exception.
do_not_redo:
  - "Another options collector, ThetaData Terminal instance, live-flow store, event identity, campaign ledger, outcome ledger, Issue Desk, rank/gate/sizing control plane, or generic Options super-score."
  - "Re-running stale MomoEdge research as activity; use the frozen benchmark and current product/source evidence."
  - "Reopening AD-1T1; it is PROVEN_LIVE and the next AD product wave is AD-1T2."
  - "Promoting FS-4 merely because trainer/scorer code exists or because missing features can be NaN-filled."
  - "Backfilling later-settled OI/NBBO into an earlier live decision as though it was knowable then."
artifacts:
  - docs/superpowers/specs/2026-08-27-options-alpha-intelligence-recovery-design.md
  - docs/superpowers/plans/2026-08-27-oa1t-macro-measured-options-microstructure.md
  - research/momoedge/MOMOEDGE_COMPLETION_BENCHMARK_PREREG_2026-08-11.md
  - research/FLOW_SIGNAL_ML_MASTERPLAN_BY_FABLE.md
  - research/OPTIONS_ALPHA_FLOW_SCORE_AMENDMENT.md
  - data/flow_signals/gate.json
  - data/options_signal_campaign/checkpoint.json
next_action: >
  Review/land the OA-1T-Macro implementation-plan carrier, then choose one execution mode for
  that bounded wave. Recommended: subagent-driven/operator execution with one worker carrier,
  explicit pickup ACK before work, and a separate START receipt if a gate delays execution.
  OA-1T-Macro remains NOT STARTED until that commission is actually acknowledged; later OA waves
  remain closed.
---

## Context

OA-0 is accepted source law on Macro main as d84468e41f40f8dfb2404b2f51be557aade8f0ec.
The Chairman approved both the in-chat architecture and the written specification. OA-0's final
exact head passed fences #14056 and CI #13809 before merge.

The first bounded implementation plan now targets only measured ThetaData trade+NBBO truth on the
existing Macro live-flow/event-stage/Flow-ML path. It deliberately does not include Terminal UI,
research-candidate composition, model promotion, exact-option outcome lifecycle, or Issue Desk
integration. Those remain separately gated waves.
