# SP1-A — short-pressure branch study

Prereg: `research/short_side/SP1_SHORT_PRESSURE_PREREG.md (§5 + Amendment 1)` (committed before this ran).

**Entry convention (read from the panel, not assumed here):** 8 NYSE sessions after settlement (CORRECTED rule, lib/finra_knowable.py).

222,367 events, 193 entry dates, 1723 tickers, 2018-02-12 → 2026-06-10, median 1186 names/date.
Returns demeaned within date, so nothing here can come from market timing.

**Survivorship:** data/yahoo/ is the CURRENT universe; delisted names are absent. Biases AGAINST H1, so a null H1 is not decisive and no effect size here is unbiased.

**Horizon labels are row offsets, not trading days.** Measured on this run: 868 of 3041 index rows in the event window (28.5%) are weekend rows contributed by non-equity files in `data/yahoo/` (crypto/FX/futures), so a 21-row step spans 15 weekday sessions and a 63-row step spans 45. The `h` column below is the row offset. No effect size here is quotable until this is fixed.

| test | h | mean (pp) | NW t | q(BH) | 2018-21 / 2022-26 | same sign |
|---|---|---|---|---|---|---|
| H0 high-DTC minus low-DTC | 21d | +0.782 | 3.06 | 0.0022 | +0.61 / +0.93 | yes |
| H1 top-DTC price-weak minus top-DTC | 21d | +0.241 | 0.85 | 0.795 | +0.07 / +0.40 | yes |
| H2 top-DTC price-strong minus top-DTC | 21d | +0.039 | 0.21 | 1.0 | +0.01 / +0.07 | yes |
| H0 high-DTC minus low-DTC | 63d | +0.902 | 1.29 | 0.2366 | +0.22 / +1.52 | yes |
| H1 top-DTC price-weak minus top-DTC | 63d | +0.663 | 1.07 | 0.4287 | +0.40 / +0.91 | yes |
| H2 top-DTC price-strong minus top-DTC | 63d | +0.267 | 0.59 | 1.0 | +0.56 / +0.01 | yes |

## Verdict

**H0 DOES NOT REPLICATE (sign is positive, significant only in the WRONG direction) — per the prereg the branch tests H1/H2 are UNINTERPRETABLE and SP1-A is a NULL.**

H0 came out POSITIVE (high days-to-cover *out*performed low, +0.78pp at 21d / +0.90pp at 63d, t 3.06 / 1.29, q 0.0022 / 0.2366). The prereg's replication gate requires H0 to be NEGATIVE **and** significant, so it does not replicate and H1/H2 are uninterpretable. This must not be read as "high short interest is bullish": it is the signature of a universe and a sample that cannot see the effect.

## Why H0 does not replicate here — measured, not asserted

- **Survivorship.** Of names eligible pre-2021, 34.6% of the highest-DTC quintile are gone from the panel by 2025. The price panel is the CURRENT universe, so the high-DTC names that went to zero — precisely the population that carries the effect — are absent. This biases H0 positive.
- **Universe.** The study sees 1289 names against 5616 eligible; coverage by DTC quintile is {0: 11.3, 1: 21.9, 2: 35.0, 3: 29.0, 4: 23.1} percent — a large/mid-cap watchlist, while the documented effect concentrates in small and illiquid names. The sort still has real spread (6.9x top/bottom quintile vs 7.8x in the full universe), so this is a population difference, not a dead sort.
- **Post-publication decay.** The result published in 2015; this sample is 2018-2026, entirely post-publication, where McLean-Pontiff-class haircuts run 26-58%.

All three push the same direction, and each one on its own is enough to account for H0 failing to appear in the hypothesised direction here.

## What this does and does not license

- It does **not** license a squeeze product, a short-pressure ranking, or any authority. H2 (the squeeze branch) reached q=1.0 at 63d with halves +0.56 / +0.01 (same sign: yes), and 0.27pp is far below the +/-5pp promotion bar. Pre-declared expectation was null; it is null.
- It does **not** overturn the published result. The honest statement is that this universe cannot test it.
- It **does** name the fixes: (1) a delisting-inclusive price panel (`collectors/edgar_delisting.py` + `edgar_deadname_prices.py` exist) and a wider universe, for survivorship; and (2) a trading-day price index — `load_prices()` unions every file in `data/yahoo/`, including weekend-trading non-equities, which is what makes the `h` column a row offset rather than a session count. Until both are fixed, short pressure stays display-tier context here.
