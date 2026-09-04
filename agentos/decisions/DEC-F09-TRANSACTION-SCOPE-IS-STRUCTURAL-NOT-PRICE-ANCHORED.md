---
key: F09-TRANSACTION-SCOPE-IS-STRUCTURAL-NOT-PRICE-ANCHORED
question: >
  How does a deterministic extractor decide WHICH transaction a filing's price, currency,
  consideration, stated premium and expected close belong to, when one document can describe a
  live deal, a rejected prior proposal, a fairness opinion, financing and employee awards?
answer: >
  Structurally, and before any number is read. `document_sections()` splits the body at every
  section cue; sections whose ROLE cannot originate current consideration are disqualified
  outright (Background of the, Opinion of, Prior Proposals, Financing of the, Employment
  Agreements, Interests of, Certain Relationships, Risk Factors); `current_transaction_scope()`
  is then the FIRST admissible section carrying an explicit current-transaction anchor, or the
  first admissible section when none does. Every field is read only inside that span. A price
  outside it is still RECORDED — as a `deferred` observation noted
  `outside_current_transaction_scope` — so the evidence stays visible and can never become a
  live term. With no admissible section the extractor returns nothing and the state is
  TRANSACTION_SCOPE_UNRESOLVED.
rationale: >
  The previous scope was anchored on the FIRST price candidate and cut at the nearest section
  boundary, which lets the document decide which transaction it is describing by whichever
  number appears first. That is not transaction identity. Reproduced at head a88c12f2: a
  rejected March-2025 "$48.00 in cash per share" proposal under "Background of the Merger",
  beside a current all-stock merger, produced VERIFIED cash economics — offer 48.00, spread
  +20%, consideration `cash`. Section ROLE is a property of the document's own structure and is
  therefore independent of the values inside it, which is the whole reason it can arbitrate
  between them. Keeping the excluded prices as `deferred` rows also satisfies nulls-printed:
  the exclusion is auditable rather than invisible.
alternatives:
  - option: Add the missing corpus case only
    why_not: >
      Sol explicitly refused this ("Do not merely add a corpus row"). It leaves the mechanism
      intact, so the next unseen document shape reproduces the same class of failure.
  - option: Widen the negative lexicon around the price span
    why_not: >
      A character window is not a structure. A background price with no disqualifying word
      within ±160 characters still wins, and widening the window starts suppressing real prices.
  - option: Let a model decide which paragraph describes the live deal
    why_not: >
      Neural Web constitution A7 forbids model numeric authority, and recall bought with model
      judgment is exactly what this wave exists to remove.
  - option: Keep the 1200-character hard cap on scope
    why_not: >
      An arbitrary bound both truncates genuine multi-paragraph deal descriptions and still
      admits a background price that happens to fall inside it. The structural boundary is the
      real bound.
evidence:
  - "tests/test_special_arb.py::test_a_historical_cash_proposal_cannot_price_a_current_stock_deal"
  - "tests/test_special_arb.py::test_a_background_price_is_never_the_only_admissible_candidate"
  - "corpus historical_cash_proposal_current_stock_deal / prior_proposal_only_price / fairness_opinion_reference_price"
  - "measured pre-repair at macro#6793 head a88c12f2: VERIFIED, offer 48.0, spread +20.0, consideration cash"
  - "Sol GitHub reviews 5102199556 §6 and 5102373399 HIGH E"
affects:
  - "WS:MARKET-OS"
  - engine/special_arb.py
  - collectors/special_situations.py
  - tests/fixtures/special_situations/f09/**
confidence: high
reversibility: easy
decided_by: "session bb72a676-c429-4224-9479-dba3c02da269 (Claude8 runtime continuity for marketontology-f09-premium-math-v1-20260902-sol-001)"
decided_at: 2026-09-03
---

The third corpus case is the one that constrains the design rather than the outcome:
`fairness_opinion_reference_price` carries a correctly-scoped `$32.00` offer AND an
out-of-scope `$57.00` DCF value from the advisor's opinion. A rule that merely *suppressed on
conflict* would decline it and read as safe; the structural rule publishes 32.00 and files 57.00
as `deferred`. Precision without that case is indistinguishable from refusing to answer.

The anchor vocabulary is deliberately broad (`Agreement and Plan of`, `merger agreement`, `will
be converted`, `right to receive`, `tender offer`, `offer to purchase`, `all-cash`, `all-stock`,
`exchange ratio`, `combination`, `entered into`, …) because it only ever selects *among already
admissible* sections — a disqualified section stays disqualified no matter how many anchors it
contains. Widening it can therefore change recall but not precision, which is why this record is
`reversibility: easy`.
