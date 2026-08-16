---
key: CHAMPION-BASELINE-COLUMNS-CARRY-THE-CHALLENGER
claim: >
  On a `us_prophet_v3` night the four columns `research/prophet_fusion/families.yml`
  declares under `champion_baseline` as "the champion's own output" — `prophet_score`,
  `score_rank`, `display_rank`, `featured` — carry the CHALLENGER's numbers in the
  candidates store, and the ten `prophet_*` leg columns beside them are null. The
  fusion override did not thin the champion baseline, it repointed most of it: measured
  on a fusion board, store `prophet_score` = 81.7 (the C1 fusion score) while the
  retired scorer on the same row scored 62.5 and ranked that row 3rd, not 1st.
falsifier: >
  A row stamped `board_definition = us_prophet_v3` whose store `prophet_score` equals
  its own `prophet_shadow.score`, or whose `score_rank` equals its
  `prophet_shadow_score_rank`; or `families.yml` ceasing to list those four names under
  `champion_baseline`; or `us_board_rank._fusion_prophet_block` publishing the legacy
  score as `prophet.score` on a non-degraded fusion night.
so_what: >
  Any arena baseline (families.yml §8.1 G0/G0'/G1/G3/G4) that reads `prophet_score` or
  `score_rank` off rows stamped `us_prophet_v3` is scoring the challenger against
  itself and will read as a dead heat for reasons that have nothing to do with either
  ranker. The champion side must read the `prophet_shadow_*` family (added #5769);
  `board_definition` is already a declared stratum in the same file and is the
  discriminator. This is strictly more dangerous than the ten nulls shipped beside it:
  a null announces itself at the first `isna()`, a column that silently changed meaning
  does not, and both eras pool under one name in an append-only store. `families.yml`
  is a sibling builder's deliverable and was NOT edited to record this — the drift is
  live in the registry until w3 re-cuts it. Concretely for W3
  (research/prophet_fusion/W3_SHADOW_RACE_RECUT.md, #5767): its champion side is
  "stamped nightly by production" as `prophet_shadow.score`/`score_rank`, which are
  BOARD ROW fields; the store names are `prophet_shadow_score` /
  `prophet_shadow_score_rank` and they exist only from #5769. The store forbids
  retroactive backfill, so the champion side is null for every night between the
  2026-08-15 override and #5769's first nightly.
kind: landmine
verified_at: 2026-08-15
verified_by: >
  `engine.us_board_rank.score_rows` over a synthetic fusion pool, then
  `us_context_vector.build_records`: published_definition = us_prophet_v3,
  prophet.components = None, store prophet_score = 81.7 / score_rank = 1.0 / featured =
  True, prophet_signal..prophet_quality_points = None x10, prophet_shadow.score = 62.5
  and prophet_shadow.score_rank = 3. Declaration read at
  research/prophet_fusion/families.yml `champion_baseline` (the fourteen names and the
  note "Baseline comparators only"). Store-is-the-race-frame read at
  scripts/prophet_fusion_race.py:88 (`CANDIDATES_DIR = data/us_prophet_rank/candidates`).
  Pinned forward by tests/test_us_context_vector.py::
  TestTheRetiredScorerAccruesUnderItsOwnName.
scope: [macro]
confidence: verified
---

## Detail

The override (`DEC:PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER`) deliberately kept the
retired scorer running so the forward race would have a champion side from night one,
and its handoff describes that race as "a join of the SAME ticker-level graded outcomes
against two rank columns". The store only ever had ONE rank column. The shadow's score
and its own `score_rank` were computed nightly on the board row and never stamped, so
the design the handoff describes had no second column to join against — which is the
same defect as the ten null legs, one level up, and the reason #5769 carries
`prophet_shadow_score` and `prophet_shadow_score_rank` rather than only the five legs
and their points.

Three separate things are true at once on a v3 row and are easy to conflate:

* `prophet.score` is the canonical priority and is CORRECT — it is the board's ranker
  and every user-facing surface reads it. Nothing here is a defect in the board.
* `prophet_score` in the store is that same number, so it is the challenger's, and it is
  the column an arena baseline would reach for by name.
* `prophet_shadow.score` is the champion's, and until #5769 it existed only in memory.

A degraded night (`us_prophet_v2_fallback`) inverts the first two: there the retired
scorer IS the published ranker, `prophet_score` is genuinely the champion's number, and
`prophet_shadow` is withheld precisely so the same value is not published twice under
two names. So the mapping from column name to which ranker produced it is not fixed —
it is a function of `board_definition`, which is why that column is a stratum and why
no baseline may key on the bare name alone.
