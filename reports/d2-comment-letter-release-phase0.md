# D2 Comment-Letter Release Phase-0 — PASS

*Family: d2_comment_letter_release | Run date: 2026-07-06 | Pre-registration: this script header*

---

## In plain English

The SEC's Division of Corporation Finance reviews public company filings by sending
comment letters (UPLOAD form type = letter FROM the SEC). Companies respond (CORRESP
= letter TO the SEC). After the review closes, the SEC releases the full correspondence
to the public via EDGAR, typically ~20 business days post-2012 (45 days pre-2012).
The question: does the public release date of a review's correspondence — which is the
EDGAR filing-index date we actually use — carry any predictable short-term price impact?

**Substance proxy:** We split reviews by how many SEC letters were sent. A "light" review
has 1-2 SEC uploads (brief back-and-forth). A "substantive" review has 3+ SEC letters
(extended scrutiny). We hypothesize that heavy scrutiny releases are more price-relevant,
but the direction is NOT pre-registered — relief and concern are both plausible.

**Baseline (AM-4):** For the yahoo store, we net out the date-matched cross-sectional mean
AR across all other yahoo tickers on the same event date (true peer baseline). For the
massive store, we use beta-adjusted AR vs SPY only (no cross-sectional peer baseline —
deferred per AM-4 due to the cost of pre-loading 20k tickers). Both are net-of-market
in spirit; the yahoo leg additionally removes any date-specific market factor.

**Result: PASS.** The substantive-review cells cleared the
pre-registered gate (|t|>=2 AND BH q<=0.10).

---

## Data sources

- EDGAR quarterly full-text indexes: `https://www.sec.gov/Archives/edgar/full-index/YYYY/QTR#/form.idx`
  (2005-Q1 through current; free, no API key; rate-limited to ~10 req/s)
- Price stores:
  - **massive_stock_day**: 2021-07-06 to 2026-07-02, ~20,476 tickers (preferred for post-2021 events)
  - **yahoo**: 1993-01-29 to 2026-07-01 for SPY; per-ticker history varies widely — many tickers have
    decades of daily price history (e.g. DE goes back to 1972). The store holds ~688 tickers
    that were alive as of collection date. Events in this store cover 2005-2021 with
    approximately 40-50 valid-AR events per year (total 729 pre-2021 events with valid AR).
- CIK→ticker map: `data/edgar/company_tickers.json` (~10,415 entries)

**SURVIVORSHIP CAVEAT (CRITICAL):** Both price stores hold only tickers alive/active as of
collection date. Companies delisted, acquired, or failed between their SEC review date and
today are NOT in either store. The 729 yahoo events covering 2005-2021 are exclusively
survivors — companies that received an SEC comment letter 5-20 years ago AND are still
trading today. This is severe positive-selection bias: companies that were ultimately
delisted or went bankrupt (potentially the most interesting outcomes for a comment-letter
study) are entirely absent. All return estimates are UPWARD-BIASED and not representative
of the full population of comment-letter recipients. This is an exploration/display result.

---

## Coverage

EDGAR filings loaded (CORRESP + UPLOAD, 2005–present): **498,152**
Reviews built (AM-2 gap rule): **126,199**
Reviews with CIK→ticker mapping: **32,049**
Reviews mapped to a price store: **26,141**
Events with valid abnormal return (beta available + fwd data): **5,886**

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

## Pre-registration (frozen before computation)

See script header for full text. Key elements:

- **Event date**: first EDGAR filing-index date within a review (UPLOAD or CORRESP)
- **Review grouping**: CIK + 180-day gap rule (AM-2)
- **Substance**: >=3 UPLOAD filings = substantive; else light (AM-1)
- **Horizons**: h5 (5 trading days), h21 (21 trading days)
- **Abnormal return**: stock return − beta × SPY return; beta from trailing 252d OLS, min 120d
- **Baseline**: yahoo = date-matched cross-sectional mean AR (AM-4); massive = beta-vs-SPY only (AM-4)
- **Gate**: |t|>=2 (date-clustered NW) AND BH q<=0.10 across 2×2×2 family
- **Direction**: two-sided (not pre-registered)
- **Split-half**: within each (substance x store) cell, split by that cell's own median event date
- **Trials logged**: 8 distinct configs in local ledger family `d2_comment_letter_release`

---

## Abnormal return summary (raw, pre-gate)

  light/massive/h5 (beta-adj vs SPY): n=4040 mean=6.36% median=-0.47%
  light/massive/h21 (beta-adj vs SPY): n=4039 mean=8.65% median=-1.68%
  light/yahoo/h5 (excess vs peer baseline): n=455 mean=-0.20% median=-0.16%
  light/yahoo/h21 (excess vs peer baseline): n=455 mean=-0.09% median=-0.72%
  substantive/massive/h5 (beta-adj vs SPY): n=1102 mean=1.89% median=-1.08%
  substantive/massive/h21 (beta-adj vs SPY): n=1102 mean=4.67% median=-3.00%
  substantive/yahoo/h5 (excess vs peer baseline): n=289 mean=-0.64% median=-0.56%
  substantive/yahoo/h21 (excess vs peer baseline): n=289 mean=0.15% median=-0.63%

---

## Gate results — 2 × 2 × 2 family (substance × horizon × store)

*Primary gate: substantive cells with |t|≥2.0 AND BH q≤0.1*
*AR metric: yahoo cells use excess_ar (event AR minus date-matched peer-baseline); massive cells use beta-adjusted AR vs SPY*

| Cell | AR metric | mean AR | t | p | q_BH | gate |
|------|-----------|---------|---|---|------|------|
| light_h21_massive | ar (beta-SPY) | 7.03% (n=4039) | 4.711 | 0.0 | 0.0 | pass-t |
| light_h21_yahoo | excess_ar (peer-baseline) | -0.15% (n=455) | -0.402 | 0.6878 | 0.7861 | fail |
| light_h5_massive | ar (beta-SPY) | 4.56% (n=4040) | 1.784 | 0.0744 | 0.1984 | fail |
| light_h5_yahoo | excess_ar (peer-baseline) | -0.21% (n=455) | -0.652 | 0.5145 | 0.686 | fail |
| substantive_h21_massive | ar (beta-SPY) | 3.55% (n=1102) | 1.428 | 0.1534 | 0.3068 | fail |
| substantive_h21_yahoo | excess_ar (peer-baseline) | 0.05% (n=289) | 0.045 | 0.9639 | 0.9639 | fail |
| substantive_h5_massive | ar (beta-SPY) | 1.13% (n=1102) | 1.197 | 0.2313 | 0.3701 | fail |
| substantive_h5_yahoo | excess_ar (peer-baseline) | -0.71% (n=289) | -2.645 | 0.0082 | 0.0328 | PRIMARY PASS |

**Notes on t-stat:**
- Date-collapsed: one mean AR per event-date, then Newey-West over date series (STATS LAW)
- NW lags = ceil(sqrt(n_dates) × h/5) to account for overlapping windows at h21
- Two-sided test (direction not pre-registered): p = 2*(1 - Phi(|t|))

---

## Split-half (consistency gate — substantive cells only)

**Method:** Split WITHIN each (substance x store) cell by that cell's own median event date.
This is correct because yahoo events are all pre-2021 and massive events are all post-2021 —
a global-median split would be a store-partition, not a temporal consistency test.
Within-cell split tests early-vs-late events within the same store's coverage window.

| Half | Cell | t | p | n | note |
|------|------|---|---|---|------|
| first_substantive_h21_massive | | 1.344 | 0.1788 | 552 | within-cell split |
| first_substantive_h21_yahoo | | -2.392 | 0.0168 | 145 | within-cell split |
| first_substantive_h5_massive | | -1.214 | 0.2248 | 552 | within-cell split |
| first_substantive_h5_yahoo | | -2.135 | 0.0327 | 145 | within-cell split |
| second_substantive_h21_massive | | 0.712 | 0.4762 | 550 | within-cell split |
| second_substantive_h21_yahoo | | 0.514 | 0.607 | 144 | within-cell split |
| second_substantive_h5_massive | | 1.975 | 0.0483 | 550 | within-cell split |
| second_substantive_h5_yahoo | | -1.422 | 0.155 | 144 | within-cell split |

---

## Verdict

**PASS**

The pre-registered primary gate requires at least one substantive-review cell to show
|t|≥2.0 (date-clustered Newey-West) AND BH-corrected q≤0.1
across all 8 cells in the 2×2×2 family (substance × horizon × store).

At least one cell cleared both thresholds.

---

## Coverage gaps and caveats

1. **Survivorship bias** (both stores, critical): companies delisted since data collection are absent.
   The 729 yahoo events covering 2005-2021 are exclusively survivors — the most serious selection
   issue is for companies that ultimately failed or were acquired after their SEC review.
   All AR estimates are optimistic and not representative of the full comment-letter population.

2. **Yahoo store price depth**: the yahoo per-ticker histories go back decades for many tickers
   (e.g. DE from 1972, SPY from 1993). The 729 pre-2021 yahoo events have real price coverage —
   approximately 36-59 valid-AR events per year across 2005-2020. The coverage limitation is
   survivorship (only living tickers), not price-data depth.

3. **Massive store — no cross-sectional baseline**: per AM-4, the massive-store leg uses
   beta-adjusted AR vs SPY only. A true date-matched peer baseline across ~20k tickers is
   computationally deferred to a later wave if the signal promotes.

4. **CIK→ticker mapping**: only ~10,415 CIKs in the repo map. Many CORRESP/UPLOAD filers
   are mutual funds, investment advisors, and foreign private issuers — not exchange-listed
   equities. The unmapped fraction is expected to be large.

5. **Beta estimation**: requires 120+ trading days of pre-event history. Early events for
   recently-listed companies will be dropped from the beta-adjusted analysis.

6. **Review grouping**: the 180-day gap rule (AM-2) is a simplification. Some long-running
   reviews may be split artificially; this creates conservative event counts.

---

## Nightly wiring (for consolidation)

This is a standalone phase-0 harness. For production:

1. **Collector**: a nightly job would fetch the latest EDGAR quarter index (one quarterly
   file per quarter, cacheable) and append new CORRESP/UPLOAD rows to
   `data/comment_letter_events/events.parquet`.
2. **Integration**: the event calendar can serve as an input to the forward-return monitoring
   pipeline once (if) the signal is promoted past the gauntlet.
3. **Re-run trigger**: run on first day of each new quarter (new quarter index published).
4. **No template changes required**: this is data-only; no site pages ship from phase-0.

---

*Generated by `scripts/d2_comment_letter_release_phase0.py` — plain harness, no production impact.*
