# US Stocks — new-signal Phase-0 (honesty check)

*Survivor panel (data/stocks, ~114 deep-OHLCV names). Optimistic bound; NOT a deep-PIT
validation. The GEX + vol-squeeze signals ship as display / entry-timing CONFIRMERS, never
a ranking alpha — this only checks they aren't actively harmful and behave as claimed.*

## (A) Volatility black hole — does compression precede a larger move?

- names used: **110** · coiled-entry days: 98422 · baseline days: 1091455
- mean forward-21d |move|: **coiled 6.29%** vs baseline 6.76%  → **0.93× lift**  (no clear lift)
- mean forward-21d signed return: coiled 1.55% vs baseline 1.55%  (≈0 difference expected — the squeeze is direction-agnostic)
- volume-CONFIRMED upside break: fwd-21d 1.52% (n=3285) vs UNCONFIRMED 1.27% (n=4047)  → the volume gate is the directional discriminator

## (B) Volatility-scaled vs plain 12-1 momentum (thin survivor cross-section)

- plain 12-1 momentum: rank-IC **0.0341** (t 3.63, n 634)
- vol-scaled momentum: rank-IC **0.0314** (t 3.46, n 634)
- Read directionally only (114-name survivor panel). Neither is promoted to the rank here;
  vol-scaled momentum is surfaced as a DISPLAY technical and is a candidate for a future
  deep-PIT gate when the offline panel is available.

## Decision

- The BARE squeeze shows no forward-|move| lift on this panel, so a still-coiled name gets
  **no entry tilt** — it is a display flag only ('a move may be loading'). Only the
  **volume-confirmed break** (the directional discriminator above) earns a bounded tilt.
- GEX confirmer + vol-squeeze stay **display + bounded entry-timing tilt**: they can only
  lower conviction, never manufacture a buy, and never touch the selection rank.
- vol-scaled momentum ≈ plain momentum here (crash-protection doesn't show on a survivor
  panel), so it stays a DISPLAY technical — re-run with the offline deep panel before any
  promotion into the rank.
