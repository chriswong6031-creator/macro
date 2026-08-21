---
key: MARKET-OS-PORTFOLIO-TRUTH-PRECEDES-FAST-IMPORT
question: >
  May the first Market OS runtime PR combine Portfolio population repair, state
  authority, weighting behavior, paste parsing, duplicate reconciliation, batch
  persistence, retry safety, and the new import interface?
answer: >
  No. Ship A1A Portfolio Population Truth + State Authority first. Only after A1A is
  proven in production may A1B convert a reviewed paste into canonical Portfolio
  positions. A1A repairs which object the page describes; A1B writes new rows into that
  repaired object.
rationale: >
  The current page conflates canonical Portfolio positions, a temporary pasted basket,
  and the selected Watchlist. Adding a bulk writer before the read authority is repaired
  would make it easy to persist into the wrong plane, duplicate rows after ambiguous
  network outcomes, or display a successful import through contaminated counts and risk.
  One independently useful truth-repair PR creates a stable acceptance surface for the
  later import PR and keeps failure diagnosis bounded.
alternatives:
  - option: Ship the complete paste-to-Portfolio experience in one broad PR
    why_not: >
      It moves too many authority boundaries at once: population, auth state, cloud/local
      fallback, weighting, parser semantics, duplicate identity, retry, persistence, and
      UI. Green tests would not isolate which layer made a Portfolio truthful or false.
  - option: Ship only new empty-state copy and leave the current data paths
    why_not: >
      The visible bug is caused by population and authority crossover, not wording.
      Cosmetic repair would preserve the lie.
  - option: Build import first and repair the surrounding page afterward
    why_not: >
      A writer cannot be accepted against a reader that may borrow the Watchlist count,
      union market membership, or silently switch an authenticated cloud user to a local
      Portfolio after failure.
evidence:
  - "Turn 6 adversarial archaeology found watchlist.js::runEntry writes through Watchlist add()/pushCloud rather than WatchStore.portfolio."
  - "watchstore.js::portfolioList returns the local Portfolio after an authenticated cloud read failure, and later _isLocalMode routes writes locally."
  - "portfolio.js uses open.length < 2 for both zero and one positions and mixes current-value rows with equal fallbacks in one money distribution."
  - "factor_exposure.js can already normalize explicit equal relative weights, so A1A can make all-unsized canonical Portfolios useful without import or schema work."
  - "Chairman requires small vertical slices without shrinking the full product vision."
affects:
  - "WS:MARKET-OS"
  - "templates/watchlist.js"
  - "templates/portfolio.js"
  - "templates/market_books.js"
  - "templates/watchstore.js"
  - "agentos/handoffs/MARKET-OS-2026-08-20.md"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-20
---

## A1A acceptance object

A1A is complete only when the live Portfolio surface describes canonical Portfolio rows
in loading, empty, one-position, many-position, degraded, and error states, with:

- no Watchlist population in counts, filters, table, or risk;
- explicit local versus cloud authority;
- all-unsized equal analysis labeled as an assumption;
- mixed sizing and mixed price basis abstaining rather than filling gaps;
- Portfolio-specific save state;
- no fabricated cluster when the risk engine supplied none.

## A1B gate

A1B remains unauthorized until A1A is merged, deployed, and proven against a real account
that has a populated Watchlist and an empty Portfolio. CI and fixture HTML alone do not
satisfy the gate.