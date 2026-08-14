---
key: NAME-SCORE-HAS-TWO-DISAGREEING-MEMORIES
claim: >
  The published name_score (snapshots.jsonl rows' conviction.potential.score, which
  also overwrites the displayed conviction.score) and the nightly name_score store
  (data/name_score/us_calls.parquet, column score) agree on only 22-29% of names on
  the dates both cover, with |Δ| up to 99 on a 0-100 scale. A one-session lag join
  was tested and rejected — same-date is the best alignment at every offset tried.
  They are two different quantities wearing one name.
falsifier: >
  A (date,ticker) join of snapshots.jsonl conviction.potential.score against
  data/name_score/us_calls.parquet score showing >=95% agreement on fresh dates, or
  a documented transform (population, timing, or parameterization) that reconciles
  the two exactly.
so_what: >
  Any consumer, arena rung, grader, or LLM answer that reads the STORE is racing or
  describing a different quantity than what shipped on the board. PR-1b's G2 rung
  deliberately races the PUBLISHED value for this reason
  (research/prophet_fusion/PR1B_BASELINE_RACE.md §12.2). The owning lane
  (engine/name_score.py + scripts/build_stock_library.py + the us_calls grader)
  needs to either reconcile the writers or name the two quantities distinctly before
  any forward evaluation cites "name_score" unqualified.
kind: landmine
verified_at: 2026-08-14
verified_by: >
  PR-1b race receipts: research/prophet_fusion/PR1B_BASELINE_RACE.md §12.2 (agreement
  22-29% across probed dates, offset sweep rejected lag explanation); producer sites
  build_stock_library.py:3752-3755 (potential overrides displayed score) and the
  nightly us_calls append lane (git log on data/name_score/us_calls.parquet).
scope: [macro]
confidence: verified
---

## Detail

The board's published conviction.potential.score is computed inside the library build
from that night's board-row inputs; us_calls.parquet is appended by the engine regime
lane over the whole ~2,100-name library. The 22-29% agreement measured on overlapping
dates is far below anything a timing skew explains (the PR-1b receipt swept join
offsets). Until the owning lane reconciles them, "name_score" claims must name their
source; the fusion arena's G2 is pinned to the published value and the registry keeps
potential_score a forbidden composite either way.
