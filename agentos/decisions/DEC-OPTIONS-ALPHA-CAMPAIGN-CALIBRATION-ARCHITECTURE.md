---
key: OPTIONS-ALPHA-CAMPAIGN-CALIBRATION-ARCHITECTURE
question: >
  How should Mastermind recover the dead Options Alpha Terminal surface into a
  genuinely useful intraday options signaling/research product without creating a
  second options truth plane, inventing an uncalibrated composite score, or
  laundering display context into directional/trading authority?
answer: >
  Use the canonical campaign + calibration architecture frozen in
  docs/superpowers/specs/2026-08-27-options-alpha-intelligence-recovery-design.md.
  Reuse the existing ThetaData/live-flow event plane, Flow ML population,
  options.signal_episode/v1, options.signal_campaign/v2, AD/ThetaData EOD spine,
  prospective outcome ledgers, and existing Options Issue Desk. Add missing measured
  trade+NBBO microstructure to the existing event/ML path; compose a regenerable
  zero-authority options.alpha_candidate_feed/v1 rather than a new lifecycle store;
  make the Terminal primary experience a live Research Candidate stream with exact
  clocks, evidence, contradictions, missingness, and healthy abstention/degraded
  states; keep the Terminal heuristic as Attention/Salience rather than probability;
  preserve the existing unsigned FS family; and require a separately preregistered,
  prospectively evaluated right-conditioned family before any bullish/bearish
  calibrated probability can even be considered for promotion. Existing DNR law is
  not amended by this decision: new positioning/GEX/OI fusion into an Options Alpha
  predictive score requires an explicit DNR scope adjudication before testing, and any
  trained calibrated probability requires a separate promotion review against current
  DNR:KILL-FUSED-COMPOSITE scope. Exact-option lifecycle/outcome work must extend the
  existing episode/Issue Desk owners and use exact NBBO rules. No implementation wave
  begins until the Chairman separately approves the written spec.
rationale: >
  The estate already contains most of the expensive foundations but they are not
  connected to the user outcome. At the action-time base, flow_signals.gate/v2
  records 69,041 durable live-flow events across 25 sessions while scoring remains
  disabled; the canonical options campaign checkpoint binds 5,263 episodes, 5,041
  campaign records and 17,136 outcomes with zero authority; AD-1T1 is production-
  proven at 0.9467 source coverage but AD-1 still lacks the AD-1T2 product-consumer
  proof; and Terminal Options Alpha still consumes options.prophet_shadow/v1, whose
  contract explicitly withholds probability, direction, contract and execution.
  Building another heuristic score or another campaign/store would discard this moat
  and violate one-canonical-system law. The selected architecture turns the existing
  evidence ledgers into an end-to-end learning/product loop while preserving the
  boundary between observation, salience, research candidate, calibrated statistical
  evidence, separately adjudicated signal authority, operator issue and trade. It
  preserves current DNR law rather than inferring new exceptions: no LLM origination,
  no generic fused composite, no new positioning fusion, no revival of the killed DOI,
  skew-deceleration or charm narratives, and no tick-rule Theta-tape authority.
alternatives:
  - option: Terminal-first heuristic fusion into one larger 0-100 Options Alpha score
    why_not: >
      Fast to render but creates another uncalibrated decision surface, duplicates
      upstream semantics, confuses salience with probability, and risks direct
      DNR:KILL-FUSED-COMPOSITE and DNR:KILL-POSITIONING-FUSION violations.
  - option: Make Prophet conditional fusion the only consumer of options intelligence
    why_not: >
      Prophet is a lawful future consumer under its own authority rules, but using it
      as the only destination shrinks Options Alpha into an equity-plan confirmer and
      fails the Chairman's standalone intraday options intelligence/product objective.
  - option: Build a new Options Alpha event/campaign/issue database optimized for the new UI
    why_not: >
      Duplicates the live-flow, episode, campaign, outcome and Issue Desk owners,
      fragments point-in-time evidence, and violates the one-canonical-system/no-
      duplicate-lifecycle law.
evidence:
  - "Chairman approved the OA-0 canonical campaign + calibration architecture and the exact experience/contract freeze in the active Sol session on 2026-08-27."
  - "config/mastermind_programs.yml: options-intelligence is the project upstream options-intelligence owner; options-alpha is the repository research-program owner; Terminal is the renderer/product host for terminal-options surfaces."
  - "data/flow_signals/gate.json at Macro action-time base ef6a099c86fa2f32d1f7e6a73c3cf284daffa3bc: n_rows=69041, n_sessions=25, scored=false, status=building_history."
  - "data/options_signal_campaign/checkpoint.json at the same base: episodes=5263, campaigns=5041, outcomes=17136, training_eligible=false, all authority booleans false."
  - "agentos/workstreams/WS-ADVANCED-DATA-OPTIONS.md: AD-1T1 PROVEN_LIVE, diagnostic source_coverage_pct=0.9467 >= 0.90, AD-1 remains BUILT_NOT_PROVEN and AD-1T2 is next."
  - "scripts/build_options_prophet.py and Terminal optionsAlphaTypes.ts: options.prophet_shadow/v1 is display-only and cannot invent score, probability, direction, contract or lifecycle."
  - "research/OPTIONS_ALPHA_FLOW_SCORE_AMENDMENT.md + scripts/ops_train_flow_score.py + config/flow_score.yml: FS-3 preregistered unsigned event-quality family exists; FS-4 implementation exists; scoring remains disabled pending FS-5."
  - "research/DO_NOT_REBUILD.md action-time read: DNR:KILL-LLM-ORIGINATION, DNR:KILL-FUSED-COMPOSITE, DNR:KILL-POSITIONING-FUSION, DNR:HOLD-THETA-TAPE, DNR:KILL-DOI-FAMILY, DNR:KILL-SKEW-DECELERATION, DNR:KILL-CHARM-NARRATIVES and DNR:KILL-OFFHORIZON-VERDICTS remain binding."
affects:
  - "WS:OPTIONS-ALPHA-INTELLIGENCE-RECOVERY"
  - "WS:ADVANCED-DATA-OPTIONS"
  - options-intelligence
  - options-alpha
  - "docs/superpowers/specs/2026-08-27-options-alpha-intelligence-recovery-design.md"
  - "data/flow_signals/*"
  - "data/options_signal_episode/*"
  - "data/options_signal_campaign/*"
  - "site/options_prophet/*"
  - "mastermind-terminal Options Alpha / Flow presentation paths"
confidence: high
reversibility: costly
decided_by: chairman-chris
decided_at: 2026-08-27
---

This decision freezes ownership and architecture only. It does not grant an
implementation carrier, model promotion, DNR exception, Terminal UI mutation,
scheduler change, Issue Desk issue, portfolio action, or brokerage authority.
