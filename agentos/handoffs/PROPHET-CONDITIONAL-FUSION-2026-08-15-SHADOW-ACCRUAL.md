---
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: us-shadow-leg-accrual (worktree modest-meitner-f3d726, branch claude/us-shadow-leg-accrual)
model: fable
ended_because: complete
prs: ["#5769"]
mission: >
  Close the second half of the reader gap the override's own handoff flagged in its
  danger_areas: the two US consumers still reading the five v2 legs off `prophet` after
  #5753 moved them to `prophet_shadow`. Decide — as a design call for the workstream —
  whether to leave the store's ten `prophet_*` leg columns null on a fusion board or to
  accrue the retired scorer under its own name, then ship the US-side test that would
  have caught it.
state_before: >
  #5753 merged. `component_coverage` had been repointed onto the shadow in that PR (the
  "first casualty" its handoff names), but `engine/us_context_vector.py` and
  `engine/us_candidate_lanes.py` had not. Result, measured rather than inferred: from
  the first fusion night all ten `prophet_{leg}` / `_{leg}_points` columns in
  data/us_prophet_rank/candidates read null on every US row, and the candidate-pool row
  published `components: {}` / `points: {}`. Silent — `_finite(None)` returns None so
  nothing raised, and no US test pinned the columns (every `prophet_signal` assertion in
  tests/ is China-side).
changed:
  - path: engine/us_context_vector.py
    what: "NEW `SHADOW_COLUMNS` family (13 columns): prophet_shadow_definition,
      prophet_shadow_score, prophet_shadow_score_rank, and prophet_shadow_{leg} /
      _{leg}_points for the five SCORE_COMPONENTS. Read off the board row's
      `prophet_shadow` block, stamped on EVERY record present-or-null, same law as
      POOL_COLUMNS/HUB_COLUMNS. The canonical `prophet_*` columns are UNCHANGED and stay
      null on a v3 row by design. prophet_shadow_definition registered in
      _OBJECT_COLUMNS (text column, null on every off-board row and every degraded
      night)."
  - path: engine/us_candidate_lanes.py
    what: "_pool_row carries a sibling `prophet_shadow` block (version, score,
      score_rank, components, points), display/forward-grading only, null when the board
      row has no shadow. The existing `prophet` block's keys and types are untouched;
      its comment, which claimed the canonical block carries the legs, was corrected."
  - path: tests/test_us_context_vector.py
    what: "NEW TestTheRetiredScorerAccruesUnderItsOwnName (6 tests) — builds a real v3
      board through us_board_rank.score_rows and reads the definition back with
      published_definition(). Pins: canonical legs null on a fusion row; shadow legs
      read off the shadow block; a genuinely measured 0.0 surviving as 0.0 while an
      off-board row stays null; a degraded night publishing the legs and carrying no
      shadow; the whole family on every row. Imports the fusion suite's `_row` helper
      rather than mirroring it."
  - path: tests/test_us_candidate_lanes.py
    what: "NEW TestTheRetiredScorerRidesAlongWithNoAuthority (3 tests) — shadow block
      present on a v3 board row, null (not an empty block) without one, and copied
      rather than aliased."
  - path: agentos
    what: "DEC:US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY,
      DSC:CHAMPION-BASELINE-COLUMNS-CARRY-THE-CHALLENGER, this handoff"
verified:
  - claim: the gap is real and reaches the store, through the production path
    command: "engine.us_board_rank.score_rows over a fusion pool ->
      us_context_vector.build_records"
    result: "published_definition = us_prophet_v3; prophet.components = None; store
      prophet_signal..prophet_quality_points = None x10; prophet_shadow.components =
      {'signal':1.0,'entry':1.0,'edge':0.0,'runway':0.75,'quality':0.0}, score 62.5,
      score_rank 3"
  - claim: the champion baseline is repointed, not merely thinned
    command: same run, reading the four families.yml `champion_baseline` non-leg columns
    result: "store prophet_score = 81.7 (the FUSION score), score_rank = 1.0, featured =
      True on a row the retired scorer scored 62.5 and ranked 3rd. See
      DSC:CHAMPION-BASELINE-COLUMNS-CARRY-THE-CHALLENGER."
  - claim: the degraded path was already correct and stays correct
    command: "score_rows with us_prophet_fusion.fuse_board patched to raise"
    result: "published_definition = us_prophet_v2_fallback; prophet.components
      populated; prophet_shadow absent from the row; store prophet_signal = 1.0 /
      prophet_signal_points = 30.0; every prophet_shadow_* column null"
  - claim: the new test would have caught this
    command: "restore engine/us_context_vector.py + engine/us_candidate_lanes.py from
      HEAD, keep the tests, pytest the two new classes"
    result: "7 failed, 2 passed. The 2 that pass both ways are the fixture premise check
      and the pin on the null state being PRESERVED — flagged, not hidden."
  - claim: the suites are green on the tree CI actually uses
    command: "python3 scripts/worktree_sparse.py add site / add data, then pytest
      test_us_context_vector, test_us_candidate_lanes, test_us_prophet_fusion,
      test_us_board_rank, test_us_context_vector_payload_containment,
      test_prophet_fusion_families, test_us_prophet_grades"
    result: "685 passed, 0 failed, 0 errors. The SAME suites read 1 failed / 16 errors
      in the sparse worktree and every one of those was a sparse artifact — do not
      believe a red in a sparse tree without materializing first."
  - claim: the new cross-suite import does not break exclusive-scope curation
    command: pytest tests/test_ci_pack.py
    result: "85 passed. The import extends test_us_context_vector.py's static import
      closure, which is exactly what that guard walks."
  - claim: repo guards clean
    command: "check_template_site_sync; check_validated_claims; check_blocklist_drift"
    result: "88 pairs OK; every affirmative 'validated' claim backed; no drift"
unverified:
  - claim: the first post-merge nightly stamps the thirteen shadow columns non-null on
      the buy lane
    what_would_verify: "after the next completed daily.yml on a post-merge head, read
      data/us_prophet_rank/candidates/2026-08.parquet through
      us_context_vector.load_candidates and confirm prophet_shadow_definition =
      us_prophet_v2_shadow with a non-null prophet_shadow_score_rank on the buy-lane
      rows, and every prophet_shadow_* null off it. NOT observable at handoff time —
      the store is written by the nightly lane only (COLLECT_LANE=nightly) and recovery
      etiquette forbids dispatching daily.yml by hand."
  - claim: (inherited, still open) the first post-merge nightly publishes
      rank_by=us_prophet_v3 with a fusion receipt and no degradation stamp
    what_would_verify: "see PROPHET-CONDITIONAL-FUSION-2026-08-15-OVERRIDE.md — the
      single open item that handoff carried, unchanged by this PR"
unresolved:
  - "families.yml `champion_baseline` still names prophet_score / score_rank /
    display_rank / featured as the champion's output while a v3 row carries the
    challenger's numbers there. NOT fixed here on purpose — families.yml is a sibling
    builder's deliverable, is the arena law, and is test-pinned. It belongs to the w3
    re-cut, which is the wave that will actually read those columns.
    DSC:CHAMPION-BASELINE-COLUMNS-CARRY-THE-CHALLENGER."
  - "(carried from the OVERRIDE handoff) SHADOW STORE GRAIN — the shadow's outcomes are
    still not separately KEYED by board_definition; this PR gives the join its second
    rank column but does not reopen the grain question, which was weighed and declined
    on store cost. Still flagged for adjudication."
  - "(carried) F8 handed 99% of rows and F4 97% an IDENTICAL contribution on the first
    live pool — five active families is not five independent votes, today's ordering is
    mostly F2 then F1 and F5. REGISTERED behaviour, published in the comparison's
    separation table. Must NOT be answered by re-tuning the floor."
  - "(carried) insider_cluster remains serving-dead (collector stopped at 2026q1); stood
    down by the variance floor on any night it is constant, never pre-excluded"
  - "(carried) the §13.0 live closure; the short_int knowable-lag reconciliation
    (task_a85de1cd); sue_z re-home; PR-1a advisories A3/A4/A5/A7"
next_actions:
  - "w3 re-cut, now cheaper: the champion side is stamped nightly in the store as
    prophet_shadow_score / prophet_shadow_score_rank rather than existing only on the
    in-memory board row. Re-cut the prereg against those columns, NOT against
    prophet_score / score_rank, which are the challenger's on a v3 row. Register the
    F8/F4 near-constancy question as a REGISTRY decision in the same pass."
  - "(inherited) Verify the first post-merge nightly publishes rank_by=us_prophet_v3
    with a fusion receipt and no degradation stamp"
  - "(inherited) C2 re-enters when the fold law is satisfiable: 91 graded dates needed,
    67 more than held. Unchanged by this PR."
  - "(inherited) First us_prophet_v3 H=10 grade matures ~10 sessions after the first
    fusion night"
do_not_redo:
  - "Do not fill the canonical `prophet_*` leg columns from `prophet_shadow` on a v3
    row. It is misattribution and the store is append-only, so shadow-fed v3 rows would
    pool with genuine v2 rows forever. The nulls are the decision, not the bug —
    DEC:US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY, pinned by
    test_the_canonical_legs_stay_null_on_a_fusion_row."
  - "Do not write 0.0 for an absent shadow leg. A leg that genuinely measured 0.0 and a
    leg that was never computed are different facts and the store is the permanent
    record of which happened."
  - "Do not stamp prophet_shadow_* on a degraded night. There the retired scorer IS the
    published ranker, so the same number under two names would hand a forward race a
    guaranteed tie and let it score that as an observation."
  - "Do not read an arena champion baseline off prophet_score / score_rank without
    stratifying on board_definition — see the DSC."
  - "Do not believe a red from these suites in a sparse worktree. 17 of them here were
    artifacts of the omitted site/ and data/ trees; materialize before diagnosing."
  - "(inherited) the OVERRIDE handoff's five do_not_redo entries and the PR-0/1a/1b/2
    lists remain binding — see PROPHET-CONDITIONAL-FUSION-2026-08-15-OVERRIDE.md"
danger_areas:
  - "The store is APPEND-ONLY and forward-only. A column added here is null for every
    prior night and permanent for every night after, so a naming or semantics mistake
    cannot be edited out later — it can only be superseded by a second column."
  - "`prophet_shadow` is absent by design on a degraded night AND on every sibling board
    (hk_prophet_v1 never had one). Code that treats its absence as an error rather than
    as a reading will fire on exactly the nights something else already went wrong."
  - "The thirteen columns are read off the board row and originate nothing. If
    score_rows ever stops freezing `prophet_shadow.score_rank` onto the row before the
    canonical sort, prophet_shadow_score_rank goes null store-wide with nothing raising
    — the same silent shape this PR exists to close."
  - "(inherited) score_rows is SHARED with hk_board_rank; every fusion path is gated on
    definition == BOARD_DEFINITION and widening that gate silently re-ranks HK."
---

Cold-stranger summary: #5753 retired the five-leg `us_prophet_v2` scorer into a
zero-authority shadow and kept it running so the forward race would have a champion side
from night one. Its own handoff warned, in `danger_areas`, that anything still reading
`prophet.components` on a US row now reads a block that no longer exists — and named
`component_coverage` as "the first casualty". It was not the last: the PIT context store
and the candidate-pool row were the other two readers, and because they ACCRUE rather
than display, their failure was silent by construction and permanent by storage. Ten
store columns went null on the first fusion night while the values sat one field away.

The call taken here is to keep those ten null — the C1 ranker genuinely has no five-leg
decomposition, and filling them from the shadow would stamp the retired heuristic's
arithmetic under the canonical ranker's name in an append-only store — and to accrue the
retired scorer under its own thirteen-column family instead. The composite and the rank
ride with the legs, and that is the part worth carrying forward: the override's handoff
already described the forward race as "a join of the SAME ticker-level graded outcomes
against two rank columns", and the store carried one. The second was being computed
nightly and dropped.

The finding a w3 session most needs is not the nulls but what sits beside them:
`families.yml` declares `prophet_score`, `score_rank`, `display_rank` and `featured` as
the champion's own output, and on a fusion night all four carry the challenger's numbers
— measured, 81.7 against the champion's 62.5, on a row the champion ranked 3rd. A null
announces itself; a column that quietly changed meaning does not. The registry is not
edited here because it is a sibling's law, so a w3 re-cut must read the champion side
off `prophet_shadow_*` and stratify on `board_definition`, never off the bare column
names.

*Supersedes `PROPHET-CONDITIONAL-FUSION-2026-08-15-OVERRIDE.md` as the latest record for
this workstream without altering it; that file remains the fuller account of the override
itself — its byte-parity proofs, the as-of-night floor derivation, and the family
separation limits — and its still-live items are carried forward above.*
