# SLF-048: Wikipedia Attention Shock — Phase-0 Report

**Family:** `slf048_wiki_attention`  
**Date:** 2026-07-06  
**Effective N (trials logged):** 24  
**Verdict:** **NULL**

> **In plain English:** We looked at whether stocks that suddenly get a lot
> more Wikipedia attention (more page views than usual) tend to fall in the
> following 1-4 weeks, specifically for smaller, less-traded companies where
> hype is more likely to cause over-extension. The idea is: a spike in Wikipedia
> visits is a sign that retail attention is arriving late, and the stock may
> already be over-extended. The tests below check if that fade pattern holds
> reliably in the data.

---

## Signal construction

Signal uses the **exact display-chip construction** imported from
`scripts.build_site._attention_z` (not reimplemented here — imported to guarantee
the tested signal is identical to what the chip shows users):

- **attention_z** = robust abnormal-attention z:
  - `recent` = trailing-5d mean of log1p(views) (robust: 5-day mean, not single day)
  - `baseline` = median and MAD over the STRICTLY-PRIOR 90d window (causal, no look-ahead)
  - `scale` = 1.4826 × MAD (converts MAD to sigma-equivalent); fallback to std if MAD=0
  - `z` = (recent − median) / scale, clipped to [−3, +6]
- Source series: `views` column from `data/attention/<TICKER>.parquet` (raw page-view counts)
- **PIT discipline:** 1 trading-day lag (views for day D available D+1; we enter at D+1 close)
- **Shock threshold:** attention_z ≥ 2.0 (matches display chip threshold in config.yml)
- **Volume z:** 20d rolling z of volume from massive_stock_day; 1-day lag
- **Fade bucket:** attention_z ≥ 2.0 AND volume_z < 1.0
- **Confirm bucket:** attention_z ≥ 2.0 AND volume_z ≥ 1.0 (descriptive only — no directional gate)

## Publication-lag assumptions

| Series | Source | Lag enforced |
|--------|--------|--------------|
| Wikipedia page views | Wikimedia REST API | 1 trading day (shift(1)) |
| Close prices | massive_stock_day / yahoo | Uses close at end of signal day |
| Volume | massive_stock_day | 1 trading day (shift(1)) |
| Market cap | stock_fundamentals/snapshots | Point-in-time snapshot (single most-recent; used for tercile classification only) |

## Pre-registered gates

| Gate | Description | Result |
|------|-------------|--------|
| **G1** | Fade-bucket mean forward return negative, |t_HAC|≥2, BH-FDR q≤0.10 across full m=4 pre-registered family | FAIL |
| **G2** | Split-half same-sign (h1 and h2 both negative) | FAIL |
| **G3** | Effect concentrated in small-cap tercile: small-cap mean NEGATIVE AND more negative than large-cap | FAIL |

---

## G1: BH-FDR results — small-cap fade bucket, monthly rebalance

Pre-registered 2×2 family: {massive, yahoo} × {5d, 21d} — **m=4 fixed** (full family).
Cells with N<10 (untestable) carry p=1.0 as non-rejecting members of the family; they do
not shrink the family size (which would be anti-conservative).

| Cell | N observations | Mean return | t_HAC | p | BH-q | Reject H0? |
|------|---------------|-------------|-------|---|------|------------|
| massive_monthly_5d_small | 106 | -0.0091 | -2.007 | 0.0448 | 0.1792 | No |
| massive_monthly_21d_small | 106 | 0.0003 | 0.041 | 0.967 | 1.0 | No |
| yahoo_monthly_5d_small *(N<10, untestable — p=1.0)* | 7 | None | None | 1.0 | 1.0 | No |
| yahoo_monthly_21d_small *(N<10, untestable — p=1.0)* | 7 | None | None | 1.0 | 1.0 | No |

**G1 verdict:** 0/4 cells satisfy mean<0, |t|≥2, q≤0.10.
G1 = FAIL (no cells)

---

## G2: Split-half robustness

| Cell | H1 mean | H2 mean | Same sign? |
|------|---------|---------|------------|
| massive_monthly_5d_small | -0.00691 | -0.01129 | Yes |
| massive_monthly_21d_small | 0.00133 | -0.00074 | No |
| yahoo_monthly_5d_small | None | None | N/A |
| yahoo_monthly_21d_small | None | None | N/A |

**G2 verdict:** FAIL

---

## G3: Cap-tercile concentration

**Definition of G3 PASS (corrected):** G3 requires BOTH (a) small-cap fade mean is NEGATIVE
(an actual fade effect exists in small-caps) AND (b) small-cap is more negative than large-cap
(concentration). A cell where both means are positive cannot 'concentrate' a fade effect;
reporting PASS in that case is logically vacuous. G3 FAIL or 'small less positive' is reported
honestly when the pre-registered negative direction is absent.

| Panel | Horizon | Small mean | Small t | Large mean | Large t | Small negative? | Small more negative? | G3 ok? |
|-------|---------|-----------|---------|-----------|---------|----------------|---------------------|--------|
| massive | 5d | -0.0091 | -2.007 | -0.00051 | -0.097 | Yes | Yes | Yes |
| massive | 21d | 0.0003 | 0.041 | 0.01115 | 1.176 | No | Yes | No |
| yahoo | 5d | N/A | None | 0.01259 | 2.388 | No | No | No |
| yahoo | 21d | N/A | None | 0.04311 | 2.188 | No | No | No |

**G3 verdict:** FAIL (small negative AND more negative than large in 1/4 cells)

---

## Full results table (all panels, rebalances, horizons, cap filters)

| Key | Panel | Rebal | Horizon | Cap | Fade N | Fade Mean | Fade t | Confirm N | Confirm Mean |
|-----|-------|-------|---------|-----|--------|-----------|--------|-----------|--------------|
| massive_monthly_21d_all | massive | monthly | 21d | all | 1030 | 0.00716 | 1.424 | 186 | -0.0024 |
| massive_monthly_21d_large | massive | monthly | 21d | large | 147 | 0.01115 | 1.176 | 22 | 0.0169 |
| massive_monthly_21d_small | massive | monthly | 21d | small | 106 | 0.0003 | 0.041 | 23 | -0.01583 |
| massive_monthly_5d_all | massive | monthly | 5d | all | 1030 | 0.00205 | 0.856 | 187 | -0.00249 |
| massive_monthly_5d_large | massive | monthly | 5d | large | 147 | -0.00051 | -0.097 | 22 | 0.00672 |
| massive_monthly_5d_small | massive | monthly | 5d | small | 106 | -0.0091 | -2.007 | 23 | -0.00306 |
| massive_weekly_21d_all | massive | weekly | 21d | all | 4807 | 0.00802 | 3.42 | 1051 | 0.00865 |
| massive_weekly_21d_large | massive | weekly | 21d | large | 666 | 0.02224 | 3.791 | 161 | 0.02582 |
| massive_weekly_21d_small | massive | weekly | 21d | small | 500 | 0.00619 | 1.302 | 116 | 0.00317 |
| massive_weekly_5d_all | massive | weekly | 5d | all | 4867 | 0.00237 | 2.142 | 1069 | 0.00056 |
| massive_weekly_5d_large | massive | weekly | 5d | large | 676 | 0.00467 | 1.972 | 163 | 0.00293 |
| massive_weekly_5d_small | massive | weekly | 5d | small | 503 | -0.00031 | -0.155 | 117 | 0.00817 |
| yahoo_monthly_21d_all | yahoo | monthly | 21d | all | 74 | 0.02642 | 2.242 | 0 | None |
| yahoo_monthly_21d_large | yahoo | monthly | 21d | large | 16 | 0.04311 | 2.188 | 0 | None |
| yahoo_monthly_21d_small | yahoo | monthly | 21d | small | 7 | None | None | 0 | None |
| yahoo_monthly_5d_all | yahoo | monthly | 5d | all | 74 | 0.00761 | 1.145 | 0 | None |
| yahoo_monthly_5d_large | yahoo | monthly | 5d | large | 16 | 0.01259 | 2.388 | 0 | None |
| yahoo_monthly_5d_small | yahoo | monthly | 5d | small | 7 | None | None | 0 | None |
| yahoo_weekly_21d_all | yahoo | weekly | 21d | all | 468 | 0.02369 | 3.874 | 0 | None |
| yahoo_weekly_21d_large | yahoo | weekly | 21d | large | 116 | 0.02954 | 4.222 | 0 | None |
| yahoo_weekly_21d_small | yahoo | weekly | 21d | small | 38 | 0.0408 | 2.202 | 0 | None |
| yahoo_weekly_5d_all | yahoo | weekly | 5d | all | 471 | 0.00639 | 2.176 | 0 | None |
| yahoo_weekly_5d_large | yahoo | weekly | 5d | large | 117 | 0.00618 | 1.959 | 0 | None |
| yahoo_weekly_5d_small | yahoo | weekly | 5d | small | 38 | 0.00807 | 1.065 | 0 | None |

---

## Coverage

- Attention tickers in store: 966
- Tickers backfilled to 2015-07: 711
- Trial ledger effective N: 24

---

> **SURVIVORSHIP CAVEAT (Yahoo 2015-2021 leg)**
>
> The yahoo deep-history panel contains **only tickers still alive and listed as of
> the backfill date (2026-07-06)**. Tickers that were delisted, went bankrupt, or were
> taken private between 2015 and 2021 are entirely absent. This creates an upward bias
> on returns and an anti-fade bias: the worst outcomes (stocks that spiked on Wikipedia
> attention and then collapsed or were delisted) are systematically missing.
>
> **Actual yahoo coverage:** ~300 tickers overlap with the attention store; mktcap resolves
> for only ~219 of those; the small-cap fade bucket (our pre-registered primary cell) has
> N=9 observations — effectively empty for statistical inference. The yahoo half of the
> pre-registered 2×2 family is therefore **untestable as specified**. The family is
> honestly 1×2 (massive panel only) for the purposes of this phase-0 run. The yahoo leg
> is reported for completeness but carries no weight in the verdict.

---

> **DEEP-HISTORY BUCKET CONSTRUCTION NOTE**
>
> The yahoo panel has no volume data; all yahoo attention-shock observations are therefore
> assigned to the fade bucket (volume_z set to 0.0, which is < VOL_Z_THRESH=1.0). This
> means the confirm bucket is empty for the yahoo leg and the within-bucket fade/confirm
> split specified in the pre-registration **cannot be evaluated** for the deep-history period.
> The pre-registered 2×2 family (panel × horizon) structurally degenerates to a 1×2 family
> for this run. This is not a conservative assumption — it is a data limitation that makes
> half the pre-registered family untestable-as-specified.

---

## Verdict

**NULL**

Pre-registered gates not met. Backfilled history ships; signal remains display-only.

---

## Nightly wiring (for consolidation)

The backfilled `data/attention/` store is git-tracked for the existing ~126-day window
(data/attention/*.parquet are tracked files in this repo). The deep-history backfill
extended those files in place in the worktree but should NOT be committed to git
(the docstring states 'do NOT commit data/trial_ledger.jsonl'; similarly the bulk
attention parquet writes are worktree-only artifacts). The correct absorption path is:

1. **Tarball (produced by build stage):** `/tmp/slf048_attention_backfill.tar.gz` (~31.5 MB)
   This tarball contains the full backfilled store. To upload to R2:
   ```bash
   cd /tmp && tar xzf slf048_attention_backfill.tar.gz
   rclone sync /tmp/slf048_attention_backfill/ r2:macro-dashboard/attention/ --transfers 16
   ```
2. **Nightly collector line** (add to scripts/collect.py, wiki_pageviews section):
   ```python
   # wiki_pageviews — already wired; backfill completed 2026-07-06 to 2015-07-01
   # The existing WikiPageviewsAdapter incremental-fetches forward from last stored date.
   # No change needed for daily increments.
   ```
3. **R2 download on render box:** The nightly render job should rsync attention/ from R2
   before the wiki chip reads it. Add to the pre-render step:
   ```bash
   rclone sync r2:macro-dashboard/attention/ data/attention/ --transfers 16
   ```

---

## Limitations

- Market-cap tercile uses a single-point-in-time snapshot (most recent). For the
  2015-2021 yahoo leg, tickers that were small-cap in 2026 may have been mid/large
  earlier. This biases G3 toward false-positive concentration; a proper PIT mktcap
  series would require historical shares-outstanding × price.
- Yahoo volume data not available; all yahoo observations are assigned to the fade bucket.
  This makes the confirm bucket empty for yahoo and the pre-registered fade/confirm split
  untestable for that leg — not a conservative assumption, a data limitation.
  The pre-registered 2×2 family degenerates to 1×2 for this run.
- Survivorship bias in yahoo panel: only currently-listed tickers are present. Delistings
  and bankruptcies are absent, creating upward return bias and anti-fade bias.
- The CI-enforced 'validated' keyword check: this report does not claim any signal is
  confirmed (display-only until gauntleted).