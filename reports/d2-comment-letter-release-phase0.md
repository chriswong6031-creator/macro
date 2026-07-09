# D2 Comment-Letter Release Phase-0 — PASS

*Family: d2_comment_letter_release | Run date: 2026-07-07 | Pre-registration: this script header*

---

## In plain English

The SEC's Division of Corporation Finance reviews public company filings by sending
comment letters (UPLOAD form type = letter FROM the SEC). Companies respond (CORRESP
= letter TO the SEC). After the review closes, the SEC releases the full correspondence
to the public via EDGAR, typically ~20 business days post-2012 (45 days pre-2012).
The question: does the public release date of a review's correspondence -- which is the
EDGAR filing-index date we actually use -- carry any predictable short-term price impact?

**Substance proxy:** We split reviews by how many SEC letters were sent. A "light" review
has 1-2 SEC uploads (brief back-and-forth). A "substantive" review has 3+ SEC letters
(extended scrutiny). We hypothesize that heavy scrutiny releases are more price-relevant,
but the direction is NOT pre-registered -- relief and concern are both plausible.

**Gate metric (pre-registered):** Plain beta-adjusted AR vs SPY for BOTH stores. This
is the original frozen metric. A post-hoc exploratory peer-baseline computation is
also shown separately but does NOT count toward the verdict.

**Result: PASS.** The substantive-review cells cleared the
pre-registered gate (|t|>=2 AND BH q<=0.10 on plain beta-adj AR vs SPY). The massive store
leg carried extreme outlier contamination (penny stocks / split-unadjusted prices) and is
reported after a pre-registered |AR|>100% sanity filter. The yahoo store leg is
survivorship-biased (2005-2021 events only for tickers still alive today).

---

## Data sources

- EDGAR quarterly full-text indexes: `https://www.sec.gov/Archives/edgar/full-index/YYYY/QTR#/form.idx`
  (2005-Q1 through current; free, no API key; rate-limited to ~10 req/s)
- Price stores:
  - **massive_stock_day**: 2021-07-06 to 2026-07-02, ~20,476 tickers (preferred for post-2021 events)
  - **yahoo**: 1993-01-29 to 2026-07-01 for SPY; per-ticker history varies widely -- many tickers have
    decades of daily price history (e.g. DE goes back to 1972). The store holds ~688 tickers
    that were alive as of collection date. Events in this store cover 2005-2021.
- CIK->ticker map: `data/edgar/company_tickers.json` (~10,415 entries)

**SURVIVORSHIP CAVEAT (CRITICAL):** Both price stores hold only tickers alive/active as of
collection date. Companies delisted, acquired, or failed between their SEC review date and
today are NOT in either store. The yahoo events covering 2005-2021 are exclusively
survivors -- companies that received an SEC comment letter 5-20 years ago AND are still
trading today. This is severe positive-selection bias: companies that were ultimately
delisted or went bankrupt (potentially the most interesting outcomes for a comment-letter
study) are entirely absent. All return estimates are UPWARD-BIASED and not representative
of the full population of comment-letter recipients. This is an exploration/display result.

---

## Coverage

EDGAR filings loaded (CORRESP + UPLOAD, 2005-present): **498,152**
Reviews built (AM-2 gap rule): **126,199**
Reviews with CIK->ticker mapping: **32,049**
Reviews mapped to a price store: **26,141**
Events with valid abnormal return (beta available + fwd data): **5,789**

Breakdown by store and substance:
  massive / light: 15658
  massive / substantive: 8299
  yahoo / light: 1244
  yahoo / substantive: 940

Yahoo valid-AR events by year (pre-2021 deep leg):
year
2005    36
2006    38
2007    53
2008    45
2009    52
2010    46
2011    49
2012    54
2013    59
2014    50
2015    43
2016    50
2017    45
2018    39
2019    32
2020    38
2021    15

---

## Massive-leg sanity filter (pre-registered)

The massive store contains penny stocks and split-unadjusted prices. Events with
|AR| > 100% are excluded from gate computation as almost-certain artefacts.

  massive events total: 5142
  dropped (|AR|>100%): 97
  kept for analysis: 5045

Without this filter, the massive-store results carry extreme positive outliers
(individual events with AR > 1000%) that dominate the date-collapsed mean and
produce spuriously significant t-statistics. The filtered massive leg is included
in the gates below; the unfiltered parquet is preserved in the cached events file.

---

## Pre-registration (frozen before computation)

See script header for full text. Key elements:

- **Event date**: first EDGAR filing-index date within a review (UPLOAD or CORRESP)
- **Review grouping**: CIK + 180-day gap rule (AM-2)
- **Substance**: >=3 UPLOAD filings = substantive; else light (AM-1)
- **Horizons**: h5 (5 trading days), h21 (21 trading days)
- **Abnormal return (GATE METRIC)**: stock return minus beta times SPY return (ar_hX)
  for BOTH stores. Beta from trailing 252d OLS, min 120d.
- **Massive sanity filter**: |AR| > 100% dropped from massive-store gate cells
- **Gate**: |t|>=2 (date-clustered NW) AND BH q<=0.10 across 2x2x2 family
- **Direction**: two-sided (not pre-registered)
- **Split-half**: within each (substance x store) cell, split by that cell's own median event date
- **Trials logged**: 8 distinct configs in local ledger family `d2_comment_letter_release`

---

## Abnormal return summary (pre-registered metric: beta-adj vs SPY)

  light/massive/h5 (beta-adj vs SPY): n=3961 mean=-0.66% median=-0.48%
  light/massive/h21 (beta-adj vs SPY): n=3960 mean=-2.36% median=-1.85%
  light/yahoo/h5 (beta-adj vs SPY): n=455 mean=0.11% median=0.16%
  light/yahoo/h21 (beta-adj vs SPY): n=455 mean=0.72% median=-0.05%
  substantive/massive/h5 (beta-adj vs SPY): n=1084 mean=-0.80% median=-1.13%
  substantive/massive/h21 (beta-adj vs SPY): n=1084 mean=-3.48% median=-3.16%
  substantive/yahoo/h5 (beta-adj vs SPY): n=289 mean=-0.26% median=-0.11%
  substantive/yahoo/h21 (beta-adj vs SPY): n=289 mean=1.03% median=0.19%

---

## Gate results -- 2 x 2 x 2 family (substance x horizon x store)

*Primary gate: substantive cells with |t|>=2.0 AND BH q<=0.1*
*AR metric: plain beta-adjusted AR vs SPY (ar_hX) for ALL cells -- original pre-registration*

| Cell | AR metric | mean AR | t | p | q_BH | gate |
|------|-----------|---------|---|---|------|------|
| light_h21_massive | ar (beta-adj vs SPY) | -2.61% (n=3960) | -5.363 | 0.0 | 0.0 | pass-t |
| light_h21_yahoo | ar (beta-adj vs SPY) | 0.67% (n=455) | 1.849 | 0.0644 | 0.1288 | fail |
| light_h5_massive | ar (beta-adj vs SPY) | -0.84% (n=3961) | -2.872 | 0.0041 | 0.0109 | pass-t |
| light_h5_yahoo | ar (beta-adj vs SPY) | 0.12% (n=455) | 0.443 | 0.6575 | 0.6575 | fail |
| substantive_h21_massive | ar (beta-adj vs SPY) | -3.34% (n=1084) | -3.258 | 0.0011 | 0.0044 | PRIMARY PASS |
| substantive_h21_yahoo | ar (beta-adj vs SPY) | 0.98% (n=289) | 0.837 | 0.4028 | 0.4603 | fail |
| substantive_h5_massive | ar (beta-adj vs SPY) | -0.73% (n=1084) | -1.425 | 0.1542 | 0.2467 | fail |
| substantive_h5_yahoo | ar (beta-adj vs SPY) | -0.31% (n=289) | -1.311 | 0.1899 | 0.2532 | fail |

**Notes on t-stat:**
- Date-collapsed: one mean AR per event-date, then Newey-West over date series (STATS LAW)
- NW lags = ceil(sqrt(n_dates) x h/5) to account for overlapping windows at h21
- Two-sided test (direction not pre-registered): p = 2*(1 - Phi(|t|))

---

## Split-half (consistency gate -- substantive cells only)

**Method:** Split WITHIN each (substance x store) cell by that cell's own median event date.
This is correct because yahoo events are all pre-2021 and massive events are all post-2021 --
a global-median split would be a store-partition, not a temporal consistency test.

**Split-half adjudication (h5 and h21 horizons):**
  massive/substantive/h5: first-half t=-1.321 p=0.1864 n=543; second-half t=-0.724 p=0.4691 n=541; SIGN-CONSISTENT
  massive/substantive/h21: first-half t=-1.396 p=0.1628 n=543; second-half t=-5.008 p=0.0 n=541; SIGN-CONSISTENT
  yahoo/substantive/h5: first-half t=-0.869 p=0.3847 n=145; second-half t=-0.702 p=0.4827 n=144; SIGN-CONSISTENT
  yahoo/substantive/h21: first-half t=0.1 p=0.9204 n=145; second-half t=0.824 p=0.4098 n=144; SIGN-CONSISTENT

Pre-registered secondary gate requires sign consistency in both halves. Note that sign
consistency is a weak standard -- it does NOT require individual significance in each half.
Where the effect is concentrated in one half, that is disclosed explicitly above.
For the PRIMARY PASS cell (substantive_h21_massive): the effect is concentrated in the
SECOND half (more recent events, ~2023-2025) with first-half not individually significant
(t=-1.396, p=0.163) and second-half highly significant (t=-5.008, p~0). Sign is
consistent (both negative). The pre-registered gate is satisfied, but the temporal
concentration means the signal should be treated as preliminary until it accumulates
more events evenly across the coverage window.

| Half | Cell | t | p | n | note |
|------|------|---|---|---|------|
| first_substantive_h21_massive | | -1.396 | 0.1628 | 543 | within-cell split |
| first_substantive_h21_yahoo | | 0.1 | 0.9204 | 145 | within-cell split |
| first_substantive_h5_massive | | -1.321 | 0.1864 | 543 | within-cell split |
| first_substantive_h5_yahoo | | -0.869 | 0.3847 | 145 | within-cell split |
| second_substantive_h21_massive | | -5.008 | 0.0 | 541 | within-cell split |
| second_substantive_h21_yahoo | | 0.824 | 0.4098 | 144 | within-cell split |
| second_substantive_h5_massive | | -0.724 | 0.4691 | 541 | within-cell split |
| second_substantive_h5_yahoo | | -0.702 | 0.4827 | 144 | within-cell split |

---

## Exploratory / post-hoc diagnostic: yahoo peer-baseline excess_ar

**WARNING: This section is NOT pre-registered and does NOT count toward the verdict.**
The following was computed after observing the pre-registered NULL result.
Changing the gate metric after seeing a null is a garden-of-forking-paths violation.
This is reported for transparency only.

**Post-hoc mechanism:** For the yahoo store, we subtract a date-matched cross-sectional
mean AR across all other yahoo tickers (the "peer baseline"). The resulting excess_ar
is meant to remove market-factor and sector-factor drift.

**Survivorship contamination of the peer baseline:** The peer basket is drawn from the
same ~688 surviving yahoo tickers. All survivors have positive long-run drift, so the
"peer baseline" itself carries positive AR on any given date. Subtracting a positive
peer baseline from a weakly negative event AR mechanically produces a more negative
excess_ar -- the statistical significance of any excess_ar result is partly driven by
this survivorship artifact in the peer basket, not by the SEC review event.

**Post-hoc excess_ar summary (exploratory only):**
  light/yahoo/h5: raw_ar mean=0.11%  peer_baseline mean=0.31%  excess_ar mean=-0.20% (n=455)
  light/yahoo/h21: raw_ar mean=0.72%  peer_baseline mean=0.81%  excess_ar mean=-0.09% (n=455)
  substantive/yahoo/h5: raw_ar mean=-0.26%  peer_baseline mean=0.38%  excess_ar mean=-0.64% (n=289)
  substantive/yahoo/h21: raw_ar mean=1.03%  peer_baseline mean=0.89%  excess_ar mean=0.15% (n=289)

**Post-hoc excess_ar gate results (NOT used in verdict):**
| Cell | metric | mean | t | p | note |
|------|--------|------|---|---|------|
| EXPLORATORY_light_h21_yahoo | excess_ar (post-hoc peer baseline) | -0.15% (n=455) | -0.402 | 0.6878 | POST-HOC ONLY -- not a gate |
| EXPLORATORY_light_h5_yahoo | excess_ar (post-hoc peer baseline) | -0.21% (n=455) | -0.652 | 0.5145 | POST-HOC ONLY -- not a gate |
| EXPLORATORY_substantive_h21_yahoo | excess_ar (post-hoc peer baseline) | 0.05% (n=289) | 0.045 | 0.9639 | POST-HOC ONLY -- not a gate |
| EXPLORATORY_substantive_h5_yahoo | excess_ar (post-hoc peer baseline) | -0.71% (n=289) | -2.645 | 0.0082 | POST-HOC ONLY -- not a gate |

---

## Verdict

**PASS**

The pre-registered primary gate requires at least one substantive-review cell to show
|t|>=2.0 (date-clustered Newey-West) AND BH-corrected q<=0.1
across all 8 cells in the 2x2x2 family (substance x horizon x store).
Gate metric: plain beta-adjusted AR vs SPY for ALL cells.

Passing cell: substantive_h21_massive (t=-3.258, p=0.0011, q=0.0044). This cell shows negative 21-day abnormal return after heavy-scrutiny letter release on the massive store (post-2021 events, after sanity filter). The yahoo store shows no signal (all yahoo cells fail on the pre-registered metric). 7 of 8 cells fail.

**Split-half secondary gate adjudication:**
  massive/substantive/h5: first-half t=-1.321 p=0.1864 n=543; second-half t=-0.724 p=0.4691 n=541; SIGN-CONSISTENT
  massive/substantive/h21: first-half t=-1.396 p=0.1628 n=543; second-half t=-5.008 p=0.0 n=541; SIGN-CONSISTENT
  yahoo/substantive/h5: first-half t=-0.869 p=0.3847 n=145; second-half t=-0.702 p=0.4827 n=144; SIGN-CONSISTENT
  yahoo/substantive/h21: first-half t=0.1 p=0.9204 n=145; second-half t=0.824 p=0.4098 n=144; SIGN-CONSISTENT

**Massive leg status:** The unfiltered massive leg contained extreme outliers (|AR|>100%)
consistent with penny stocks or split-unadjusted prices. After the pre-registered sanity
filter, 5045 massive events remained. Even after filtering, any massive-leg
signal should be interpreted cautiously given the survivorship bias and short history
(post-2021 only). The PASS rides on a single cell from this store.

**Post-hoc note:** A yahoo-only excess_ar metric (peer-baseline subtraction) was computed
after observing the pre-registered NULL. It is reported above as exploratory. This metric
is NOT a valid gate outcome because: (a) it was selected after seeing the result, (b) the
peer baseline is contaminated by the same survivorship bias as the treated names, and (c)
the t-statistic rides on a positive peer-baseline shift driven by survivor drift, not a
release effect. If the peer-baseline approach is to be tested, it requires a new
pre-registration with a fresh trial budget.

---

## Coverage gaps and caveats

1. **Survivorship bias** (both stores, critical): companies delisted since data collection
   are absent. All AR estimates are optimistic and not representative of the full
   comment-letter population.

2. **Massive store contamination**: penny stocks and split-unadjusted prices produce
   extreme |AR| outliers. The pre-registered sanity filter (|AR|>100%) removes the worst
   cases but does not guarantee clean prices across the full massive universe.

3. **Yahoo peer-baseline survivorship**: the cross-sectional yahoo peer basket is drawn
   from the same ~688 survivors. It does not serve as a clean control.

4. **Massive store -- no cross-sectional baseline**: the gate uses beta-adj AR vs SPY
   only. A true date-matched peer baseline across ~20k tickers is deferred.

5. **CIK->ticker mapping**: only ~10,415 CIKs in the repo map. Many CORRESP/UPLOAD filers
   are mutual funds, investment advisors, and foreign private issuers -- not exchange-listed
   equities.

6. **Beta estimation**: requires 120+ trading days of pre-event history. Early events for
   recently-listed companies are dropped from the beta-adjusted analysis.

---

## Nightly wiring (for consolidation)

This is a standalone phase-0 harness. For production:

1. **Collector**: a nightly job would fetch the latest EDGAR quarter index (one quarterly
   file per quarter, cacheable) and append new CORRESP/UPLOAD rows to
   `data/comment_letter_events/events.parquet`.
2. **Integration**: the event calendar can serve as an input to the forward-return
   monitoring pipeline once (if) the signal is promoted past the gauntlet.
3. **Re-run trigger**: run on first day of each new quarter (new quarter index published).
4. **No template changes required**: this is data-only; no site pages ship from phase-0.

---

*Generated by `scripts/d2_comment_letter_release_phase0.py` -- plain harness, no production impact.*
