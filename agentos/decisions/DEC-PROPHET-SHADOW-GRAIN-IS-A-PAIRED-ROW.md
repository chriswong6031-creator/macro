---
key: PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW
question: >
  Must the retired us_prophet_v2 scorer's forward outcomes be kept under their own
  board_definition key in the candidates store — duplicating the whole candidate
  universe per night — or is one candidate row carrying the canonical C1 rank plus a
  prophet_shadow score/rank the correct grain for the forward race?
answer: >
  The shipped paired-row design is ACCEPTED. One row per name per night, stamped with
  the canonical us_prophet_v3 rank and carrying the retired scorer's score and
  score_rank as prophet_shadow (naming us_prophet_v2_shadow). The forward race is a
  JOIN of the same ticker-level graded outcomes against two rank columns, not two
  separately keyed populations. This deviates from the PR-0 commissioning, which asked
  for the shadow's outcomes to be keyed by the store's board_definition, and the
  deviation is ratified rather than merely tolerated. The acceptance is CONDITIONAL on
  three properties holding, and they are the test for any future challenger: canonical
  and shadow must admit the SAME candidate population; they must grade against the SAME
  ticker-level outcome; and the shadow must hold zero gate, rank and plan authority.
  A challenger that breaks any one of them — a different admission population,
  different grading semantics, or independent execution authority — is no longer a
  paired column and requires its own separately keyed lane at that point.
rationale: >
  The store's contract, not convenience, decides the grain. `append_candidates()`
  requires the COMPLETE verdict map — its whole value is that ineligible names are
  present too — so a second board_definition means duplicating ~2,900 rows and ~200
  context columns every night to vary TWO numbers. That is not a cheaper or dearer
  version of the same record; it is a second copy of the entire candidate plane whose
  only true difference is a score and a rank, and every column in it would have to be
  kept identical by construction forever or the two lanes would silently diverge on
  something that was never the subject of the comparison.
  The constraint the commissioning actually names is NO SECOND GRADER AND NO DUPLICATE
  CONTROL PLANE, and the paired row satisfies it exactly: there is one grader, one
  outcome per ticker per night, and the two rankers differ only where they are supposed
  to differ. Keying by definition would BUY separation of forward records — which is
  the failure the v1->v2 bump and hk_prophet_v2 (#4470) exist to prevent — but that
  failure is about pooling two rankers' records into one track record, and a paired
  column cannot pool them: the two ranks sit in different fields on the same row and
  no query can average them by accident. The separation is achieved by construction
  instead of by key.
  The three conditions are what make that argument sound rather than merely convenient.
  Same population + same outcome + zero authority is precisely the case where "two rank
  columns on one row" and "two keyed lanes" carry identical information. Break any of
  them and they stop being equivalent — which is why the conditions are recorded as the
  boundary of this decision and not as commentary on it.
alternatives:
  - option: Key the shadow by board_definition as PR-0 commissioned
    why_not: ~2,900 duplicated rows x ~200 context columns per night to vary a score
      and a rank, with every other column obliged to stay identical by construction in
      perpetuity. It buys forward-record separation that the paired column already has
      structurally. Remains the correct answer the moment any of the three conditions
      fails, and is reversible into (see reversibility).
  - option: Do not run the retired scorer forward at all
    why_not: Already refused by DEC:PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER —
      retiring the champion on the day it is superseded destroys the only prospective
      comparison this change will ever have. The shadow costs one arithmetic pass over
      rows already in memory.
  - option: Keep the shadow but grade it with its own grader
    why_not: A second grader is the duplicate control plane the commissioning forbids
      by name, and it would make every rank difference unattributable — a divergence
      could be the ranker or the grading, with no way to tell which.
evidence:
  - "engine/us_board_rank.py score_rows: prophet_shadow stamped on every row with its
    own score_rank; SHADOW_DEFINITION = us_prophet_v2_shadow"
  - "Observed on the live pool: AYI carries prophet.score 65.0 (C1, display_rank 1) and
    prophet_shadow {version: us_prophet_v2_shadow, score: 65.2, score_rank: 16} — the
    two orders on one row, which is the join the forward race needs"
  - "pytest tests/test_us_prophet_fusion.py::TestTheShadowHasNoAuthority — deleting
    prophet_shadow from every row leaves the scored output byte-identical; the shadow's
    own rank differs from the board order on the fixture, so the test is not vacuous"
  - "PROPHET-CONDITIONAL-FUSION-2026-08-15-OVERRIDE.md `unresolved[0]` — the deviation
    was flagged for adjudication at handoff rather than taken silently"
  - "scripts/build_stock_library.py:6531 — the store dedupes on (stamp_date, ticker,
    board_definition), which is why a degraded night must not wear the canonical stamp"
affects:
  - WS:PROPHET-CONDITIONAL-FUSION
  - engine/us_board_rank.py
  - engine/us_context_vector.py
  - scripts/build_stock_library.py
confidence: high
reversibility: easy
reversibility_detail: >
  Forward-only and additive. Stamping the second definition later starts a separately
  keyed lane from that night on; the paired rows already written keep both numbers on
  the row and stay readable as the join they were built to be, so nothing already
  accrued is lost or has to be migrated. The cost of reversing is the duplicate store
  volume, which is exactly the cost this decision declined to pay today.
decided_by: ceo-sol
decided_at: 2026-08-15
---

## What this does NOT settle

* **It is not a ruling that paired columns are the house pattern.** It is a ruling for
  a shadow that shares the population, the outcome and the grader, and holds no
  authority. The three conditions are the decision.
* **It grants the shadow nothing.** `us_prophet_v2_shadow` still originates no plan,
  controls no Featured slot, sets no priority and moves no user-visible order — see
  [[DEC-PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER]] and the `authority` string the
  shadow block publishes on every row.
* **It is not evidence about either ranker.** Which of the two columns orders names
  better is a w3 question with no graded fusion night yet in existence.
