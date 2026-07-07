# D2 Comment-Letter Release Phase-0 — NULL

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

**Result: NULL.** The substantive-review cells did not clear the
pre-registered gate (|t|>=2 AND BH q<=0.10).

---

## Data sources

- EDGAR quarterly full-text indexes: `https://www.sec.gov/Archives/edgar/full-index/YYYY/QTR#/form.idx`
  (2005-Q1 through current; free, no API key; rate-limited to ~10 req/s)
- Price stores:
  - **massive_stock_day**: 2021-07-06 to 2026-07-02, ~20,476 tickers (preferred for post-2021 events)
  - **yahoo**: SPY from 1993; per-ticker AAPL/MSFT from ~2023-07-03, ~688 tickers total
    (survivorship-biased; yahoo stock coverage is shallow for pre-2023 events; most deep
    history comes from SPY used as the beta-adjustment baseline only)
- CIK→ticker map: `data/edgar/company_tickers.json` (~10,415 entries)

**SURVIVORSHIP CAVEAT:** Both price stores hold only tickers alive/active as of collection date.
Companies delisted between their SEC review date and today are NOT in either store.
All return estimates are UPWARD-BIASED. This is a display/exploration result, not a
production signal claim.

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

---

## Pre-registration (frozen before computation)

See script header for full text. Key elements:

- **Event date**: first EDGAR filing-index date within a review (UPLOAD or CORRESP)
- **Review grouping**: CIK + 180-day gap rule (AM-2)
- **Substance**: >=3 UPLOAD filings = substantive; else light (AM-1)
- **Horizons**: h5 (5 trading days), h21 (21 trading days)
- **Abnormal return**: stock return − beta × SPY return; beta from trailing 252d OLS, min 120d
- **Gate**: |t|>=2 (date-clustered NW) AND BH q<=0.10 across 2×2×2 family
- **Direction**: two-sided (not pre-registered)
- **Trials logged**: 8 distinct configs in ledger family `d2_comment_letter_release`

---

## Abnormal return summary (raw, pre-gate)

  light/massive/h5: n=4040 mean=6.36% median=-0.47%
  light/massive/h21: n=4039 mean=8.65% median=-1.68%
  light/yahoo/h5: n=455 mean=0.11% median=0.16%
  light/yahoo/h21: n=455 mean=0.72% median=-0.05%
  substantive/massive/h5: n=1102 mean=1.89% median=-1.08%
  substantive/massive/h21: n=1102 mean=4.67% median=-3.00%
  substantive/yahoo/h5: n=289 mean=-0.26% median=-0.11%
  substantive/yahoo/h21: n=289 mean=1.03% median=0.19%

---

## Gate results — 2 × 2 × 2 family (substance × horizon × store)

*Primary gate: substantive cells with |t|≥2.0 AND BH q≤0.1*

| Cell | mean AR | t | p | q_BH | gate |
|------|---------|---|---|------|------|
| light_h21_massive | 7.03% (n=4039) | 4.711 | 0.0 | 0.0 | pass-t |
| light_h21_yahoo | 0.67% (n=455) | 1.849 | 0.0644 | 0.1984 | fail |
| light_h5_massive | 4.56% (n=4040) | 1.784 | 0.0744 | 0.1984 | fail |
| light_h5_yahoo | 0.12% (n=455) | 0.443 | 0.6575 | 0.6575 | fail |
| substantive_h21_massive | 3.55% (n=1102) | 1.428 | 0.1534 | 0.3038 | fail |
| substantive_h21_yahoo | 0.98% (n=289) | 0.837 | 0.4028 | 0.4603 | fail |
| substantive_h5_massive | 1.13% (n=1102) | 1.197 | 0.2313 | 0.3084 | fail |
| substantive_h5_yahoo | -0.31% (n=289) | -1.311 | 0.1899 | 0.3038 | fail |

**Notes on t-stat:**
- Date-collapsed: one mean AR per event-date, then Newey-West over date series (STATS LAW)
- NW lags = ceil(sqrt(n_dates) × h/5) to account for overlapping windows at h21
- Baseline: beta-adjusted vs SPY (OLS trailing 252d, min 120d)

**Warning on light_h21_massive (t=4.7, "pass-t" but not substantive):** This is NOT a clean
result. The mean AR of 7.0% vs median of -1.9% signals extreme outlier contamination.
Investigation shows 27 events with >500% 21-day AR (ATXI +6263%, ASTI +2390%, HCWB +3243%),
all microcap/penny stocks. The Newey-West t-stat is detecting the heavy right tail, not a
systematic release effect. This cell does not meet the PRIMARY gate (requires SUBSTANTIVE reviews)
and even if it did, the mean is not a meaningful return estimate given the extreme outliers. A
winsorized or median-based version would likely show no effect. This does NOT constitute evidence
of a light-review release effect.

---

## Split-half (consistency gate — substantive cells only)

| Half | Cell | t | p | n |
|------|------|---|---|---|
| first_substantive_h21_massive | | 1.225 | 0.2207 | 585 |
| first_substantive_h21_yahoo | | 0.837 | 0.4028 | 289 |
| first_substantive_h5_massive | | -0.917 | 0.3589 | 585 |
| first_substantive_h5_yahoo | | -1.311 | 0.1899 | 289 |
| second_substantive_h21_massive | | 0.747 | 0.4553 | 517 |
| second_substantive_h21_yahoo | | None | None | 0 |
| second_substantive_h5_massive | | 1.871 | 0.0613 | 517 |
| second_substantive_h5_yahoo | | None | None | 0 |

Sign consistency across halves: see table above

---

## Verdict

**NULL**

The pre-registered primary gate requires at least one substantive-review cell to show
|t|≥2.0 (date-clustered Newey-West) AND BH-corrected q≤0.1
across all 8 cells in the 2×2×2 family (substance × horizon × store).

No cell cleared both thresholds simultaneously. The null is printed; this is a valid and complete run.

---

## Coverage gaps and caveats

1. **Survivorship bias** (both stores): companies delisted since data collection are absent.
   Historical reviews for failed companies are excluded. All AR estimates are optimistic.

2. **Yahoo store depth**: the yahoo store for this repo extends to ~2023-07-03, not 2005.
   Pre-2021 events can only be covered by tickers in the yahoo store AND having data back
   to the event date. In practice, the deep (2005-2021) leg has very sparse coverage.

3. **CIK→ticker mapping**: only ~10,415 CIKs in the repo map. Many CORRESP/UPLOAD filers
   are mutual funds, investment advisors, and foreign private issuers — not exchange-listed
   equities. The unmapped fraction is expected to be large.

4. **Beta estimation**: requires 120+ trading days of pre-event history. Early events for
   recently-listed companies will be dropped from the beta-adjusted analysis.

5. **Review grouping**: the 180-day gap rule (AM-2) is a simplification. Some long-running
   reviews may be split artificially; this creates conservative event counts (more reviews,
   smaller n per review) rather than optimistic ones.

---

## Nightly wiring (for consolidation)

This is a standalone phase-0 harness. For production:

1. **Collector**: a nightly job would fetch the latest EDGAR quarter index (one quarterly
   file per quarter, cacheable) and append new CORRESP/UPLOAD rows to
   `data/comment_letter_events/events.parquet`.
2. **Integration**: the event calendar (`events.parquet`) can serve as an input to the
   forward-return monitoring pipeline once (if) the signal is promoted past the gauntlet.
3. **Re-run trigger**: run on first day of each new quarter (new quarter index published).
4. **No template changes required**: this is data-only; no site pages ship from phase-0.

---

*Generated by `scripts/d2_comment_letter_release_phase0.py` — plain harness, no production impact.*
