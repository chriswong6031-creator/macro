# SP1-A — short-pressure branch study

Prereg: `research/short_side/SP1_SHORT_PRESSURE_PREREG.md (§5 + Amendment 1)` (committed before this ran).

47,807 events, 120 entry dates, 641 tickers, 2018-01-22 → 2026-04-10, median 339 names/date.
Returns demeaned within date, so nothing here can come from market timing.

**Survivorship:** data/yahoo/ is the CURRENT universe; delisted names are absent. Biases AGAINST H1, so a null H1 is not decisive and no effect size here is unbiased.

| test | h | mean (pp) | NW t | q(BH) | 2018-21 / 2022-26 | same sign |
|---|---|---|---|---|---|---|
| H0 high-DTC minus low-DTC | 21d | +0.372 | 1.22 | 0.4466 | +0.48 / +0.28 | yes |
| H1 top-DTC price-weak minus top-DTC | 21d | +0.510 | 1.48 | 0.1661 | +0.67 / +0.37 | yes |
| H2 top-DTC price-strong minus top-DTC | 21d | +0.142 | 0.41 | 1.0 | -0.65 / +0.87 | NO |
| H0 high-DTC minus low-DTC | 63d | +0.785 | 1.09 | 0.822 | +1.34 / +0.29 | yes |
| H1 top-DTC price-weak minus top-DTC | 63d | +1.012 | 1.39 | 0.2488 | +0.42 / +1.55 | yes |
| H2 top-DTC price-strong minus top-DTC | 63d | +1.282 | 1.69 | 0.0918 | +0.28 / +2.19 | yes |

## Verdict

**H0 DOES NOT REPLICATE (sign is positive, not significant) — per the prereg the branch tests H1/H2 are UNINTERPRETABLE and SP1-A is a NULL.**

H0 came out POSITIVE (high days-to-cover *out*performed low, +0.37pp at 21d / +0.79pp at 63d, t 1.22 / 1.09) — the opposite sign to the published result and not significant. This must not be read as "high short interest is bullish": it is the signature of a universe and a sample that cannot see the effect.

## Why H0 does not replicate here — measured, not asserted

- **Survivorship.** Of names eligible pre-2021, 34.8% of the highest-DTC quintile are gone from the panel by 2025. The price panel is the CURRENT universe, so the high-DTC names that went to zero — precisely the population that carries the effect — are absent. This biases H0 positive.
- **Universe.** The study sees 583 names against 5616 eligible; coverage by DTC quintile is {0: 3.2, 1: 13.4, 2: 19.2, 3: 12.6, 4: 7.2} percent — a large/mid-cap watchlist, while the documented effect concentrates in small and illiquid names. The sort still has real spread (5.4x top/bottom quintile vs 7.8x in the full universe), so this is a population difference, not a dead sort.
- **Post-publication decay.** The result published in 2015; this sample is 2018-2026, entirely post-publication, where McLean-Pontiff-class haircuts run 26-58%.

All three push the same direction and any one of them accounts for a t of 1.2.

## What this does and does not license

- It does **not** license a squeeze product, a short-pressure ranking, or any authority. H2 (the squeeze branch) reached q=0.09 at 63d but its 21d sibling flips sign across halves, its halves differ ~8x (+0.28 / +2.19), and 1.28pp is far below the +/-5pp promotion bar. Pre-declared expectation was null; it is null.
- It does **not** overturn the published result. The honest statement is that this universe cannot test it.
- It **does** name the fix: a delisting-inclusive price panel (`collectors/edgar_delisting.py` + `edgar_deadname_prices.py` exist) and a wider universe. Until then, short pressure stays display-tier context here.
