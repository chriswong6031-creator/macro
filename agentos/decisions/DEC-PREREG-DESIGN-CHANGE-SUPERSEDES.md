---
key: PREREG-DESIGN-CHANGE-SUPERSEDES
question: >
  A short-interest study already ran and published. A later measurement showed its
  price index was not a trading-day index — weekend rows from crypto/FX/futures
  made every "21d"/"63d" label 15/45 weekday sessions, and a weekday-only
  counterfactual halved the H0 t-stat. Is restricting the index to NYSE sessions
  an in-place amendment (like the FINRA-lag gloss) or a supersession?
answer: >
  Supersede. Mint a successor study (SP1-B) with its own pre-registration, leave
  the original runs intact and non-quotable, and do not apply the filter as a
  correction of SP1-A. Complementary to DEC:PREREG-DATA-CONVENTION-CORRECTED-IN-PLACE,
  which still governs data-availability conventions. Applied to
  research/short_side/SP1_SHORT_PRESSURE_PREREG.md §5C.
rationale: >
  §5B's standing rule already reserved supersession for changes to the DESIGN —
  hypotheses, conditioners, horizons, universe, controls, statistics, or the
  promotion bar. Two of those surfaces move. Horizons: a 21-row step on the
  contaminated index spanned 15 weekday sessions; after the fix the same numeric
  label is 21 true NYSE sessions — a different estimand, not a gloss on the same
  window. Sample: searchsorted and MIN_NAMES_PER_DATE both change which
  settlements enter (counterfactual D: 193 → 188 entry dates). A data-availability
  convention answers "when is a fact knowable?"; the price calendar answers
  "what is a day?" and "what is a 21-day horizon?" Those are design parameters.
  The lag-correction licenses do not apply: that change made the test strictly
  harder and was not authored by looking at SP1 outcomes (PR #5705). This change
  was discovered by looking at SP1 outcomes and seeing t drop from 3.06 to 1.92.
  Applying it as an amendment after seeing that move is the goalpost hazard
  prereg immutability exists to forbid. Immutability is preserved by leaving
  SP1-A's two published runs attributable to the contaminated calendar they
  actually used, and by locking SP1-B's design — including the already-seen
  expected neighborhood and the unchanged promotion bar — BEFORE the official
  run. A result in that neighborhood is confirmation, not discovery; a material
  deviation (H0 negative-and-significant, or |mean| ≥ 5pp) needs its own
  adjudication. The citation ban is not lifted: survivorship remains unfixed.
alternatives:
  - option: Amend SP1-A in place, as §5B did for the FINRA lag
    why_not: >
      Misfiles a horizon-and-sample change as a data-availability convention.
      The lag case left every design surface untouched and corrected a factual
      gloss toward the rule's own stated intent, under two licenses this case
      lacks (strictly harder; not authored from SP1 outcomes). Rewriting what
      "21d" meant in the 2026-08-05 and 2026-08-15 entries would also destroy
      the audit trail of what those runs measured.
  - option: Relabel HORIZONS to (15, 45) so the official run preserves the old window
    why_not: >
      Preserves the bug. The original prereg said 21d and 63d intending trading
      days. Keeping the numeric labels as true sessions is the design the
      successor is for; keeping 15/45 would be a third, unregistered experiment.
  - option: Apply the filter without a new prereg, because the intent was always trading days
    why_not: >
      The study that RAN used a different estimand. Intent does not license a
      post-outcome redesign. The counterfactual already exists in §7; treating
      its numbers as SP1-A's official result is exactly the goalpost move.
  - option: Leave the calendar contaminated and only disclose it
    why_not: >
      The 2026-08-15 entry already disclosed it and named the next act as a
      pre-registration. Disclosure without a successor leaves every horizon
      label in the report off by 5/7 and the citation ban standing on a
      fixable third reason.
evidence:
  - "research/short_side/SP1_SHORT_PRESSURE_PREREG.md §5B standing rule — supersession reserved for design surfaces including horizons and universe"
  - "research/short_side/SP1_SHORT_PRESSURE_PREREG.md §7 2026-08-15 — 868/3041 weekend rows (28.5%); 21-row step = 15 weekday sessions; counterfactual D +0.702pp / t 1.92 / q 0.0551"
  - "DEC:PREREG-DATA-CONVENTION-CORRECTED-IN-PLACE — the complementary rule this does not supersede"
  - "scripts/research/sp1_short_pressure_study.py load_prices() unions every data/yahoo/ file; horizons via px.iloc[pos + h]"
  - "lib/nyse_calendar.py session_rows — house helper for dropping non-session rows"
affects:
  - "research/short_side/SP1_SHORT_PRESSURE_PREREG.md"
  - "research/*_PREREG.md"
  - "scripts/research/sp1_short_pressure_study.py"
  - "reports/sp1-short-pressure.md"
confidence: high
reversibility: easy
decided_by: session cursor/sp1-trading-day-index-0aee
decided_at: 2026-08-15
---

## Complementary, not a reversal

`DEC:PREREG-DATA-CONVENTION-CORRECTED-IN-PLACE` still governs the case it named:
a prereg whose *data-availability convention* is later measured wrong is
corrected in place. This record is the other half of that partition. It does
not supersede the earlier decision; it occupies the surface that decision
explicitly reserved.

## What would reverse this

A demonstration that the NYSE-session restriction leaves the estimand unchanged
— same event dates, same 21/63 weekday-session windows, same sample — would
collapse this back into a convention correction. The 2026-08-15 measurements
already refute that: 21-row = 15 sessions, and entry-date count moves.
