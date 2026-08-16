---
key: US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY
question: >
  The fusion override moved the retired v2 scorer's `components`/`points` off the
  published `prophet` block onto `prophet_shadow`, so the candidates store's ten
  `prophet_*` leg columns read null on every `us_prophet_v3` row. Leave them null and
  accept the accrual hole, or carry the retired scorer's output forward under its own
  column name?
answer: >
  Carry it, under its own name, and carry the COMPOSITE and the RANK with the legs.
  `engine/us_context_vector.py` gains a `SHADOW_COLUMNS` family of thirteen columns —
  `prophet_shadow_definition`, `prophet_shadow_score`, `prophet_shadow_score_rank`, and
  `prophet_shadow_{leg}` / `_{leg}_points` for the five legs — read off `prophet_shadow`
  and stamped on every row, present or null. `engine/us_candidate_lanes.py` carries the
  same block on the display-tier pool row. The canonical `prophet_*` columns STAY NULL
  on a v3 row: the C1 ranker genuinely has no five-leg decomposition (its receipt is
  `prophet.fusion`), and filling them from the shadow would stamp the retired
  heuristic's arithmetic under the canonical ranker's name in an append-only store.
  Every `prophet_shadow_*` column is null on a degraded night
  (`us_prophet_v2_fallback`), where the retired scorer IS the published ranker and
  `score_rows` withholds the shadow block on purpose. Zero authority: store and display
  only, no rank, gate or plan effect.
rationale: >
  Three facts decided it. (1) THE STORE IS THE RACE FRAME —
  scripts/prophet_fusion_race.py:88 reads data/us_prophet_rank/candidates, the very
  store us_context_vector writes, so leaving the legs null means the w3 forward race
  has no champion record at all forward of 2026-08-15. (2) THE CHAMPION BASELINE WAS
  ALREADY REPOINTED, not merely thinned — families.yml declares prophet_score,
  score_rank, display_rank and featured as `champion_baseline`, and on a v3 night all
  four carry the challenger's numbers (DSC:CHAMPION-BASELINE-COLUMNS-CARRY-THE-
  CHALLENGER). So the honest champion columns did not exist anywhere in the store, and
  a family of legs without a composite would not have created them. (3) THE OVERRIDE'S
  OWN HANDOFF ALREADY ASSUMED THEM: it describes the forward race as "a join of the
  SAME ticker-level graded outcomes against two rank columns", and the store carried
  one. Including score and score_rank is therefore completion of the shipped design,
  not scope added to it. Additive by construction — the store charters schema-union
  append with forward-only self-healing, so a new column is simply null for prior
  nights and no migration exists to get wrong.
alternatives:
  - option: Leave the `prophet_*` columns null and accept the accrual hole
    why_not: Defensible on attribution grounds — and that half is KEPT, the canonical
      columns do stay null. But it silently ends the champion's forward record on the
      night the champion was retired, which is the one thing the override's shadow was
      built to prevent, and the values were already being computed nightly one field
      away. The cost of keeping them is thirteen nullable columns in a store that
      already carries ~200.
  - option: Fill `prophet_*` from `prophet_shadow` so the existing columns keep working
    why_not: Misattribution, and permanent. The store is append-only and keyed for
      pooling, so genuine v2 rows and shadow-fed v3 rows would pool under one name as
      though one ranker produced both. Every consumer that correctly reads `prophet_*`
      as "the published ranker's legs" would then be wrong on exactly the nights the
      distinction matters.
  - option: Stamp a second `board_definition` row per name for the shadow
    why_not: >
      Settled independently and concurrently by
      DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW (#5767, merged 2026-08-15 02:06Z while
      this PR's packs were running), which ACCEPTS the paired row over a second key —
      the store's append_candidates() contract requires the COMPLETE verdict map, so a
      second definition duplicates ~2,900 rows and ~200 context columns per night to
      vary two numbers. That decision and this one are complements rather than rivals.
      It ratifies a forward race that is "a JOIN of the same ticker-level graded
      outcomes against two rank columns", and this one is what puts the SECOND rank
      column in the store. Before it, the shadow's score and rank existed only on the
      in-memory board row, so the ratified design had one column to join.
  - option: Fix `research/prophet_fusion/families.yml` to repoint `champion_baseline`
    why_not: Out of scope and not this session's to take. families.yml is a sibling
      builder's deliverable, is the arena LAW, and is test-pinned. The drift is recorded
      as a discovery and belongs to the w3 re-cut, which is the wave that will actually
      read those columns.
evidence: >
  Reproduced through the production path, not inferred: score_rows over a fusion pool
  yields prophet.components = None and store prophet_signal..prophet_quality_points =
  None x10 on a v3 row, while prophet_shadow carries {'signal':1.0,'entry':1.0,
  'edge':0.0,'runway':0.75,'quality':0.0}, score 62.5 and score_rank 3. The degraded
  path reproduced separately (fuse_board raising): published_definition =
  us_prophet_v2_fallback, prophet.components populated, prophet_shadow absent, store
  prophet_signal = 1.0. 685 tests pass across the seven affected suites on a
  materialized checkout; 7 of the 9 new tests red on the unmodified engine.
affects:
  - WS:PROPHET-CONDITIONAL-FUSION
  - engine/us_context_vector.py
  - engine/us_candidate_lanes.py
  - data/us_prophet_rank/candidates/
reversibility: one_way
reversibility_detail: >
  Reversible in the CODE by deleting the family — nothing reads it yet and it holds no
  authority, so removal changes no behaviour. NOT reversible in the STORE: this is an
  append-only forward record, so rows already stamped keep the columns as historical
  fact for the nights they were written, and a naming or semantics mistake can only be
  superseded by a second column, never edited out. That one-way half is why the names
  were chosen to be unambiguous about which ranker produced each number, and why the
  canonical `prophet_*` columns were left alone rather than repurposed.
supersedes: []
scope: [macro]
confidence: high
pr: "#5769"
decided_at: 2026-08-15
decided_by: fable main loop, on the design call the #5753 commissioning left open
workstream: WS:PROPHET-CONDITIONAL-FUSION
---

## Detail

This is the second half of a defect the override's own handoff named in its
`danger_areas`: "Anything reading `prophet.components` or `prophet.points` on a US row
now reads a block that no longer exists — `component_coverage` was the first casualty
and would have reported every leg dead on every fusion night, which is the exact shape
of a real extension outage." `component_coverage` was fixed in #5753 by following the
legs onto the shadow. The two remaining readers — the PIT context store and the
candidate-pool row — were not, and they are the two that ACCRUE rather than display, so
their failure is silent by construction and permanent by storage.

What is deliberately NOT decided here: whether the shadow deserves its own
`board_definition` grain, whether `families.yml` should repoint `champion_baseline`, and
how the w3 prereg should be re-cut against a champion side that production now stamps
nightly. All three belong to the w3 re-cut and all three are now cheaper to answer,
because the numbers they need are in the store instead of in memory.
