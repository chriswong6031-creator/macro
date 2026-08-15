---
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: us-prophet-fusion-canonical (worktree us-prophet-fusion-canonical-b2191b, branch claude/us-prophet-fusion-canonical)
model: fable
ended_because: complete
prs: ["#5593", "#5602", "#5604", "#5667", "#5700"]
mission: >
  Handoff A / wave w2b — implement the 2026-08-15 Chairman override: replace
  us_prophet_v2 as the canonical US board ranker with the deterministic C1
  evidence-family fusion, retire the exact current v2 scorer into a zero-authority
  shadow that keeps forward-grading, implement the as-of-night presence/variance
  evaluation #5700 left unfinished, and produce a deterministic before/after board
  comparison as the operator acceptance surface. One PR, 4h ceiling, no C2 fitting.
state_before: >
  PR-2 (#5700) merged; C2 refused (refused_no_lawful_folds, zero fitted coefficients,
  67 graded dates short). Live board ranked by us_prophet_v2's five-leg weighted
  heuristic. The WS objective and scope boundary both committed the live rank path to
  the w7 promotion gate. The variance floor was registered in families.yml with its
  as-of-night form explicitly UNIMPLEMENTED and carried to PR-3.
changed:
  - path: engine/us_prophet_fusion.py
    what: "NEW (~600 lines). The C1 construction extracted from
      scripts/prophet_fusion_race.build_c1 into a production module: registered signs
      ported verbatim, oriented values, percentile_rank (pandas rank(pct, average)
      semantics, pure Python, no pandas), admit_members (BOTH floors, frame-parametric),
      aggregate (the C1 arithmetic incl. within-family duplicate collapse and family
      abstention), extract_members (live board row -> members, mirroring
      grade_us_board._row_features), fuse_board (as-of-night entry point). Imports
      nothing from scripts/ or research/ — pinned by a test."
  - path: engine/us_board_rank.py
    what: "BOARD_DEFINITION us_prophet_v2 -> us_prophet_v3 with the displaced stamp
      appended in the same change; SHADOW_DEFINITION + FALLBACK_DEFINITION;
      legacy_v2_values() = the frozen five-leg arithmetic extracted verbatim;
      score_rows builds the fusion plane once per pool, publishes prophet.score as the
      fusion priority with a glass-box prophet.fusion receipt, stamps prophet_shadow on
      every row with its own score_rank, and sorts (stage_rank, scored-first,
      -score, ticker); published_definition() reads the definition off the ROWS;
      fusion_ranking_receipt() + fusion_floors out-parameter; ranking_block defaults its
      definition from the rows and publishes score_kind = FUSION_SCORE_KIND;
      component_coverage follows the legs onto the shadow; is_us_definition()."
  - path: scripts/build_stock_library.py
    what: "passes fusion_floors, stamps rank_by/board_definition/candidate-pool/context-
      vector from published_definition() rather than the constant, logs the fusion
      receipt, and raises a ::warning on a degraded night. Stale us_prophet_v1 literals
      removed."
  - path: scripts/us_prophet_fusion_compare.py
    what: "NEW. The acceptance surface: old vs new top-30 over the committed board with
      rank deltas, promoted/demoted, stage, entry status, family contributions, old v2
      score/rank and a plain-English why-moved per row — plus a family-SEPARATION table
      and a hard freeze check (refuses if the frozen v2 does not reproduce the
      published scores)."
  - path: research/prophet_fusion/FUSION_BOARD_COMPARISON.md + fusion_board_comparison.json
    what: "the generated comparison over the 2026-08-13 board (69 buy rows), committed"
  - path: research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md
    what: "§18 — the override, what it supersedes (quoted, not deleted), what did NOT
      change and why, the prospective floor derivation, §18.5 honest limits, degradation
      semantics, and what w3-w7 become"
  - path: engine/prophet_bridge.py, engine/stock_desk.py, engine/prophet_miss_audit.py,
      engine/us_prophet_grades.py, engine/hk_board_rank.py
    what: "stale us_prophet_v1/v2 literals removed from the ordering-authority prose;
      every consumer already read the FIELD (prophet.score) or the artifact's rank_by,
      so the authority transferred with no logic change"
  - path: tests/test_us_prophet_fusion.py
    what: "NEW, 62 tests across the four claims (port is an extraction / inputs are the
      same inputs / the freeze held / the shadow has no authority)"
  - path: tests/test_us_board_rank.py, tests/test_grade_us_board.py,
      tests/test_us_reclaim_waiver_prophet_v2.py
    what: "v2-leg assertions repointed at prophet_shadow; era fixtures read the live
      stamp from the producer; the score-scope contract extended to bind the canonical
      column; the shelf-invariance tests exclude only prophet_shadow.score_rank"
  - path: .github/ci/legacy-jobs.yml
    what: "the new suite rides the step that already owns engine/us_board_rank.py"
  - path: agentos (DEC:PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER, WS record, this handoff)
    what: "the dated authority change; WS objective/scope-boundary superseded clauses
      preserved as record; 4 new do_not_redo entries"
verified:
  - claim: the ported aggregation IS the raced C1, per row
    command: pytest tests/test_us_prophet_fusion.py::TestByteParityWithTheRacedC1
    result: "over the frozen 24-date / 2,251-row research frame: family scores agree to
      <1e-12, C1 scores to <1e-10 on the x100 scale, null-for-null agreement, identical
      admitted-member set, identical dropped set, identical families_present"
  - claim: the frozen v2 scorer reproduces what the board actually published
    command: pytest tests/test_us_prophet_fusion.py::TestLegacyV2ByteParity;
      python3 scripts/us_prophet_fusion_compare.py
    result: "69/69 rows of the 2026-08-13 board reproduced to 1e-9; the compare script
      RAISES ReplayMismatch rather than printing a comparison if any row drifts"
  - claim: the as-of-night floors change the answer vs the whole-frame ones
    command: fus.admit_members over the live buy pool vs over the frozen frame
    result: "live: 7/8 members vote, F1/F2/F4/F5/F8 active, gex_confirm_verdict dropped
      on presence 0.464. Frozen frame: 6 members, F1 ABSENT (tier_cascade 0.25 vs ~1.00
      live). Same code, same thresholds, different frame."
  - claim: the shadow has zero authority, operationally
    command: pytest tests/test_us_prophet_fusion.py::TestTheShadowHasNoAuthority
    result: "deleting prophet_shadow from every row leaves the scored output byte-
      identical (order, scores, featured flags, stages); the shadow's own rank differs
      from the board order on the fixture, so the test is not vacuous"
  - claim: a degraded night cannot wear the canonical stamp
    command: pytest tests/test_us_prophet_fusion.py::TestDegradationIsStampedNotHidden
    result: "a refused plane stamps us_prophet_v2_fallback on every row, publishes the
      cause, omits the fusion block, omits prophet_shadow (the retired scorer IS the
      published ranker that night), and published_definition()/ranking_block() both
      follow the rows; a mixed pool raises"
  - claim: sibling boards are untouched
    command: pytest tests/test_hk_board_rank.py tests/test_hk_board_ui.py; the sibling
      class in the new suite
    result: "298 passed; hk_prophet_v1 gets the retired arithmetic as its published
      score, no fusion block, no shadow, its own score_kind and definition"
  - claim: the suites green over the branch
    command: pytest test_us_board_rank / test_us_prophet_fusion / test_grade_us_board /
      test_us_candidate_lanes / test_us_context_vector / test_gate_reasons_exhaustive /
      test_us_reclaim_waiver_prophet_v2 / test_prophet_bridge / test_stock_desk /
      test_prophet_outage_backfill / test_prophet_miss_audit / test_us_board_priority_ui
      / test_us_board_lanes; agentos validate; audit_unrun_tests; run_ci_pack validate
    result: "386 + 269 + 350 + 298 passed; agentos 0 errors; audit_unrun_tests P0-P3 all
      0; 194 pack jobs validate"
unverified:
  - claim: the first post-merge nightly publishes rank_by=us_prophet_v3 with a fusion
      receipt and no degradation stamp
    what_would_verify: "first completed daily.yml on a post-merge head: site/factordata/
      us_standouts.json carries rank_by us_prophet_v3, ranking.fusion.families_active
      non-empty, ranking.fusion.floors.captured true, no ::warning
      us-board-fusion-degraded in the run log, and every buy row carrying both
      prophet.fusion and prophet_shadow. NOT observable at handoff time — the engine job
      runs hours and recovery etiquette forbids dispatching it by hand."
  - claim: the comparison holds on a pool whose composition differs materially from
      2026-08-13's
    what_would_verify: "re-run scripts/us_prophet_fusion_compare.py after the first
      fusion-ranked nightly; the committed artifact is one board, and the family
      separation table in particular is a property of that night's coverage"
unresolved:
  - "SHADOW STORE GRAIN — a deliberate, named deviation from the commissioning. The brief
    asked for the shadow's forward outcomes to be kept distinct via the candidates
    store's board_definition key. That store's append_candidates() contract requires the
    COMPLETE verdict map (its whole value is that ineligible names are present too), so a
    second definition means duplicating ~2,900 rows and ~200 context columns per night to
    vary two numbers. What shipped instead: ONE row per name, and the shadow's score and
    rank stamped on the board row as prophet_shadow (naming us_prophet_v2_shadow), so the
    forward race is a join of the SAME ticker-level graded outcomes against two rank
    columns. No second grader and no duplicate control plane, which is the constraint the
    brief actually names — but the shadow's outcomes are not separately KEYED by
    board_definition. Flagged for adjudication; reversible by stamping the second
    definition if the store cost is acceptable."
  - "F8 handed 99% of rows and F4 97% of rows an IDENTICAL contribution on the first live
    pool, so five active families is not five independent votes — today's ordering work
    is mostly F2, then F1 and F5. This is REGISTERED behaviour (a sparse-but-variable
    event flag is meant to pass the variance floor) and is published in the comparison's
    separation table every run. It must NOT be answered by re-tuning the floor."
  - "insider_cluster remains serving-dead (collector stopped at 2026q1); it is stood down
    by the variance floor on any night it is constant rather than pre-excluded"
  - "(inherited) the §13.0 live closure; the short_int knowable-lag reconciliation
    (task_a85de1cd); sue_z re-home; PR-1a advisories A3/A4/A5/A7"
next_actions:
  - "Verify the first post-merge nightly (see unverified) — the single open item"
  - "w3 re-cut: the shadow lane's prereg now instruments a race whose CHAMPION side is
    stamped nightly by production. Re-cut it against prophet_shadow rather than a
    replayed G0, and register the F8/F4 near-constancy question as a REGISTRY decision"
  - "C2 re-enters when the fold law is satisfiable: 91 graded dates needed, 67 more than
    held. Unchanged by this PR."
  - "First us_prophet_v3 H=10 grade matures ~10 sessions after the first fusion night"
do_not_redo:
  - "Do not re-litigate C1's adoption against the w7 gate — DEC:PROPHET-FUSION-IS-THE-
    CANONICAL-US-RANKER settled it 2026-08-15. The gate still governs C2-C5."
  - "Do not bump SELECTION_ERA for a ranking change (it names the SELECTION regime;
    bumping restarts the H=63 episode clock its own revision ruling protects)"
  - "Do not re-tune the variance floor against an observed ordering — feature-only law,
    and the sparse-but-variable pass is its registered acceptance test"
  - "Do not let a degraded night publish under us_prophet_v3, and do not read the board
    definition from the module constant anywhere downstream — published_definition()"
  - "Do not import scripts/ or research/ from engine/us_prophet_fusion.py — the parity
    test imports the race harness, production never does"
  - "(inherited) PR-0/PR-1a/PR-1b/PR-2 do_not_redo lists remain binding"
danger_areas:
  - "score_rows is SHARED with hk_board_rank. Every fusion path is gated on
    definition == BOARD_DEFINITION; a change that widens that gate silently re-ranks HK."
  - "The five legs moved to prophet_shadow. Anything reading prophet.components or
    prophet.points on a US row now reads a block that no longer exists — component_coverage
    was the first casualty and would have reported every leg dead on every fusion night,
    which is the exact shape of a real extension outage."
  - "extract_members must track grade_us_board._row_features. A drift there is invisible
    to every parity test: the arithmetic stays exact while the inputs come from somewhere
    else. TestExtractionMirrorsTheGradedFrame is the only thing holding them together."
  - "The variance floor's denominator excludes dates that cannot carry variation. Remove
    that and a one-name board refuses its own plane and publishes a fabricated outage."
---

Cold-stranger summary: the US board is now ordered by the C1 evidence-family fusion
(`us_prophet_v3`) instead of the five-leg priority heuristic, by Chairman override rather
than by winning the arena — the override's basis is that C1 is unfitted, glass-box, and
order-only, not that it beat the champion on outcomes, and every published surface says
so. The construction was not re-derived: it was extracted from the frozen race and pinned
byte-for-byte against it, and the retired scorer was extracted the same way and pinned
against 69 scores the board actually published. The one genuinely new piece of
engineering is the as-of-night floor evaluation that #5700 left unfinished, and it earns
its place immediately — the live buy pool admits `tier_cascade` (F1 votes) where the
frozen 24-date frame does not. The retired champion keeps running as a zero-authority
shadow so the forward race has a champion side from night one. The honest limit to carry
forward: five active families is not five independent votes — F8 and F4 handed ~all rows
the same number on the first live pool, so F2/F1/F5 are doing the ordering, and that is a
registry question for w3, never a reason to re-tune the floor.

*Supersedes `PROPHET-CONDITIONAL-FUSION-2026-08-15.md` as the latest record for this
workstream without altering it; that file remains the PR-2 account.*
