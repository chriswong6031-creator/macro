# SLF-006 Auction Absorption — Phase-0 Event Study

> **Verdict: NULL / NO-GO**

## In plain English

Treasury auctions happen several times a week. Strong demand (measured
by bid-to-cover ratio, how much foreigners buy, and how little dealers
are stuck with) might predict that bond prices rise afterward — or it
might not, because smart investors often pre-position BEFORE the auction.
This study checks whether the absorption score already computed on bonds.html
has any forward-return signal. A PASS means we can move it toward a
registered forward signal; a FAIL means it stays context-only.

## Setup

- **Engine**: `engine/treasury_supply._prep` + `_score_rows` (no math forked)
- **Tenor buckets**: belly (2y/3y/5y/7y) → IEF; long (10y/20y/30y) → TLT
- **PIT discipline**: auction results published ~13:00 ET auction day;
  enter on **close of auction day** (t=0)
- **Event windows**: t+1, t+5, t+21 trading days
- **Quintile contrast**: Q5 (absorption_z top-20%) minus Q1 (bottom-20%)
- **IC**: pooled Spearman of absorption_z vs forward return (HAC NW t-stat)
- **Vol control**: MOVE index present on disk; used in conditioning notes
- **Duration conditioning (G2)**: TLT 50dma above/below split

## Data

- Auctions: 413 scored coupon auctions after engine scoring
  (belly=168,
  long=245)
- Date range: 2016-12-13 – 2026-06-25

## Pre-registered gates

| Gate | Criterion | Result |
| ---- | --------- | ------ |
| G1 | \|t_HAC\| ≥ 2.0 at ≥1 horizon with BH-FDR q ≤ 0.10 | **FAIL** |
| G2 | Same-sign Q5-Q1 contrast in TLT above/below 50dma | **PASS** |
| G3 | Split-half same-sign (first vs second half of history) | **FAIL** |

## Results by cell

### Quintile contrast (Q5-Q1 gross return spread, %)

| Cell | n | Q1 mean% | Q5 mean% | Spread% | t_HAC | p_HAC | BH-q | BH-reject |
| ---- | - | -------- | -------- | ------- | ----- | ----- | ---- | --------- |
| belly_t1 | 168 | 0.128 | -0.018 | -0.146 | -1.08 | 0.280 | 0.4198 | False |
| belly_t5 | 168 | 0.664 | 0.057 | -0.607 | -2.20 | 0.028 | 0.1662 | False |
| belly_t21 | 164 | 0.517 | -0.489 | -1.005 | -1.69 | 0.091 | 0.1890 | False |
| long_t1 | 245 | 0.061 | 0.103 | +0.042 | 0.28 | 0.781 | 0.7814 | False |
| long_t5 | 245 | -0.054 | -0.176 | -0.122 | -0.32 | 0.747 | 0.7814 | False |
| long_t21 | 242 | 0.177 | -1.218 | -1.395 | -1.67 | 0.095 | 0.1890 | False |

### Continuous Spearman IC

| Cell | n | IC | t_HAC | p_HAC |
| ---- | - | -- | ----- | ----- |
| belly_t1 | 168 | -0.1011 | -1.31 | 0.192 |
| belly_t5 | 168 | -0.1382 | -1.75 | 0.080 |
| belly_t21 | 164 | -0.2118 | -2.45 | 0.014 |
| long_t1 | 245 | 0.0052 | 0.09 | 0.927 |
| long_t5 | 245 | -0.0307 | -0.54 | 0.592 |
| long_t21 | 242 | -0.0928 | -1.40 | 0.162 |

## Statistical caveats

### 1. Contrast t-stat construction (corrected from original build)

The Q5-Q1 t-statistics reported here use a proper **two-sample standard
error**: `sqrt(lrv_q5/n_q5 + lrv_q1/n_q1)`, where each arm's long-run
variance is estimated via Newey-West (Bartlett kernel, lag=4).  The
original build used `newey_west_tstat(q5.values - q1.mean(), lags=4)`,
which treats `q1.mean()` as a variance-free constant.  That formulation
omits Q1's sampling variance and roughly doubles the reported |t|
(e.g., original belly_t5 t_HAC = -4.14 corrects to -2.20 with the
proper two-sample SE).  The NULL/NO-GO verdict is unchanged: with
corrected t-stats no cell clears BH-FDR q ≤ 0.10 (G1 now FAIL as well
as G3), making the null more robust, not less.

### 2. HAC-overlap caveat

The Newey-West lag=4 is a **fixed constant, not scaled to the horizon**.
Within a single quintile (~N/5 members), auctions are temporally sparse
(months apart), so lag=4 corrects little real serial dependence — the
quintile-subset HAC is near-iid by construction.  The overlap that matters
(t+21 forward-return windows that span 2-3 subsequent same-tenor auctions)
lives in the pooled calendar series, not the quintile subset.  For the
t+21 horizon, a horizon-scaled lag (>=21 trading days ≈ 4-5 auctions)
would be more principled; the fixed lag=4 is conservative for t+1/t+5 and
may be slightly under-corrected for t+21.  The primary multiple-testing
guard is BH-FDR across 6 pre-declared cells, not the lag parameter.

### 3. Duration-proxy mismatch (belly bucket)

Of the 168 belly auctions, approximately **51 are 2y or 3y tenors** mapped to IEF (iShares 7-10y
Treasury ETF) — a material duration mismatch.  A 2y or 3y auction probes
the short end of the curve, but IEF's effective duration is ~7 years.
These instruments share broad macro direction but differ substantially in
convexity and rate sensitivity.  The null result for the belly bucket
should **not** be over-read as a clean test of short-tenor absorption
signal: it is partly a test of whether short-tenor auction strength
predicts 7-10y ETF returns, which is a weaker and noisier hypothesis.
A cleaner test would use SHY (1-3y) or IEI (3-7y) for the 2y-3y subset.

## Gate detail

### G1 — HAC t-stat + BH-FDR

Passing cells at |t_HAC| ≥ 2.0 and BH-q ≤ 0.10: **none**
G1 result: **FAIL**

### G2 — Duration-trend conditioning (TLT above/below 50dma)

| Sub-cell | TLT above-50dma IC | TLT below-50dma IC | Same sign |
| -------- | ------------------ | ------------------- | --------- |
| belly_t5 | -0.0685 | -0.1910 | Yes |
| long_t5 | -0.0390 | -0.0290 | Yes |
| long_t21 | -0.0807 | -0.1123 | Yes |

G2 result: **PASS** (3/3 same-sign, need ≥2)

### G3 — Split-half same-sign

| Bucket | Metric | H1 IC | H2 IC | Same sign |
| ------ | ------ | ----- | ----- | --------- |
| belly | t+5 | -0.2829 | 0.0070 | No |
| belly | t+21 | -0.3730 | 0.0136 | No |
| long | t+5 | -0.0320 | -0.0403 | Yes |
| long | t+21 | -0.0862 | -0.1039 | Yes |

G3 result: **FAIL** (2/4 same-sign, need ≥3)

## Multiple-testing / Deflated Sharpe

- Total pre-registered trials (logged before any backtest): 12
- Best-cell daily SR: 0.2128
- Deflated Sharpe (P[true SR > 0]): 0.8792
  - full DSR: sr0_annual=1.98, n_trials=12

## Verdict and recommendation

**Overall: NULL / NO-GO**

At least one gate failed. The absorption engine output remains
context-only on bonds.html. No scoring, no MRS leg.

**Limitations of this null:**

1. **Duration-proxy mismatch**: ~51 of 168 belly auctions are 2y/3y
   tenors mapped to IEF (7-10y ETF). This is a material mismatch —
   the null for the belly bucket is partly a test of whether
   short-tenor absorption predicts 7-10y returns, a weaker hypothesis.
   See the 'Statistical caveats' section above.
2. **Panel length**: 413 scored auctions over ~10 years; a longer panel
   would reduce quintile-arm standard errors appreciably.
3. **Metric reformulation**: the absorption_z aggregates three demand
   sub-signals (bid-to-cover, indirect, dealer) with equal weight.
   A sub-signal decomposition or a tail/cover-only variant might recover
   signal that the composite obscures.

## Nightly wiring (for consolidation)

None required — engine already runs nightly in the bonds build path.
This phase-0 uses no new collector. If a Phase-1 is commissioned,
a new harness would symlink the same treasury_auctions and yahoo stores.

## PIT publication-lag assumptions

| Series | Publication lag enforced |
| ------ | ------------------------ |
| Treasury auction results | ~13:00 ET same day; enter on CLOSE of auction day |
| TLT / IEF close prices | Same-day EOD; PIT-clean by construction |
| MOVE index | Same-day EOD; used for reference only |
| absorption_z | Computed from PRIOR auctions only (engine trailing window) |
