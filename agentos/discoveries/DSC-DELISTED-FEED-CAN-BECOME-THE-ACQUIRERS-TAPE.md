---
key: DELISTED-FEED-CAN-BECOME-THE-ACQUIRERS-TAPE
claim: >
  Yahoo can answer a delisted ticker with the merger acquirer's CONTINUING
  series — the whole history re-based by the exchange ratio under
  auto_adjust=True plus live post-delisting successor bars — and the stocks
  collector's basis-rebase path (store.basis_shifted -> period='max' re-pull)
  then imports that foreign tape wholesale: AVB (delisted 2026-08-17) had its
  entire 1994-2026 file rewritten onto a x2.793 successor basis with moving
  bars through 08-24 by the 2026-08-22 nightly.
falsifier: >
  git show 006a5e921eb4:data/stocks/AVB.parquet — if its 2026-08-14 close reads
  ~184.06 (the real AvalonBay basis, as the prior nightly 2509329de74f has)
  rather than ~65.90, the wholesale rescale did not happen. Forward: a future
  ledger-row delisting whose data/stocks file never diverges despite the
  symbol staying in the fetch set would weaken the mechanism claim.
so_what: >
  A delisting must reach lib/delisted_symbols (config/delisted_symbols.yml) to
  stop EVERY yfinance write path into data/stocks — the nightly
  StockPriceAdapter retention set AND scripts/heal_stocks_basis.py — because a
  dead symbol's feed is not merely empty, it can be a DIFFERENT instrument.
  Never "heal" a delisted name's basis drift: the drift IS the contamination.
  Freshness-by-lag cannot detect this class (the tape keeps advancing); the
  tell is a store tip AFTER the ledger's last_session, now shouted by
  scripts/audit_stocks_freshness.py and collectors/yahoo.py alike.
kind: landmine
verified_at: 2026-08-28
verified_by: >
  Blob comparison across nightly commits (2509329de74f real basis 184.06 ->
  006a5e921eb4 rescaled 65.90, ratio 2.793 constant 1994-2026 vs
  data/baskets/ohlcv/AVB.parquet); fix + heal PR "stocks: exit-ledger
  exclusion + AVB successor-splice heal" (claude/avb-delisted-stocks-contamination).
scope:
  - macro
  - collectors/sector_holdings.py
  - scripts/heal_stocks_basis.py
  - scripts/audit_stocks_freshness.py
  - config/delisted_symbols.yml
  - data/stocks/
confidence: verified
---

The reused-ticker audit's `delisted_printing` class did flag AVB (unacked,
disclosure-only) — detection existed but nothing blocked the write. EQR sits in
the same unacked list for a different reason (rename to VMRK; key-migration
protocol #4622, not a ledger row — the security continues).
