---
key: MARKET-OS-WATCHLIST-PORTFOLIO-SEPARATE-TRUTH-UNIFIED-EXPERIENCE
question: >
  Should Mastermind collapse Watchlists and Portfolio into one stored and analyzed
  object because users may treat one of their Watchlists as their Portfolio?
answer: >
  No. Keep one canonical Portfolio population and multiple canonical Watchlist
  populations separate in truth, while unifying their interaction inside My Market.
  Portfolio means owned or explicitly held exposure. A Watchlist means attention only.
  One Add to My Market flow may write to either or both, and a Watchlist may be analyzed
  only through an explicit hypothetical-basket mode.
rationale: >
  Portfolio risk, sizing, cost basis, brokerage synchronization, cash, and personal
  impact all require an ownership population. Watchlists carry none of those semantics.
  The current union construction already demonstrates the failure mode: Watchlist names
  enter Portfolio market counts and can appear to keep an empty Portfolio populated.
  Unified interaction removes user friction without destroying the truth boundary that
  every later Portfolio calculation depends on.
alternatives:
  - option: Store Watchlists and Portfolio as one positions table with a kind discriminator
    why_not: >
      This would still require every consumer to recover two meanings from one row set,
      makes accidental population union easier, and weakens the canonical owner boundary
      already implemented as watchlists/watchlist_symbols versus portfolio_positions.
  - option: Treat any selected Watchlist as the actual Portfolio and equal-weight missing sizes
    why_not: >
      Interest is not ownership. Equal weighting can be an explicit hypothetical or an
      all-unsized analysis assumption, but it may not silently turn watched names into
      financial exposure.
  - option: Keep Portfolio and Watchlists on unrelated pages with unrelated controls
    why_not: >
      This preserves semantics but repeats the current workflow break. The user should
      navigate one My Market experience and use one add flow while the underlying truth
      remains distinct.
evidence:
  - "templates/market_books.js::buildModel on Macro main unions Watchlist symbols with open Portfolio positions before painting the market strip (GitHub connector read, 2026-08-20)."
  - "templates/watchlist.js::pfCount falls back to the Watchlist blob length when the Portfolio controller is unavailable (GitHub connector read, 2026-08-20)."
  - "Terminal PR #410 merged a positions-only /portfolio surface over portfolio_positions and removed the Watchlist-as-Portfolio switcher."
  - "Terminal supabase/migrations/0007_portfolio_positions.sql records portfolio_positions separately from watchlists and watchlist_symbols."
  - "Chairman Market OS brief requires an easy unified experience but presents amalgamation as a product-design option, not a binding storage ruling."
affects:
  - "WS:MARKET-OS"
  - "WS:WATCHLIST-PORTFOLIO-CEO"
  - "terminal-user-services"
  - "templates/watchlist.html.j2"
  - "templates/watchlist.js"
  - "templates/portfolio.js"
  - "templates/market_books.js"
  - "templates/watchstore.js"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-20
---

## Product consequence

The product shell is **My Market**:

```text
My Market
├── Overview
├── Portfolio
├── AI Infrastructure
├── Dividend Watch
├── China Ideas
└── Other named Watchlists
```

Overview may combine changes and events across those collections, but every item names
its source population. Portfolio calculations use Portfolio positions only. A named
Watchlist uses only its own symbols. Cross-collection synthesis is an explicit projection,
not a shared denominator.

## Data consequence

Preserve the canonical shared Supabase plane:

- `portfolio_positions` for held positions;
- `watchlists` and `watchlist_symbols` for attention sets.

Brokerage synchronization must populate the canonical Portfolio plane rather than minting
a connected-portfolio store. A future Watchlist basket calculation is labeled hypothetical
and never presented as actual allocation or risk.

## Reopening condition

Reopen only if a later migration proves that one physical table can preserve two immutable,
type-safe populations across every Macro and Terminal consumer with less risk than the
current separate stores. Ease of UI implementation is not such evidence.