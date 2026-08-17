---
key: CN-PROPHET-RANKS-BY-BOARD-INDEPENDENT-INTELLIGENCE
question: >
  May China Intelligence own the CN Prophet board's RANK — and if so, how, given that
  the Intelligence Hub reads the Prophet board as one of its five desks?
answer: >
  Yes, as ORDERING authority only, and only through a board-INDEPENDENT composite.
  The live definition is cn_prophet_v4 (2026-08-15): within each unchanged v3
  lifecycle/admission lane, rows order by measured intel_interest_score
  (engine/china_intel_interest.py), then by the unchanged v3 prophet_score, then by
  ticker — and the featured/sector caps bind in that order, so interest decides the
  last shelf slot. The v3 SCORE is untouched: no intelligence term enters
  SCORE_WEIGHTS. Every v3 admission gate is preserved byte for byte. The standing
  "never China Intelligence composites in Prophet" rule is replaced by a PROVENANCE
  rule: any displayed CN Prophet score/rank must trace to engine/china_board_rank.py,
  which may consume registered board-independent evidence; raw
  china_intel_hub.opportunity_score, Hub board-derived terms, and anything under
  research/cn_prophet_audit/ may never directly own Prophet rank. A name with no
  measurable intelligence keeps its v3 priority under an explicit
  intel_interest_basis=fallback_v3 stamp — never a fabricated zero.
rationale: >
  The thing that was actually dangerous was the FEEDBACK LOOP, not the word
  "composite". The Hub's opportunity_score carries the board's own output back into
  itself through four terms (board_row direction, board label edge, board-absent
  bonus, board's contribution to the leading-vs-lagging gap), so ranking the board by
  it would make names rank highly partly because they already rank highly.
  china_intel_interest re-derives the composite with all four STRUCTURALLY ABSENT —
  never computed, never available to compute — which is what makes it admissible
  where the Hub composite is not. First principles: rank by interestingness, gate by
  entry. A great entry oscillator should not carry an uninteresting name to the top,
  and an interesting name should still not be featured without clearing the entry and
  execution machinery. This ships with NO claim of statistical promotion: the R4
  tripwire's evidence field reads "NO forward evidence", and the displaced v3 ORDER
  accrues in parallel as cn_prophet_v3_shadow so the race is measurable from merge day.
alternatives:
  - option: Rank by the Hub's opportunity_score directly
    why_not: >
      Closes a feedback loop through four board-derived terms; explicitly forbidden by
      the amended provenance rule and by the operator's commission.
  - option: Add intelligence as a scored component inside SCORE_WEIGHTS
    why_not: >
      That is promotion to SCORE authority, which is gauntlet territory
      (DEC:GAUNTLET-GATES-PROMOTION-NOT-BUILD) and has no forward evidence. Ordering is
      the weakest authority that delivers the operator's requirement.
  - option: Score an unmeasured name zero instead of falling back to v3
    why_not: >
      Sinks every name the desks never saw beneath every covered name on evidence that
      was never gathered — a fabricated measurement, and the exact failure the "nulls
      printed, not hidden" law exists to prevent.
  - option: Keep the absolute ban and leave v3 live
    why_not: >
      Operator commission 2026-08-15 ("Handoff B") explicitly asks for intelligence
      ranking authority now; the ban's real target (the loop) is closed structurally.
evidence:
  - "engine/china_intel_interest.py — BOARD_DERIVED_TERMS_EXCLUDED; tests/test_china_intel_interest.py pins the fence structurally (AST read-scan, mutation-checked)"
  - "engine/china_board_rank.py — BOARD_DEFINITION=cn_prophet_v4, V3_SHADOW_DEFINITION, intel_order_key, rank_field; SCORE_WEIGHTS unchanged"
  - "research/cn_prophet_v4/V4_VS_V3_BOARD_PROOF_2026-08-14.md — 116/116 rows measured; 12 of 24 featured names change; reconstruction reproduces the live shelf exactly"
  - "Measured 2026-08-15: site/chinaaltdata/by_ticker.json is a top-30 DISPLAY slice covering 0/116 board rows; china_altdata.full_rows() covers 116/116 in ~1.8s"
  - "Measured 2026-08-15: 60/116 board rows read altdata side=distribute; an unsigned |convergence| core put the three most-distributed names in the top three slots"
  - "engine/cn_v3_tripwires.py R4 cn_v4_vs_v3_order_shadow_excess — named tripwire, 60-episode floor, revert action, evidence field states NO forward evidence"
affects:
  - "engine/china_board_rank.py"
  - "engine/china_intel_interest.py"
  - "engine/china_standout_track.py"
  - "engine/cn_v3_tripwires.py"
  - "scripts/build_china_library.py"
  - "site/factordata/china_standouts.json"
confidence: medium
reversibility: easy
decided_by: chairman-chris
decided_at: 2026-08-15
---

## Grounds

Operator commission ("Handoff B — China Prophet v4: intelligence-ranked, entry-gated",
2026-08-15). Confidence is `medium` rather than `high` because the FIRST-PRINCIPLES
architecture is sound and structurally enforced, while the empirical claim that
interest-first ordering beats score-first ordering has **n=0** and is exactly what the
R4 shadow race exists to measure. Reversibility is `easy` by design: the revert is
one field — `partition_board_rows(rank_field="score_rank")` — plus moving
`BOARD_DEFINITION` back, with historical rows untouched either way.

## Boundaries this decision does NOT cross

- No SCORE authority. `SCORE_WEIGHTS` is unchanged; `prophet_score` is bit-identical
  with and without intelligence (pinned by `test_intel_adds_no_score`).
- No ADMISSION authority. An uninteresting name is never gated out, and a fascinating
  one is never gated in: every v3 execution safeguard is preserved and is
  order-independent (pinned by `test_admission_gates_are_order_independent`).
- No research leakage. Nothing under `research/cn_prophet_audit/` is read; P-B2/P-B3/P-C
  fences are unmodified (annotated, not amended, in the P-B2 prereg §13).
- No promotion claim. The word "validated" appears nowhere user-facing, and the R4
  evidence field states plainly that there is none yet.

## Era bookkeeping

`cn_prophet_v3` joined `_CN_SUPERSEDED_ERA_STAMPS` in the same PR — the repo's own
era-partition tripwire (`tests/test_cn_track_ledger_eras.py`) caught the omission, which
is how 72 v2 rows once fell out of every cohort (#4509). v3's accrued rows stay a closed
era, graded as `prior_record`, never pooled with v4's.

## What would reopen this

R4 maturing against the v3-order shadow with v4 behind it by any margin at n>=60; a
demonstration that `intel_interest_score` is not in fact board-independent (a leak past
the AST fence); or evidence that the ordering change moved names in a way the entry
machinery was silently relying on the old order to prevent.
