---
key: MARKET-OS-PASTE-FLOW-WRITES-WATCHLIST-NOT-PORTFOLIO
claim: >
  The current Macro flow labeled "Paste your holdings" does not create canonical
  Portfolio positions; it adds ticker symbols to the selected Watchlist and keeps the
  entered sizing in a separate temporary ENTERED/localStorage overlay.
falsifier: >
  Read templates/watchlist.js::runEntry and show that it calls
  WatchStore.portfolio.upsert/importRows without calling the Watchlist add()/pushCloud
  path, and that the persisted rows then appear in portfolio_positions.
so_what: >
  Future Market OS work must treat ENTERED as a temporary hypothetical basket only,
  remove its ability to affect Portfolio counts/risk/market views, and implement the
  canonical paste writer separately after Portfolio state authority is repaired.
kind: landmine
verified_at: 2026-08-20
verified_by: "GitHub connector read of templates/watchlist.js::runEntry, parseBook, weightsOf, and templates/watchstore.js Portfolio API on Macro main"
scope:
  - macro
  - terminal-user-services
  - "templates/watchlist.js"
  - "templates/watchstore.js"
  - "templates/portfolio.js"
confidence: verified
---

## Mechanism

The current flow:

```text
parseBook(text)
    ↓
add(ticker) for each row              # Watchlist blob mutation
    ↓
ENTERED = {mode, parsed}
    ↓
localStorage mdash.ws.entry.v1        # temporary sizes/text
    ↓
pushCloud()                           # selected Watchlist sync
```

The path does not invoke the canonical Portfolio adapter. The UI may therefore display a
Portfolio-looking analysis while Terminal and `portfolio_positions` remain empty.

## Consequences

- The apparent Portfolio and the actual Portfolio can disagree.
- Pasted names can modify a Watchlist as an undocumented side effect.
- Supplied sizes are not durable position fields.
- The temporary population can be counted or analyzed as though it were owned.
- Signing in does not prove the draft became a Portfolio.

## Required future behavior

A1A isolates this object as:

> Temporary basket — not saved to your Portfolio.

A1B later adds an explicit review and idempotent write into canonical Portfolio rows. A
future session must not "fix" the issue by renaming the existing Watchlist mutation.