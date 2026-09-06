---
key: CASH-DEAL-NUMBERS-ARE-BYTE-BOUND-OR-ABSENT
question: >
  How should the Special Situations desk stop publishing ungrounded risk-arbitrage
  economics - by constraining the OUTPUT (clamp, band, exception list, confidence score),
  or by constraining the INPUT (no number without source bytes)?
answer: >
  Input. A premium or spread number may be published only when it descends from an immutable
  `special_situations.deal_term_observation.v1` record bound to the filing body's sha256 with
  exact character offsets and an excerpt digest. Missing, ambiguous or coarse inputs produce a
  typed visible state (AMBIGUOUS / NOT_FIXED_CASH / STALE_PRICE / SOURCE_UNAVAILABLE /
  CALCULATION_UNAVAILABLE / TERMINAL), never a substituted value. The pre-existing magnitude
  band and days cap were REMOVED rather than tuned, and a fully receipted extreme value is
  published with an `extreme_value` disclosure flag rather than banded away.
rationale: >
  The output-constraining controls were already present and had already failed: the band
  admitted the 42,790.2% row because its offer/price ratio was an ordinary 1.6457
  (DSC:ARB-PLAUSIBILITY-BAND-ADMITTED-THE-DEFECT-IT-GUARDED). Any control that inspects only
  the derived number is blind to an invented input, so tightening it trades a visible wrong
  answer for an invisible one. Constraining the input also fixes the whole class at once: the
  same rule that kills the invented close day kills the stale close, the mixed-consideration
  row, the cross-currency compare and the model-authored price, because each fails to produce
  a byte-bound observation. It additionally makes the failure legible to a human - a typed
  state names WHAT is missing - where a clamp silently reports a plausible number.
alternatives:
  - option: Clamp or re-band the annualized value
    why_not: >
      The band already existed and passed the defect. A second guard on the same derived value
      inherits the same blindness, and the carrier explicitly rules a clamp not a fix.
  - option: Hard-code an LGMK exception or a ticker denylist
    why_not: >
      Fixes one row and leaves the mechanism. Guard test now fails the build if the string
      LGMK, _PLAUS_LO, _PLAUS_HI or _DAYS_CAP reappears in the owner.
  - option: Keep the LLM `llm_terms` lane as numeric authority with a confidence score
    why_not: >
      A confidence score is another derived number with no source binding; it cannot
      distinguish a correctly-read price from a fluent invention. The model keeps proposing
      candidates and drafting prose, but holds zero numeric authority.
  - option: Reuse contracts/capital_structure_document_term_observation.schema.json
    why_not: >
      Read it: it is scoped to registration-fee-table rows and requires issuer_id/security
      semantics that do not map to deal terms. Reusing it would couple Special Situations to
      the Capital Structure owner. Minted a sibling contract in the same house shape instead.
  - option: Build a new deal/event/price store to hold the grounded terms
    why_not: >
      Forbidden by the carrier and unnecessary: the observation ledger is a correction-safe
      child of the EXISTING event/accession owner and duplicates no lifecycle or source bytes.
evidence:
  - "macro#6785 (carrier), PR #6793"
  - "RED: all 39 new tests fail against origin/main's module; 654.3% published with zero provenance keys"
  - "GREEN: 117/117 on the three owned suites at head d93092705fdc"
  - "precision corpus: 8 correct publications, 8 correct declines, 0 false precise publications over 19 cases"
  - "no regressions: 45 failed / 1794 passed / 19 skipped identically on origin/main and branch (all 45 pre-existing sparse-tree artifacts)"
affects:
  - engine/special_arb.py
  - engine/special_situations.py
  - engine/special_sits_intel.py
  - collectors/special_situations.py
  - contracts/special_situations_deal_term_observation.schema.json
confidence: high
reversibility: costly
decided_by: "session 38c55853-6e42-4cbd-8a1f-910c2f7d673b (Claude4/Ryan4-Max), under Sol operation marketontology-f09-premium-math-v1-20260902-sol-001"
decided_at: 2026-09-03
review_by: 2026-12-03
---

## What "byte-bound" costs, and why it was accepted

Deterministic extraction has materially lower recall than the model lane it demotes: every
candidate span must clear an explicit per-share anchor plus a ±160-character negative lexicon,
so a filing that phrases the consideration unusually yields `TERM_NOT_FOUND` and the deal shows
a typed degraded state instead of a spread. That is the intended trade — the carrier's ruling
is that a declined extraction is a normal outcome and a false precise price is not.

Two consequences future sessions should not re-litigate:

1. **Coverage will look like a regression and is not one.** Fewer rows will carry economics
   than the `llm_terms` lane produced. The count that matters is VERIFIED rows plus a visible
   degraded census, not "rows with a number".
2. **A bare `$` names no currency.** It is admitted as USD only where the document carries no
   other dollar qualifier AND the listing is USD; every observation records which of four
   `currency_basis` values applied, so an inference can never later be mistaken for an
   observation. A `.TO` deal priced in a bare `$` is refused rather than compared to a USD close.
