# SP1-B — short-pressure branch study (trading-day index)

Prereg: `research/short_side/SP1_SHORT_PRESSURE_PREREG.md (§5C SUPERSESSION 1)` (committed before this ran).

**Entry convention (read from the panel, not assumed here):** 8 NYSE sessions after settlement (CORRECTED rule, lib/finra_knowable.py).

229,486 events, 200 entry dates, 1715 tickers, 2018-01-25 → 2026-05-12, median 1183 names/date.
Returns demeaned within date, so nothing here can come from market timing.

**Survivorship:** data/yahoo/ is the CURRENT universe; delisted names are absent. Biases AGAINST H1, so a null H1 is not decisive and no effect size here is unbiased.

**Horizon labels are true NYSE sessions.** Measured on this run: 0 of 2085 index rows in the event window are weekend rows, so a 21-row step spans 21 weekday sessions and a 63-row step spans 63. The `h` column below is a session count. Survivorship is still unfixed; no effect size here is quotable.

| test | h | mean (pp) | NW t | q(BH) | 2018-21 / 2022-26 | same sign |
|---|---|---|---|---|---|---|
| H0 high-DTC minus low-DTC | 21d | +0.749 | 2.09 | 0.0363 | +0.28 / +1.18 | yes |
| H1 top-DTC price-weak minus top-DTC | 21d | +0.281 | 0.77 | 1.0 | -0.06 / +0.59 | NO |
| H2 top-DTC price-strong minus top-DTC | 21d | +0.240 | 0.98 | 0.656 | +0.31 / +0.17 | yes |
| H0 high-DTC minus low-DTC | 63d | +0.959 | 1.01 | 0.4697 | -0.29 / +2.09 | NO |
| H1 top-DTC price-weak minus top-DTC | 63d | +0.872 | 0.93 | 1.0 | -0.83 / +2.42 | NO |
| H2 top-DTC price-strong minus top-DTC | 63d | +0.735 | 1.37 | 0.206 | +1.14 / +0.37 | yes |

## Verdict

**H0 DOES NOT REPLICATE (sign is positive, significant only in the WRONG direction) — per the prereg the branch tests H1/H2 are UNINTERPRETABLE and SP1-B is a NULL.**

H0 came out POSITIVE (high days-to-cover *out*performed low, +0.75pp at 21d / +0.96pp at 63d, t 2.09 / 1.01, q 0.0363 / 0.4697). The prereg's replication gate requires H0 to be NEGATIVE **and** significant, so it does not replicate and H1/H2 are uninterpretable. This must not be read as "high short interest is bullish": it is the signature of a universe and a sample that cannot see the effect.

## Why H0 does not replicate here — measured, not asserted

- **Survivorship.** Of names eligible pre-2021, 34.6% of the highest-DTC quintile are gone from the panel by 2025. The price panel is the CURRENT universe, so the high-DTC names that went to zero — precisely the population that carries the effect — are absent. This biases H0 positive.
- **Universe.** The study sees 1289 names against 5616 eligible; coverage by DTC quintile is {0: 11.3, 1: 21.9, 2: 35.0, 3: 29.0, 4: 23.1} percent — a large/mid-cap watchlist, while the documented effect concentrates in small and illiquid names. The sort still has real spread (6.9x top/bottom quintile vs 7.8x in the full universe), so this is a population difference, not a dead sort.
- **Post-publication decay.** The result published in 2015; this sample is 2018-2026, entirely post-publication, where McLean-Pontiff-class haircuts run 26-58%.

All three push the same direction, and each one on its own is enough to account for H0 failing to appear in the hypothesised direction here.

## What this does and does not license

- It does **not** license a squeeze product, a short-pressure ranking, or any authority. H2 (the squeeze branch) reached q=0.206 at 63d with halves +1.14 / +0.37 (same sign: yes), and 0.73pp is far below the +/-5pp promotion bar. Pre-declared expectation was null; it is null.
- It does **not** overturn the published result. The honest statement is that this universe cannot test it.
- It **does** name the remaining fix: a delisting-inclusive price panel (`collectors/edgar_delisting.py` + `edgar_deadname_prices.py` exist) and a wider universe, for survivorship. The trading-day price index (prereg §5C) is in place — `calendar_audit` reads 0 weekend rows and 21/63 true sessions. Until survivorship is fixed, short pressure stays display-tier context here.
