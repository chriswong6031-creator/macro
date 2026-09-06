---
key: A-FALLBACK-MAKES-ITS-PRIMARY-PATHS-COVERAGE-UNMEASURABLE
claim: >
  While a resolver ends in `(specific or general)[0]`, every gap in the specific matcher is
  invisible — the miss still resolves, through the fallback — so the primary path's true
  coverage is unmeasured for as long as the fallback exists, and deleting the fallback converts
  a pile of silent recall gaps into visible declines all at once.
falsifier: >
  Remove the `or admissible` fallback from `current_transaction_scope()` in
  `engine/special_arb.py` and walk `tests/fixtures/special_situations/f09/corpus.json`. If no
  case that previously resolved now declines, the anchor vocabulary had no gaps and this is
  wrong.
so_what: >
  When you delete a fallback, expect a burst of failures that are NOT regressions — they are
  the primary path's pre-existing gaps becoming visible for the first time. Triage each one on
  the merits instead of reading the count as breakage: a genuine formulation the vocabulary
  should always have carried is a RECALL bug, fixed by extending the closed vocabulary; a case
  that should never have resolved is now correctly declining and its expectation changes. The
  one move that is never available is restoring the fallback to quiet them, because that
  re-hides every gap including the ones you have not seen yet. Budget for this triage before
  removing a fallback — the failure count on the first run says nothing about how much is real.
kind: landmine
verified_at: 2026-09-04
verified_by: >
  macro#6793. Removing the fallback made 5 previously-green tests fail at once. Corpus audit
  split them exactly: the four NEGATIVE cases (dividend, redemption, exercise price, aggregate
  value) still declined correctly and needed nothing, while `contingent_value_right`,
  `cross_currency_bare_dollar`, `explicit_foreign_currency` and `terminated_offer` were genuine
  current transactions whose phrasing `_CURRENT_TXN_ANCHOR` did not carry ("will be acquired
  for", "will receive", "previously announced merger"). Vocabulary extended, negatives
  re-verified as still declining, 201 passed.
scope:
  - macro
  - engine/special_arb.py
confidence: verified
---

`current_transaction_scope()` chose the first admissible section carrying an explicit
current-transaction anchor, "or the first admissible section when none does". Sol's semantic
addendum killed the second clause: an unanchored section is not a proven transaction, so
selecting it makes document order the authority for which deal a published price belongs to.

The interesting part is what the deletion revealed. Five tests failed immediately, and the
tempting read — "the repair is too aggressive, soften the rule" — was wrong in both directions.
The corpus audit separated them cleanly:

| case | after removing the fallback | verdict |
|---|---|---|
| `dividend_negative`, `redemption_negative`, `exercise_price_negative`, `aggregate_value_negative` | still decline | correct, and now for a *structural* reason rather than only the negative lexicon |
| `contingent_value_right` — "holders **will receive** $9.00 in cash per share" | declines | genuine transaction, phrasing uncovered |
| `cross_currency_bare_dollar` / `explicit_foreign_currency` — "each common share **will be acquired for** C$32.00" | declines | genuine transaction, phrasing uncovered |
| `terminated_offer` — "the **previously announced merger** providing for $21.00" | declines | genuine transaction, phrasing uncovered |

So the fallback had been silently supplying scope for four real filings whose language the
anchor vocabulary never matched. Nobody could have measured that while it existed: every miss
resolved anyway, and the corpus was green.

The repair is to extend the closed vocabulary, which is categorically different from restoring
the fallback even though both turn the tests green. **A missing phrase is a recall bug; a
fallback is a false-precision bug.** Extending the vocabulary still requires the document to
assert a transaction; the fallback required only that the document have sections. The negatives
are the proof the distinction held — all four still decline after the widening.

One test fixture was also caught: the amendment-lineage case used a bare `Amendment No. 1.`
body with no anchor at all, so after the change it produced no observations and the test would
have passed for the wrong reason — nothing to merge, rather than a merge being refused. A real
amendment names the agreement it amends, and the fixture now does.
Related: [[A-GREEN-SUITE-CANNOT-TELL-YOU-WHICH-GUARDS-IT-PINS]].
