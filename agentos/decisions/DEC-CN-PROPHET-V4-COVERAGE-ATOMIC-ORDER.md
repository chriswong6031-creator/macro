---
key: CN-PROPHET-V4-COVERAGE-ATOMIC-ORDER
question: >
  When Intelligence coverage of a China Prophet v4 bake is incomplete, may the live
  board mix intel_interest_score and v3 prophet_score in the same primary ordering
  slot, or must the bake use one ordering basis globally?
answer: >
  One ordering basis globally. If every ranked stock has valid measured Intelligence
  interest — including a measured 0.0 — the bake orders by intel_interest_then_v3_score.
  If even one ranked stock lacks valid Intelligence evidence (missing, unavailable, or
  malformed), the entire bake sets board_rank equal to score_rank and orders as v3.
  board_definition stays cn_prophet_v4. Individual Intelligence observations stay on
  the row; only their authority over this bake's order is disabled. There is no
  persistent fallback mode: the decision is remade independently on each bake.
  A coverage-fallback bake is a v4 operational bake and must not accrue as R4
  treatment. R4 treatment requires board_definition=cn_prophet_v4 AND lane=featured
  AND effective_order_basis=intel_interest_then_v3_score.
rationale: >
  The per-row v3-score substitute was a reasonable continuity mechanism for initial v4,
  but it compares uncovered high-v3 names against covered interest scores on different
  underlying scales. A partially broken Intelligence plane can then produce a hybrid
  ranking that is neither v4 nor v3. Atomic fallback is the boring, falsifiable
  alternative: no fitted mapping between the two scores is authorized, because there
  is no evidence justifying such a mapping. R4 asks whether intelligence ordering
  outperforms the displaced v3 ordering; a fallback observation that received control
  behavior must not enter the treatment cohort.
alternatives:
  - option: Keep mixed-scale ordering (interest for covered rows, v3 score substituted for uncovered rows)
    why_not: >
      The two keys are not commensurate. One uncovered name can invert the shelf relative
      to both pure intelligence order and pure v3 order.
  - option: Map interest onto the v3-score scale (percentile, rank, or fitted weights) so mixed rows stay comparable
    why_not: >
      Invents a mathematical mapping with no forward evidence. Forbidden by the
      hardening handoff; would be a new model, not a continuity mode.
  - option: Drop uncovered names, or score them zero
    why_not: >
      Fabricates a measurement. A measured 0.0 is valid evidence; an unavailable
      observation is not a zero.
  - option: Select R4 treatment by board_definition=cn_prophet_v4 alone
    why_not: >
      A fallback bake still stamps cn_prophet_v4 while running v3 order, which would
      contaminate the experiment with control behavior labeled as treatment.
evidence:
  - "engine/china_board_rank.py apply_v4_board_order — complete coverage sorts by intel_order_key; incomplete copies score_rank onto board_rank"
  - "tests/test_china_board_rank_v4.py — 99 measured + 1 unavailable live order == score_rank; measured 0.0 does not fallback; next complete bake resumes intelligence; R4 eligibility pins"
  - "engine/cn_v3_tripwires.py R4 treatment.effective_order_basis = intel_interest_then_v3_score"
  - "engine/china_standout_track.py append_board persists order_mode / requested_order_basis / effective_order_basis"
affects:
  - "DEC:CN-PROPHET-RANKS-BY-BOARD-INDEPENDENT-INTELLIGENCE"
  - "engine/china_board_rank.py"
  - "engine/cn_v3_tripwires.py"
  - "engine/china_standout_track.py"
  - "scripts/build_china_library.py"
confidence: high
reversibility: easy
decided_by: chairman-chris
decided_at: 2026-08-16
---

## Grounds

Operator implementation handoff "China Prophet v4 Hardening" (2026-08-16). This amends
the fallback clause of `DEC:CN-PROPHET-RANKS-BY-BOARD-INDEPENDENT-INTELLIGENCE` without
replacing the ranking-authority decision: Intelligence still owns ORDERING only, the
v3 score is untouched, and admission is unchanged. The per-row mixed-scale substitute
is what this record closes.

Revert path is the existing R4 one-field revert (`partition_board_rows` rank_field ->
`score_rank`) plus dropping the coverage-atomic branch in `apply_v4_board_order`.
