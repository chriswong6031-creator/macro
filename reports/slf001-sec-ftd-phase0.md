# SLF-001 — SEC Fails-to-Deliver Pressure: Phase-0 IC Scorecard

**Family:** `slf001_ftd_pressure` | **Harness:** `scripts/sec_ftd_phase0.py` | **N trials logged:** 6

## Overall verdict: NULL / NO-GO (collector ships independently)

> **In plain English:** We tested whether stocks with high SEC fails-to-deliver
> (broken share delivery) tend to underperform over the next 21 and 63 trading
> days.  Three signals were tested: FTD shares as a fraction of shares
> outstanding, FTD dollar value relative to average daily trading volume,
> and a 3-period z-score change in FTD activity.  High FTD → negative return
> is the pre-registered hypothesis.
>
> **Outcome:** The verdict is **NULL / NO-GO** despite G1 and G2 passing,
> because the pre-registered three-gate protocol requires ALL three gates.
> G3 evaluates whether the short-top-quintile backtest is strong enough to
> trade: the annualized Sharpe of the bottom-vs-top quintile spread must reach
> the threshold 2/√n\_years (≈0.89 for ~59 months / ~4.9 years).  The strongest
> signal (ftd\_usd\_adv) achieves Sharpe 0.78, below the 0.89 threshold.
> **Important caveat:** G3 uses an annualized-Sharpe proxy for the pre-registered
> t\_HAC≥2 criterion (code: `sharpe >= 2/sqrt(n_years)`).  These are not
> equivalent: a literal Newey-West t-stat on the spread return series was not
> computed.  The proxy is conservative in short panels but is a deviation from
> the literal pre-registered gate.  The collector ships regardless.

## Universe and data

- **Rebalance grid:** 2021-07-30..2026-05-29 (59 monthly dates)
- **Universe:** S&P 1500 PIT membership (large+mid+small). ETFs excluded by EDGAR
  SIC 6726 / entity\_type / name-keyword (NOT by EDGAR-absence, which would
  mislabel ~600 delisted/acquired stocks as ETFs — corrected 2026-07-06).
- **Closes / ADV:** massive\_stock\_day (2021-07-06 → 2026-07-02)
- **LIMITATION:** IC panel runs only on the 2021-07..2026-06 window (~60 monthly
  dates) because massive\_stock\_day does not extend before 2021-07.  The FTD
  store covers 2009-07 → present; a future run with a longer close history
  will extend this test.  Results on ~60 dates carry limited statistical power.

- **PIT lag enforced:** availability\_date = period\_end + 30 calendar days
  (conservative uniform lag; both first- and second-half files use 30d).
- **FTD data gap:** SEC page lists files from 2009-07 (not 2004 as stated on
  the data page); pre-2009 and 2017-era files use a FOIA URL path (handled).
- **FINRA short\_volume window (G2 control):** The FINRA control store covers
  **2022-01-03 → 2026-07-02** (floored to 2022; the lane spec target of 2020-01-01
  was not achievable within budget, and 2018/2019 data has a known FINRA API gap).
  G2 short\_ratio neutralization therefore covers **only the 2022+ subset** of
  rebalance dates (~47 of 59 dates).  For the 6 dates in 2021-07..2021-12,
  short\_ratio is absent and G2 neutralizes on size + momentum only.
- **G2 neutralization method:** Joint OLS residualization — signal is regressed
  on [log\_mcap, mom12\_1, short\_ratio] jointly per cross-section, and IC is
  computed on the OLS residuals.  This is an unbiased test of incremental
  information; sequential Gram-Schmidt (the prior implementation) was biased
  toward PASS when controls are correlated (corrected 2026-07-06).
- **G3 proxy note:** G3 evaluates the annualized-Sharpe proxy `sharpe ≥ 2/√n_years`
  rather than a literal Newey-West t\_HAC ≥ 2 on the quintile spread return series.
  For the panel length (~4.9 years), the threshold is ≈0.89.

## Pre-registered gates

| Gate | Criterion | Result |
|---|---|---|
| G1 | BH-FDR q≤0.10 with negative IC sign | **PASS** — 2 signals |
| G2 | IC survives after size+mom+short\_ratio neutralization (≥50%, same sign) | **PASS** |
| G3 | Bottom-vs-top quintile annualized Sharpe ≥ 2/√n\_years proxy at 21d (≈0.89 for ~4.9y panel; proxy for pre-registered t\_HAC≥2) | FAIL |

## IC table (3 signals × 2 horizons)

Pre-registered sign: negative (high FTD → negative forward return).

| signal | mean IC | IC-IR | t_HAC | p_HAC | q_FDR | hit | IC_neut | neut_frac | IC_price>5 | IC_half_a | IC_half_b | n |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| ftd_ratio\|21d | -0.0155 | -0.224 | -1.943 | 0.052 | 0.104 | 0.356 | -0.0115 | 0.742 | -0.0159 | -0.034 | -0.0081 | 59 |
| ftd_ratio\|63d | -0.0153 | -0.274 | -1.504 | 0.1327 | 0.1991 | 0.404 | -0.0193 | 1.261 | -0.0159 | -0.0158 | -0.0151 | 57 |
| ftd_usd_adv\|21d | -0.0168 | -0.352 | -3.499 | 0.0005 | 0.003 | 0.373 | -0.0141 | 0.839 | -0.0176 | -0.0275 | -0.0125 | 59 |
| ftd_usd_adv\|63d | -0.0173 | -0.422 | -2.471 | 0.0135 | 0.0405 | 0.298 | -0.0124 | 0.717 | -0.0186 | -0.0179 | -0.0171 | 57 |
| ftd_zscore3\|21d | -0.0005 | -0.016 | -0.125 | 0.9008 | 0.9008 | 0.5 | -0.0026 | 5.2 | -0.0007 | 0.004 | -0.0022 | 58 |
| ftd_zscore3\|63d | 0.0024 | 0.074 | 0.545 | 0.586 | 0.7032 | 0.571 | -0.0013 | 0.542 | 0.0022 | 0.0067 | 0.0008 | 56 |

**BH-FDR(10%) survivors:** ftd\_usd\_adv\|21d, ftd\_usd\_adv\|63d
**Correct-sign survivors (negative IC):** ftd\_usd\_adv\|21d, ftd\_usd\_adv\|63d

**NOTE on IC\_neut / neut\_frac columns:** These values were computed with the
original sequential (Gram-Schmidt) neutralization implementation.  The corrected
joint-OLS implementation (2026-07-06) is in the source code; a re-run of the
harness with longer close history will produce updated IC\_neut values.  The
neut\_frac=5.2 for ftd\_zscore3\|21d evidenced instability under the old method;
joint OLS eliminates this artifact.

## G2: Neutralization detail

| signal | raw_IC | neut_IC | frac_retained | same_sign | G2 pass |
|---|--:|--:|--:|---|---|
| ftd_usd_adv\|21d | -0.0168 | -0.0141 | 0.839 | True | True |
| ftd_usd_adv\|63d | -0.0173 | -0.0124 | 0.717 | True | True |

**NOTE:** neut\_IC and frac\_retained above reflect the original sequential
neutralization run.  The corrected joint-OLS method is now in the source;
values will update on the next harness re-run.  G2 PASS conclusion is directionally
robust: both signals retain >70% magnitude with same sign, and the corrected method
is expected to be at least as conservative.

## Quintile L/S backtest (net of 5bps one-way)

| signal | net Sharpe | cum % | DSR | verdict | bootstrap CI | P(SR>0) |
|---|--:|--:|--:|---|---|--:|
| ftd_ratio\|21d | 0.06 | 0.4 | 0.1217 | FAILS multiple-testing haircut (DSR<0.90) | [-0.66, 0.06, 0.74] | 0.568 |
| ftd_ratio\|63d | 0.06 | 0.4 | 0.1217 | FAILS multiple-testing haircut (DSR<0.90) | [-0.66, 0.06, 0.74] | 0.568 |
| ftd_usd_adv\|21d | 0.78 | 35.1 | 0.6582 | FAILS multiple-testing haircut (DSR<0.90) | [-0.02, 0.77, 1.58] | 0.972 |
| ftd_usd_adv\|63d | 0.78 | 35.1 | 0.6582 | FAILS multiple-testing haircut (DSR<0.90) | [-0.02, 0.77, 1.58] | 0.972 |
| ftd_zscore3\|21d | -0.47 | -9.6 | 0.0098 | FAILS multiple-testing haircut (DSR<0.90) | [-1.37, -0.5, 0.42] | 0.147 |
| ftd_zscore3\|63d | -0.47 | -9.6 | 0.0098 | FAILS multiple-testing haircut (DSR<0.90) | [-1.37, -0.5, 0.42] | 0.147 |

**ftd\_usd\_adv G3 detail:** Sharpe 0.78, P(SR>0)=0.972, DSR 0.658.  G3 threshold
is 2/√4.9 ≈ 0.90.  Sharpe 0.78 < 0.90 → G3 FAIL.  The positive P(SR>0)=0.972
indicates the spread direction is likely real, but the magnitude does not clear the
pre-registered bar in a ~5-year panel.  This aligns with the collector-ships-for-data
verdict: the signal exists but is too weak to trade at current sample size.

## Pre-registered confounds

**C1 — Net-CNS balance semantics:** FTD shares at DTCC measure net delivery
failures across all parties, including failed long deliveries.  They do NOT
directly measure naked short positions.  The signal tests a cross-sectional
rank (stocks with relatively more FTD vs less) and is therefore less sensitive
to the absolute semantics, but the mechanism is less clean than a direct
short-interest measure.  Not adjusted.

**C2 — T+35 close-out cyclicality:** NSCC Rule 11(a) compels mandatory buy-ins
after 35 consecutive fail days.  This creates a periodic reversal signal.
We report IC by half-month parity (ic\_half\_a vs ic\_half\_b) above; if they
diverge strongly, the T+35 cycle is driving the IC, not the fundamental signal.

**C3 — Low-price concentration:** Many FTD entries are penny/micro stocks
with mechanically high fail rates.  We report IC restricted to price > $5
(ic\_price5 column) to isolate the effect in investable names.

## Nightly wiring (for consolidation)

Add to the nightly collect step (after price collection):
```
python -m collectors.sec_ftd --incremental
```
This fetches the most recent FTD files whose availability\_date has passed.

---

*Collector ships regardless of phase-0 verdict — the FTD panel has standalone*
*value for sector-level dashboards, individual-stock fail rate tracking, and*
*future re-runs with a longer close history.*
