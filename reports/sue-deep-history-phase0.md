# SUE deep-history re-validation — Phase-0 follow-up

**VERDICT: SUE is DEMOTED from scored → display. The deep-history re-validation the docs called
for is now DONE (the price block was lifted by a backfill), and it COLLAPSES SUE's cross-sectional
edge: IC 0.038 → 0.0006, HAC t 2.85 → 0.06. The whole factor zoo is now scored on deep history.**

`DATA_SIGNAL_EXPANSION_2026.md #5` flagged that SUE shipped "validated on the 2023-2025 price
window because the price-universe cache is shallow there … a deep-history + PIT-survivorship
re-validation is the honest follow-up." The first pass of this report (below, *The block*)
characterized that block; this pass removes it and reports the result.

## What changed since the first pass — the block was lifted

`scripts/sue_deep_phase0.py` backfilled max-history adjusted closes for the EDGAR EPS universe
(yfinance, batched, cached to `data/edgar/sue_deep_closes.parquet`: 1,313 names, 1,113 with
>10y). That panel unblocks the deep grid. The IC scorecard pipeline was then wired to use it:
`engine.equity_factors._closes("deep")` + `scripts.factor_ic_scorecard --deep` rebuild the whole
factor cross-section on the deep panel and refresh `data/edgar/ic_scorecard.json`.

## Deep result (`scripts/factor_ic_scorecard --deep --start 2011`)

Span **2011-03-31 … 2025-12-31, 60 quarterly rebalances, ~1,154 names**, forward 63d, fully
point-in-time (EDGAR fundamentals truncated to as-of; FINRA short-interest dropped — it has no
point-in-time history).

| factor | mean IC | IC-IR (ann) | t_HAC | q_FDR | hit | n | survives FDR |
|---|--:|--:|--:|--:|--:|--:|:--:|
| payout (shareholder yield) | **+0.0247** | +0.60 | **+2.72** | **0.072** | 0.58 | 60 | ✅ |
| value | +0.0184 | +0.45 | +2.01 | 0.247 | 0.55 | 60 | ✗ |
| profitability | +0.0141 | +0.24 | +0.82 | 0.93 | 0.55 | 60 | ✗ |
| … | | | | | | | |
| **SUE** | **+0.0006** | **+0.02** | **+0.06** | **0.95** | 0.52 | 60 | ✗ |
| low_vol | −0.0209 | −0.19 | −0.74 | 0.93 | 0.47 | 60 | ✗ |

**SUE collapses to ≈0** — exactly the standalone deep-SUE read (`sue_deep_phase0.json`: IC 0.0005,
IC-IR 0.016, HAC t 0.061, L/S quintile Sharpe 0.094). On the shallow 2023-2025 window SUE was the
strongest factor and the lone BH-FDR survivor (IC 0.038, q 0.05, L/S Sharpe 1.45). Deep history
erases it. **The lone deep survivor is now `payout`** (q 0.072) — but see the caveat: marginal,
and on a survivorship-biased panel it is not promoted to a scored leg.

## SURVIVORSHIP CAVEAT (load-bearing)

yahoo serves only **currently-listed** tickers, so delisted S&P members are absent — the deep panel
is survivorship-**BIASED**, an **optimistic bound** (the same caveat the whole factor zoo carries,
DATA_SIGNAL_EXPANSION #5). So:

- SUE's deep IC ≈ 0 is *generous* — a clean (delisting-recovered) panel would not raise it.
- `payout`'s marginal survival (q 0.072) is on the optimistic panel; shareholder-yield is plausibly
  correlated with **survival itself**, so the bias flatters it. It is **shown, not scored**.

A truly clean deep test needs delisting-recovered prices (harder / paid). Until then the deep read
is the honest *ceiling*, and a lone marginal survivor on it is not a green light.

## What was wired

- `engine/equity_factors.py`: `_closes("deep")` / `compute_factors(universe="deep")` read the deep
  panel; FINRA short-interest is omitted in deep mode (no PIT history → would leak the current snapshot).
- `scripts/factor_ic_scorecard.py --deep`: rebuilds the zoo on the deep panel, stamps
  `universe`/`survivorship_biased`/`price_span`/`caveat` into `ic_scorecard.json`, and **refuses to
  write a shallow fallback** when the (offline, gitignored) deep cache is absent — so daily CI never
  clobbers the committed deep scorecard with a shallow run.
- `engine/signal_lab.py` + `factors.html.j2` + `signal_lab.html.j2`: SUE row demoted scored→display;
  the live factor panel and prose now carry the deep span + survivorship caveat.

## The block (first pass — kept for the record)

| component | depth | status |
|---|---|---|
| EPS panel (`data/edgar/eps_quarterly.parquet`) | 2008-03 → 2026-05, 1,317 tickers | deep ✓ |
| PIT fundamentals (`data/edgar/fundamentals_panel.parquet`) | fy 2009 → 2025 | deep ✓ |
| Broad-universe prices (`engine.equity_factors._closes()`) | 2023-05 → 2026, ~1,506 tickers | **was shallow ✗ — the binding constraint** |

The EPS history and PIT fundamentals were always deep; only the broad-universe **daily-close panel**
was shallow (~3y rolling breadth cache). The backfill above removed that binding constraint.

## Conclusion

The shallow ~2.5y window over-credited SUE; deep history (even survivorship-biased and optimistic)
says it has no cross-sectional edge. SUE is demoted to earnings-momentum context. No cross-sectional
free-data factor earns a *scored* leg on the honest deep panel — which is the point of publishing the
graveyard rather than a green light.
