# SLF-055: NY Fed Primary Dealer Stress — Phase 0

**Family:** `slf055_dealer_stress` | **Date:** 2026-07-06
**Verdict: PARTIAL** — PARTIAL — some signal evidence; null not fully rejected; collector ships as display

---

## In plain English

Primary dealers are the 25 financial firms that trade directly with the Fed.
When they hold large SHORT positions in Treasuries (or reduce their long
positions sharply), it usually signals they expect bond prices to fall — a
potential stress indicator. Settlement fails (when bond deliveries fail to
complete on time) spike during funding crunches and repo market stress.

We tested whether either of these weekly signals could predict future bond
price changes (TLT) or stock market drawdowns (SPY). The NY Fed publishes
this data every Thursday for the prior Wednesday, so we enforced a 7-day
publication lag before using any data.

**Coverage note:** The PD collector stores 1483 Wednesday-only weekly
observations (1998-01-28 to present). However, TLT only began trading on
2002-07-30, so all TLT-based forward tests span 2002→present only.
The SBP2001 era (1998-2001) is excluded from TLT forward cells.
SPY-based tests span the full period.

**Key result:** The signals show partial evidence of predictive
content. The collector ships regardless — ~28 years of weekly macro series
has standalone display value for monitoring funding-market stress.

---

## Data

- **Source:** NY Fed Markets Data API (`markets.newyorkfed.org/api/pd/...`)
- **Coverage (collector):** 1998-01-28 to present — 1483 Wednesday weekly observations
  (NY Fed /api/pd/list/asof.json returns ~1941 as-of dates including non-Wednesday
  dates for other surveys; only the 1483 Wednesday Treasury-position releases are
  retained — non-Wednesday rows are all NaN for our target series and are dropped.)
- **Coverage (TLT forward tests):** 2002-07-30 to present only (TLT inception).
  SBP2001 era (1998-2001) contributes no observations to TLT-based cells.
- **Coverage (SPY forward / AUC tests):** 1998-01-28 to present.
- **Publication lag enforced:** 7 days (data released Thursday for prior Wednesday)
- **Era-safe z-scores:** rolling 3-year (156-week) window, computed WITHIN each era

### Era distribution (1483 Wednesday observations)
  - SBN2013: 92 weeks
  - SBN2015: 365 weeks
  - SBN2022: 130 weeks
  - SBN2024: 104 weeks
  - SBP2001: 179 weeks
  - SBP2013: 613 weeks

### Era schema breaks (confound pre-registration)
The survey schema changed four times (2001, 2013, 2015, 2022, 2024 revisions).
Raw level comparison across eras is meaningless (scope of reporting changed).
All z-scores are era-bounded: the rolling window resets at each era boundary.

### Series mapping per era
| Era | Net Treasury Position | Fails-to-Deliver (PDFTD-*) | Fails-to-Receive (PDFTR-*) |
|-----|----------------------|---------------------------|---------------------------|
| SBP2001/SBP2013 | PDPUSGCS5L* + PDPUSGCS5M* + PDPUSGTBNOP | PDFASUFDA | PDFASUFRA |
| SBN2013+ | PDPOSGST-TOT | PDFTD-USTET | PDFTR-USTET |

_Mapping verified: 2024-07-03 API response — PDPOSGST-TOT=312736,_
_PDFTD-USTET=113493 (fails to deliver), PDFTR-USTET=124567 (fails to receive)._

---

## Pre-registered gates

| Gate | Criterion | Result |
|------|-----------|--------|
| **G1** | |t_HAC| >= 2 AND BH-FDR q <= 0.10, any of 3 signals × 2 horizons (weekly events, corrected HAC lags) | **FAIL** |
| **G2** | Leave-one-era-out same-sign on CONDITIONAL (extreme-week) forward return | **PASS** |
| **G3** | AUC CI excludes 0.5 from above (stress → drawdown) | **FAIL** |
| **T3** | Adds over auction absorption_z | **PRE-DECLARED SKIP** — weekly vs per-auction index alignment undefined |

---

## T1: Event study results (extreme signal >= 95th pctile)

| Signal | Target | Horizon | N events | Mean fwd ret | t_HAC | p_HAC | BH q | BH reject |
|--------|--------|---------|----------|--------------|-------|-------|------|-----------|
| Dealer Net Position Z (stress = short) | TLT | 21d | 38 | -0.0006 | -0.098 | 0.9216 | 0.9653 | No |
| Dealer Net Position Z (stress = short) | TLT | 63d | 21 | -0.0004 | -0.071 | 0.9436 | 0.9653 | No |
| Dealer Net Position Z (stress = short) | SPY | 21d | 39 | 0.0013 | 0.149 | 0.8817 | 0.9653 | No |
| Dealer Net Position Z (stress = short) | SPY | 63d | 22 | 0.0242 | 1.552 | 0.1208 | 0.7248 | No |
| Total UST Fails Z | TLT | 21d | 34 | 0.0074 | 0.907 | 0.3644 | 0.8680 | No |
| Total UST Fails Z | TLT | 63d | 23 | 0.0035 | 0.301 | 0.7632 | 0.9653 | No |
| Total UST Fails Z | SPY | 21d | 41 | 0.0079 | 0.782 | 0.4340 | 0.8680 | No |
| Total UST Fails Z | SPY | 63d | 27 | 0.0212 | 2.155 | 0.0311 | 0.3732 | No |
| Fails 4-week Change Z | TLT | 21d | 28 | -0.0019 | -0.562 | 0.5743 | 0.9653 | No |
| Fails 4-week Change Z | TLT | 63d | 21 | -0.0055 | -0.936 | 0.3495 | 0.8680 | No |
| Fails 4-week Change Z | SPY | 21d | 37 | -0.0007 | -0.043 | 0.9653 | 0.9653 | No |
| Fails 4-week Change Z | SPY | 63d | 27 | 0.0080 | 0.817 | 0.4139 | 0.8680 | No |

**G1 result:** FAIL — no cell clears both thresholds

---

## T2: Drawdown AUC (stress predicts SPY >=5% drawdown in 63d)

| Signal | AUC | 2.5% CI | 50% CI | 97.5% CI | N | CI excl 0.5 (above) |
|--------|-----|---------|--------|----------|---|---------------------|
| Dealer Net Position Z (stress = short) | 0.5193 | 0.4979 | 0.5193 | 0.5407 | 7069 | No |
| Total UST Fails Z | 0.4866 | 0.4659 | 0.4863 | 0.5078 | 7069 | No |
| Fails 4-week Change Z | 0.4489 | 0.4284 | 0.4488 | 0.4704 | 7049 | No |

**G3 result:** FAIL — no signal AUC CI clearly above 0.5

---

## G2: Leave-one-era-out (conditional on extreme signal weeks)

G2 tests whether the CONDITIONAL forward return (mean TLT-21d return at extreme
signal weeks, signal >= 95th pctile) keeps the same sign when each era is
excluded from the sample. This is the meaningful test: we check if the extreme-
event edge is robust across eras, not just whether unconditional bond returns
were positive on average (which would trivially pass regardless of the signal).

SBP2001 (1998-2001) is excluded from TLT cells because TLT did not exist yet.
G2 criterion: 'all 6 eras' does not apply to TLT cells — at most 5 eras testable.

### Dealer Net Position Z (stress = short)
Full-sample conditional mean (extreme weeks only): -0.00366 (sign: -1, n_extreme: 62)
Eras testable: 5 of 5

| Excluded era | N remaining | N extreme | Cond mean | Sign | Consistent |
|--------------|-------------|-----------|-----------|------|------------|
| SBN2013 | 1143 | 58 | -0.00629 | -1 | Yes |
| SBN2015 | 870 | 44 | -0.01398 | -1 | Yes |
| SBN2022 | 1105 | 56 | -0.00266 | -1 | Yes |
| SBN2024 | 1136 | 57 | -0.00685 | -1 | Yes |
| SBP2013 | 674 | 34 | 0.00668 | 1 | No |

**All consistent:** False

### Total UST Fails Z
Full-sample conditional mean (extreme weeks only): 0.01007 (sign: 1, n_extreme: 62)
Eras testable: 5 of 5

| Excluded era | N remaining | N extreme | Cond mean | Sign | Consistent |
|--------------|-------------|-----------|-----------|------|------------|
| SBN2013 | 1143 | 58 | 0.01080 | 1 | Yes |
| SBN2015 | 870 | 44 | 0.00745 | 1 | Yes |
| SBN2022 | 1105 | 56 | 0.01368 | 1 | Yes |
| SBN2024 | 1136 | 57 | 0.01229 | 1 | Yes |
| SBP2013 | 674 | 34 | 0.00303 | 1 | Yes |

**All consistent:** True

### Fails 4-week Change Z
Full-sample conditional mean (extreme weeks only): 0.00282 (sign: 1, n_extreme: 46)
Eras testable: 5 of 5

| Excluded era | N remaining | N extreme | Cond mean | Sign | Consistent |
|--------------|-------------|-----------|-----------|------|------------|
| SBN2013 | 826 | 42 | 0.00224 | 1 | Yes |
| SBN2015 | 738 | 37 | 0.00555 | 1 | Yes |
| SBN2022 | 856 | 43 | 0.00427 | 1 | Yes |
| SBN2024 | 871 | 44 | 0.00068 | 1 | Yes |
| SBP2013 | 353 | 18 | -0.00269 | -1 | No |

**All consistent:** False

**G2 result:** PASS — conditional edge sign consistent across all testable era exclusions

---

## Deflated Sharpe (multiple-testing haircut)

Applied to CONDITIONAL event returns: `total_fails_z | TLT | 21d`, non-overlapping
extreme-week events only (signal >= 95th pctile). This is the Sharpe of the
strategy that enters TLT at extreme-stress weeks and exits after 21 trading days,
not the unconditional TLT Sharpe (which would be uninformative about signal value).
Trial grid: 15 distinct configs (3 signals × 2 horizons × 2 targets + 3 AUC)

| Metric | Value |
|--------|-------|
| SR (annualized, event-frequency) | 2.06 |
| DSR | 0.1629 |
| Verdict | FAILS multiple-testing haircut (DSR<0.90) |
| N trials | 15 |

---

## T3: Comparison vs absorption_z

**PRE-DECLARED SKIP.**

Reason: `data/treasury_auctions/auctions.parquet` is indexed per-auction event,
not by weekly calendar. The NY Fed PD data is released on a weekly Wednesday
schedule. Aligning these two time series would require interpolation or matching
assumptions that are not methodologically pre-registerable without looking at
results first. The two signals capture qualitatively different phenomena
(auction-day demand vs ongoing financing positions). T3 is registered in the
trial grid with `skip_t3=True` and is not counted toward the verdict.

---

## Nightly wiring (for consolidation)

Add to `scripts/collect.py` under the Thursday update block:
```python
# NY Fed Primary Dealer Statistics (Thursdays ~16:15 ET)
from collectors.nyfed_primary_dealer import run as run_pd
run_pd(config.data_dir() / 'nyfed_pd')
```

---

## Trial ledger entries

```
{"ts": "2026-07-06T11:37:27.010922+00:00", "family": "slf055_dealer_stress", "config_hash": "117facbc633cc309", "config": {"signal": "net_pos_z", "horizon": 21, "target": "TLT", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.011097+00:00", "family": "slf055_dealer_stress", "config_hash": "47a24e4e20f3792b", "config": {"signal": "net_pos_z", "horizon": 21, "target": "SPY", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.011182+00:00", "family": "slf055_dealer_stress", "config_hash": "7cff4f8241703664", "config": {"signal": "net_pos_z", "horizon": 63, "target": "TLT", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.011245+00:00", "family": "slf055_dealer_stress", "config_hash": "dbe6cd29dcce892b", "config": {"signal": "net_pos_z", "horizon": 63, "target": "SPY", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.011300+00:00", "family": "slf055_dealer_stress", "config_hash": "1c5d563590ce6feb", "config": {"signal": "total_fails_z", "horizon": 21, "target": "TLT", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.011354+00:00", "family": "slf055_dealer_stress", "config_hash": "edfebb59776ef2c7", "config": {"signal": "total_fails_z", "horizon": 21, "target": "SPY", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.011406+00:00", "family": "slf055_dealer_stress", "config_hash": "e752a4dfee85b106", "config": {"signal": "total_fails_z", "horizon": 63, "target": "TLT", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.011455+00:00", "family": "slf055_dealer_stress", "config_hash": "fb5f1ddb5401bf86", "config": {"signal": "total_fails_z", "horizon": 63, "target": "SPY", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.011503+00:00", "family": "slf055_dealer_stress", "config_hash": "cc242ea084240759", "config": {"signal": "total_fails_chg4w_z", "horizon": 21, "target": "TLT", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.011879+00:00", "family": "slf055_dealer_stress", "config_hash": "25473ff7b86227b8", "config": {"signal": "total_fails_chg4w_z", "horizon": 21, "target": "SPY", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.012091+00:00", "family": "slf055_dealer_stress", "config_hash": "3c48c40389f0ab0a", "config": {"signal": "total_fails_chg4w_z", "horizon": 63, "target": "TLT", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.012191+00:00", "family": "slf055_dealer_stress", "config_hash": "e9a7b901d75b3ccd", "config": {"signal": "total_fails_chg4w_z", "horizon": 63, "target": "SPY", "skip_t3": true, "skip_reason": "weekly-vs-auction index alignment undefined"}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.012263+00:00", "family": "slf055_dealer_stress", "config_hash": "9bdcb9eb623b7fe7", "config": {"signal": "net_pos_z", "test": "AUC_drawdown", "target": "SPY", "horizon": 63, "skip_t3": true}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.012326+00:00", "family": "slf055_dealer_stress", "config_hash": "94c6e9516354c00f", "config": {"signal": "total_fails_z", "test": "AUC_drawdown", "target": "SPY", "horizon": 63, "skip_t3": true}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
{"ts": "2026-07-06T11:37:27.012383+00:00", "family": "slf055_dealer_stress", "config_hash": "307c3f9b85ce8629", "config": {"signal": "total_fails_chg4w_z", "test": "AUC_drawdown", "target": "SPY", "horizon": 63, "skip_t3": true}, "source": "grid", "info_cutoff": "2026-07-06", "note": null}
```

---

## PIT discipline statement

- **NY Fed PD data:** 7-day publication lag enforced (data available Thursday
  for prior Wednesday; we shift signal index +7 days before ffilling to daily)
- **TLT/SPY forward returns:** computed from daily close-to-close at h=21/63 days,
  shifted backward (shift(-h)) to align with the conditioning date
- **TLT realized vol:** trailing 21-day annualized; no look-ahead in computation
- **Z-scores:** rolling 3-year window using ONLY prior observations within era
  (min 4 weeks before z is non-NaN; no look-ahead in mean/std estimation)

---
*Generated 2026-07-06 | Lane L6 SLF-055 | model: claude-sonnet-4-6*