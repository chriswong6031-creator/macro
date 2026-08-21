---
key: STAGE-TARGET-WEEK-IS-THE-POPULATION-MODE
question: >
  When the benchmark's completed Stage week and the classified population's modal
  completed Stage week disagree, which one anchors the current cross-section?
answer: >
  The POPULATION's modal completed week, in both divergence directions. SPY remains
  REQUIRED as a corroborating benchmark — an unclassifiable SPY still yields
  `(None, "unresolved")` and no current cross-sectional authority — but it never
  overrides the mode. Divergence either way emits
  `::warning title=stage-target-week::` and adds a `benchmark_week_divergence` issue
  to the population receipt, with both `spy_stage_week` and `population_modal_week`
  recorded so the resolution is auditable.
rationale: >
  The first draft specified `target = min(spy_stage_week, population_modal_week)`,
  justified ONLY by the benchmark-ahead case: `data/yahoo/SPY.parquet` and
  `data/baskets/ohlcv/` are different stores on different collectors, so a one-day
  drift across a Friday flips SPY into a new completed week while the universe sits
  on the prior one, and a SPY-only rule would mark a perfectly valid cross-section
  wholly stale. Adversarial review proved the cap is TWO-SIDED and inverts when the
  BENCHMARK is the store that freezes: SPY stuck at 2026-06-26 while 2,600 names
  classify to 2026-08-14 makes `min()` pick June, so `stage_current` becomes True for
  the ~100 genuinely stale June rows and False for the 2,600 current ones. Counts,
  weather, `top_stage2`, the change feed and `data_session` then all recompute from
  the June rows, and `append_stage_snapshot` stamps those rows `stage_current=True`
  into the machine snapshot — where the §4.2 consumer gate PASSES them. The wave's
  stated goal, achieved exactly in reverse, behind nothing louder than a coverage
  warning. This is not hypothetical: DSC:STAGE-STALE-NAMES-ARE-FETCH-UNIVERSE-DRIFT
  records that single-store freezes are the norm in this repo. Worked through both
  directions, the modal week is correct in each — `min()` was right in the
  benchmark-ahead case only because `modal < spy` there. A stale benchmark degrades
  Mansfield RS (each name's RS is computed on its own weekly grid with the benchmark
  reindexed and forward-filled), but RS is one scoring input among several and the
  stage classification itself — price versus the 30-week MA — does not depend on SPY
  at all. Degrading one input with a loud warning beats inverting the population.
alternatives:
  - option: "min(spy_stage_week, population_modal_week) — the original spec"
    why_not: >
      Two-sided: inverts the entire population whenever the benchmark store is the
      one that freezes, and stamps genuinely stale rows as current into the machine
      snapshot. Its rationale only ever covered the benchmark-ahead direction.
  - option: "SPY's completed week alone, as the handoff first proposed"
    why_not: >
      A benign one-day cross-store drift across a Friday marks the whole population
      stale and blacks out a market read that is genuinely comparable, because each
      name's RS is computed on its own weekly grid against a forward-filled benchmark.
  - option: "Population mode alone, dropping the SPY requirement"
    why_not: >
      Loses the independent check on what week the market is actually in: if the
      WHOLE store froze together, the mode would be an old week and nothing would
      contradict it. SPY's classification is also our proof that the classifier and
      benchmark store work at all.
  - option: "A coverage threshold that switches anchors above/below some percentage"
    why_not: >
      Reintroduces an arbitrary tunable on the very axis the wave is trying to make
      non-arbitrary, and would need re-justifying every time the universe changes.
evidence:
  - "PR #6156, commit d54bc766b402 (`engine/stage_analysis.py::_resolve_target_stage_week_detail`)"
  - "research/STAGE_OBSERVATION_TRUTH_WAVE8.md §1.2 (supersedes its own earlier min() draft, with the inversion worked out)"
  - "Adversarial review executed the frozen-SPY resolver: returned target_stage_week 2026-06-26 against population_modal_week 2026-08-14"
  - "tests/test_stage_analysis.py::test_target_week_resolver_does_not_invert_when_benchmark_lags — the regression pin"
  - "Verified against the real completed-week rule: tapes ending Thu Aug 20 / Wed Aug 19 / Mon Aug 17 / Fri Aug 14 all resolve to 2026-08-14; Fri Aug 21 resolves to 2026-08-21 (the skew case)"
  - "Production run: target 2026-08-14, source spy_benchmark, 2,562 current / 179 stale / 0 unknown, coverage 93.5%"
affects:
  - macro
  - engine/stage_analysis.py
  - engine/stage_industry.py
  - engine/marketing/attention_source.py
confidence: high
reversibility: easy
decided_by: "session claude/stage-observation-truth"
decided_at: 2026-08-20
---

# The Stage target week is the population's mode, never capped at the benchmark

Both candidate weeks come from the single canonical completed-week rule
(`engine.cycles._w_fri_completed`), so this remains ONE Stage calendar and involves
no threshold or day-count. Currentness is completed-week EQUALITY:
`stage_current = (stage_week_end == target_stage_week)`, tri-valued so an unprovable
week is `unknown` rather than assumed current.
