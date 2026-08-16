---
key: PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER
question: >
  Does the deterministic C1 evidence-family fusion have to win the frozen w7 promotion
  gate before it may order the live US board, as WS:PROPHET-CONDITIONAL-FUSION committed
  in its objective and scope boundary?
answer: >
  No, by Chairman override dated 2026-08-15. C1 becomes the canonical US board ranker
  immediately, shipped as board definition us_prophet_v3. The exact pre-change
  us_prophet_v2 scorer is frozen, byte-parity proven, and continues to run nightly over
  the identical candidate population under us_prophet_v2_shadow with zero rank, gate and
  plan authority. Selection is untouched - population, raw signal gate, admissible entry
  statuses, stage logic, execution safeguards, featured shortfalls, earnings/extension
  checks and caps are all unchanged, and SELECTION_ERA deliberately does not move. The
  canonical order becomes (stage_rank, -fusion_score, ticker). The override covers C1
  ONLY: the promotion gate is narrowed, not repealed, and still governs C2-C5 and every
  claim of forward predictive alpha.
rationale: >
  Three properties made C1 adoptable without the gate, and the override rests on them
  rather than on any outcome evidence. (1) It is UNFITTED - an equal-weight vote across
  evidence families with no coefficient read off any outcome - so there is no fit to
  overfit and nothing the missing folds would have calibrated. That is exactly why the
  C2 refusal (#5700, zero lawful folds, 67 graded dates short) does not block it while
  it would block every rung above it. (2) It is a GLASS BOX - every published priority
  decomposes into named family contributions and member percentiles on the row itself -
  so a reader can audit an order they disagree with, which is the acceptance mode this
  override actually uses. (3) Its blast radius is ORDER ONLY: the same names are on the
  board, so the change cannot admit a name the gate would have refused. The commissioner
  accepts on a visual review of the resulting list, which is a legitimate PRODUCT
  criterion for a ranking change and is recorded as such - not as evidence of alpha.
alternatives:
  - option: Wait for w7 - run C1 in shadow until the arena adjudicates
    why_not: The arena's own arithmetic says the earliest lawful C2 read is 67 graded
      dates away and the first H=63 maturation is months out. Holding the live ranker
      to that clock is the permanent-no-wearing-a-gate's-clothes failure the program's
      own entry-map revision rule documents. The Chairman priced the wait against a
      board he can inspect today and chose the board.
  - option: Ship C1 but keep the us_prophet_v2 stamp, since selection did not change
    why_not: The forward ledgers key on board_definition. A board ordered by a different
      ranker publishes a different top-30 from the same evidence, so pooling v2's
      forward record with v3's would read as one track record of a ranker that never
      ran - the exact failure the v1->v2 bump and hk_prophet_v2 (#4470) exist to prevent.
  - option: Ship C1 and retire v2 entirely
    why_not: Retiring the champion on the day it is superseded destroys the only
      prospective comparison the program will ever have for this change. The shadow
      costs one arithmetic pass over rows already in memory and makes the champion side
      of the forward race observable from night one.
  - option: Fit family weights first (C2) so the vote is not equal-weight
    why_not: >
      Explicitly forbidden by the commissioning and by #5700's do_not_redo: no lawful
      folds exist, no fallback in-sample path exists, and adding one is the weakened-fit
      failure the arena was built to refuse.
evidence:
  - "Byte-parity of the ported aggregation against the raced C1 over the frozen 24-date
    research frame (2,251 rows): family scores identical to <1e-12, C1 scores identical
    to <1e-10 on the x100 production scale, null-for-null agreement, same admitted
    members and same families present. tests/test_us_prophet_fusion.py::
    TestByteParityWithTheRacedC1."
  - "Byte-parity of the FROZEN v2 scorer against 69 scores the board actually published
    under us_prophet_v2 on 2026-08-13 (site/factordata/us_standouts.json): every row
    reproduced to 1e-9. Without this the shadow is not a shadow and every before/after
    comparison is a comparison against nothing."
  - "As-of-night floors change the answer materially: on the live buy pool 7 of 8
    members vote and F1/F2/F4/F5/F8 are active, where the whole-frame floor admitted 6
    and F1 was absent (tier_cascade 0.25 across the frozen frame vs ~1.00 live). The
    prospective form #5700 left unimplemented was therefore a precondition, not a
    refinement."
  - "research/prophet_fusion/FUSION_BOARD_COMPARISON.md - the deterministic before/after
    over the 2026-08-13 board: 4 of the old top-5 move, 2 names enter the top 30 and 2
    leave, largest moves +15 (AYI 16->1) and -13 (CVCO 6->19, SNPS 14->27)."
  - "PR #5700 / research/prophet_fusion/PR2_C2_REDUNDANCY.md: C2 refused
    (refused_no_lawful_folds), zero fitted coefficients, 67 more graded dates needed."
affects:
  - WS:PROPHET-CONDITIONAL-FUSION
  - WS:PROPHET-US-ENTRY-TIMING
  - engine/us_board_rank.py
  - engine/us_prophet_fusion.py
  - engine/prophet_bridge.py
  - scripts/build_stock_library.py
  - research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md
reversibility: easy
reversibility_detail: >
  ONE CONSTANT, no data loss. Setting BOARD_DEFINITION back to us_prophet_v2 restores the
  retired scorer as the published ranker on the next build - legacy_v2_values is the
  frozen arithmetic and is still exercised nightly by the shadow and by the sibling HK
  board, so it cannot rot while unused. Rows already stamped us_prophet_v3 stay keyed
  under their own definition and never pool with v2's, so a revert loses no forward
  record on either side. The cost of a revert is the published discontinuity itself,
  which is why the era stamp moved rather than staying put.
confidence: high
decided_by: Chairman override, operator-relayed 2026-08-15 (Handoff A); implemented and recorded by the fable main loop
decided_at: 2026-08-15
---

## What this does NOT authorize

* **No C2 fit, no C3/C4/C5.** The fold law (masterplan §9.2) is untouched and no
  coefficient is manufactured. C1 ships precisely because it needs none.
* **No claim of forward predictive alpha.** `FUSION_SCORE_KIND` publishes the limit in
  the artifact: *"unfitted equal-weight evidence-family vote; a breadth-of-evidence
  ordering, not a calibrated return forecast and not a promoted alpha model."* The
  word "validated" is CI-enforced and does not appear.
* **No selection change.** `SELECTION_ERA` stays `anticipation-v1-2026-08-08`. A rank
  change is not an admission change, and bumping the era would restart the H=63 episode
  clock the era's own revision ruling exists to protect.
* **No silent degradation.** A night the fusion plane refuses publishes under
  `us_prophet_v2_fallback` with a `prophet.degradation` receipt. Missing is never
  reinterpreted as zero, at the row level (`fusion_score: null`, sorted after every
  scored row in its bucket) or at the board level.

## Relationship to the prior ruling

Supersedes the *sequencing* half of
[[DEC-PROPHET-ZERO-AUTHORITY-SUPERSEDED-BY-EARNED-CONDITIONAL-AUTHORITY]] — "the
deployed `us_prophet_v2` remains champion until a challenger clears the frozen arena and
promotion gate" — for C1 and C1 alone. The substantive half of that ruling (earned
conditional authority; no restoration of the additive `potential_score`, a
confirming-desk-count score, or an unconditional composite) is unchanged and still
binding: C1 is not a composite of desk counts, it is a per-family normalized vote with
the count constructions fenced out by name (`DNR:KILL-FUSED-COMPOSITE`,
`DNR:KILL-POSITIONING-FUSION`).
