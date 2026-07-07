# G-T2X Gauntlet Results

**Pre-registration:** research/signal_engine/TIER_ENTRY_DEEPDIVE.md §6
**Status:** LOCKED — no post-hoc threshold tuning. Nulls printed, not hidden.
**Run date:** 2026-07-06

---

## Pre-Registration Summary

**Candidate:** T2 tier-onset events, t+1 E1 fill, per-overlay filters.

**First-wave overlays (5, one pass each):**
1. OV1: 2W washout context (w2.stoch <= 35 OR stoch_cross_up)
2. OV2: fire-day turnover z > 0 (above-median volume on signal day)
3. OV3: sector-cycle phase in {bottoming, recovering}
4. OV4: NW dispersion-regime lens (NW L3 regime signal)
5. OV5: fill_premium_20d < 8% (not-extended)

**Ruler:** mean 21d benchmark-excess from E1 fill with −5% stop, month-block bootstrap CI (1000 reps, seed 42).

**Promotion gates (ALL must hold + directional consistency in both temporal splits):**
- CI_lo > 0
- stop-out_21 <= 50% (US) / <= 52% (CN)
- clean8_21 >= 33%
- n_filtered >= 300 per market
- retention >= 25% of base T2 fires

**Kill:** filtered excess <= unfiltered T2 base, OR retention < 15%.

---

## Universe and Data

- **US:** 7981 T2 onset events, 2498 tickers (baskets/ohlcv), 2015-01-01 to 2026-05-31
- **CN:** 1945 T2 onset events, 800 tickers (china_stocks, seed=42 cap 800), 2016-01-01 to 2026-05-31
- **Benchmark:** SPY (US), 510300.SS (CN)
- **Fill:** t+1 open (US), t+1 (hi+lo)/2 (CN)
- **Stop:** −5% from fill, monitored from fill-day low including fill day
- **Runtime:** US 338s, CN 175s, total 526s (8.8m)

---

## Base T2 Metrics (Unfiltered — v3 baseline)

| Market | n_base | excess_21 mean | CI_lo_95 | CI_hi_95 | stop_out_21% | clean8_21% |
|---|---|---|---|---|---|---|
| US | 7981 | -0.0005 | -0.0059 | 0.0044 | 55.6% | 29.9% |
| CN | 1945 | 0.0072 | -0.0032 | 0.0183 | 55.6% | 34.6% |

*Note: v3 baseline (TIER_ENTRY_DEEPDIVE.md §3a) for US T2: excess_21 mean −0.03%, CI (−0.59%, +0.44%), stop_out 55.6%, clean8 29.9%.*

> **Base inconsistency footnote:** The displayed base excess above (truncation-excluded mean, events after 2026-03-01 excluded from CI bootstrap) differs slightly from the kill-rule base used in per-overlay verdicts, which is computed via the `compute_overlay_stats` path including truncated events: US −0.000252 / CN +0.006970. No verdict flips under either base — the sign and relative ordering of filtered vs. base excess are unchanged regardless of which base figure is used.

---

## Per-Overlay Results

### OV1: 2W Washout Context

**Results Table:**

| Market | n_base | n_filtered | retention% | excess_21 mean | CI_lo_95 | CI_hi_95 | stop_out_21% | clean8_21% |
|---|---|---|---|---|---|---|---|---|
| US | 7981 | 2763 | 34.6% | -0.0029 | -0.0098 | 0.0034 | 57.2% | 32.1% |
| CN | 1945 | 685 | 35.2% | 0.0108 | -0.0041 | 0.0250 | 52.7% | 37.4% |

**Split-half consistency:**

| Market | H1 n | H1 dates | H1 mean exc | H2 n | H2 dates | H2 mean exc | Consistent? |
|---|---|---|---|---|---|---|---|
| US | 1351 | 2015-06-23 to 2021-04-16 | 0.0005 | 1351 | 2021-05-04 to 2026-02-26 | -0.0065 | NO |
| CN | 339 | 2016-01-04 to 2020-06-24 | -0.0019 | 339 | 2020-06-30 to 2026-02-27 | 0.0231 | NO |

**Gate-by-gate (US / CN):**

| Gate | Threshold | US value | US result | CN value | CN result |
|---|---|---|---|---|---|
| CI_lo > 0 | > 0 | -0.0098 | FAIL | -0.0041 | FAIL |
| stop_out_21 <= 50%/52% | <= 50.0% | 57.2% | FAIL | 52.7% | FAIL |
| clean8_21 >= 33% | >= 33% | 32.1% | FAIL | 37.4% | PASS |
| n_filtered >= 300 | >= 300 | 2763.0000 | PASS | 685.0000 | PASS |
| retention >= 25% | >= 25% of base | 34.6% | PASS | 35.2% | PASS |

**Verdict: KILL** (US=KILL, CN=NULL) US kill: filtered excess (-0.0029) <= base (-0.0003).

---

### OV2: Fire-day Turnover z > 0

**Results Table:**

| Market | n_base | n_filtered | retention% | excess_21 mean | CI_lo_95 | CI_hi_95 | stop_out_21% | clean8_21% |
|---|---|---|---|---|---|---|---|---|
| US | 7981 | 2888 | 36.2% | -0.0046 | -0.0122 | 0.0028 | 58.0% | 28.8% |
| CN | 1945 | 1344 | 69.1% | 0.0063 | -0.0055 | 0.0198 | 57.5% | 36.5% |

**Split-half consistency:**

| Market | H1 n | H1 dates | H1 mean exc | H2 n | H2 dates | H2 mean exc | Consistent? |
|---|---|---|---|---|---|---|---|
| US | 1420 | 2015-03-02 to 2020-11-09 | -0.0046 | 1420 | 2020-11-09 to 2026-02-27 | -0.0049 | NO |
| CN | 665 | 2016-01-04 to 2021-02-05 | 0.0052 | 666 | 2021-02-10 to 2026-02-27 | 0.0074 | NO |

**Gate-by-gate (US / CN):**

| Gate | Threshold | US value | US result | CN value | CN result |
|---|---|---|---|---|---|
| CI_lo > 0 | > 0 | -0.0122 | FAIL | -0.0055 | FAIL |
| stop_out_21 <= 50%/52% | <= 50.0% | 58.0% | FAIL | 57.5% | FAIL |
| clean8_21 >= 33% | >= 33% | 28.8% | FAIL | 36.5% | PASS |
| n_filtered >= 300 | >= 300 | 2888.0000 | PASS | 1344.0000 | PASS |
| retention >= 25% | >= 25% of base | 36.2% | PASS | 69.1% | PASS |

**Verdict: KILL** (US=KILL, CN=KILL) US kill: filtered excess (-0.0046) <= base (-0.0003). CN kill: filtered excess (0.0063) <= base (0.0070).

---

### OV3: Sector-Cycle Phase {bottoming, recovering}

**Status: NOT-RUN**

**Reason:** No point-in-time historical per-stock sector membership available. sector_holdings/ contains only a current snapshot (2026-06-11 single date). sector_cycles/backfill.parquet has MONTHLY sector phase (11 SPDR ETFs) from 2010-12-31 but no PIT ticker-to-sector assignment for individual stocks over the backtest window. Without PIT stock-to-sector mapping, this overlay cannot be computed without improvising a proxy — prohibited by pre-registration.

**Verdict: NOT-RUN** (both US and CN)

---

### OV4: NW L3 Dispersion-Regime Lens

**Status: NOT-RUN**

**Reason:** The specific NW L3 dispersion-regime series has no PIT history; data/neuralweb/ contains only current-state files (world_state.json, kernel_estimates.parquet, spine_index.parquet) with no backfilled daily label series. Other regime series in data/ (e.g. data/regime/regime_history.parquet) are different constructs and would be prohibited proxies — the pre-registration requires the specific L3 dispersion-regime signal, not a similar-sounding substitute. Without the correct historical daily label series, this overlay cannot be applied over the backtest window.

**Verdict: NOT-RUN** (both US and CN)

---

### OV5: fill_premium_20d < 8%

**Results Table:**

| Market | n_base | n_filtered | retention% | excess_21 mean | CI_lo_95 | CI_hi_95 | stop_out_21% | clean8_21% |
|---|---|---|---|---|---|---|---|---|
| US | 7981 | 4195 | 52.6% | -0.0012 | -0.0062 | 0.0036 | 47.4% | 25.9% |
| CN | 1945 | 1054 | 54.2% | -0.0006 | -0.0097 | 0.0091 | 48.4% | 29.0% |

**Split-half consistency:**

| Market | H1 n | H1 dates | H1 mean exc | H2 n | H2 dates | H2 mean exc | Consistent? |
|---|---|---|---|---|---|---|---|
| US | 2066 | 2015-01-12 to 2020-07-06 | 0.0008 | 2066 | 2020-07-06 to 2026-02-27 | -0.0039 | NO |
| CN | 521 | 2016-01-04 to 2020-07-03 | -0.0019 | 522 | 2020-07-07 to 2026-02-26 | 0.0017 | NO |

**Gate-by-gate (US / CN):**

| Gate | Threshold | US value | US result | CN value | CN result |
|---|---|---|---|---|---|
| CI_lo > 0 | > 0 | -0.0062 | FAIL | -0.0097 | FAIL |
| stop_out_21 <= 50%/52% | <= 50.0% | 47.4% | PASS | 48.4% | PASS |
| clean8_21 >= 33% | >= 33% | 25.9% | FAIL | 29.0% | FAIL |
| n_filtered >= 300 | >= 300 | 4195.0000 | PASS | 1054.0000 | PASS |
| retention >= 25% | >= 25% of base | 52.6% | PASS | 54.2% | PASS |

**Verdict: KILL** (US=KILL, CN=KILL) US kill: filtered excess (-0.0012) <= base (-0.0003). CN kill: filtered excess (-0.0006) <= base (0.0070).

---

## Summary Verdict Table

| Overlay | US n_filt | CN n_filt | US excess | CN excess | US CI_lo | CN CI_lo | US stop% | CN stop% | US clean8% | CN clean8% | US verdict | CN verdict | Overall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OV1 | 2763 | 685 | -0.0029 | 0.0108 | -0.0098 | -0.0041 | 57.2% | 52.7% | 32.1% | 37.4% | KILL | NULL | KILL |
| OV2 | 2888 | 1344 | -0.0046 | 0.0063 | -0.0122 | -0.0055 | 58.0% | 57.5% | 28.8% | 36.5% | KILL | KILL | KILL |
| OV3 | NOT-RUN | NOT-RUN | — | — | — | — | — | — | — | — | NOT-RUN | NOT-RUN | NOT-RUN |
| OV4 | NOT-RUN | NOT-RUN | — | — | — | — | — | — | — | — | NOT-RUN | NOT-RUN | NOT-RUN |
| OV5 | 4195 | 1054 | -0.0012 | -0.0006 | -0.0062 | -0.0097 | 47.4% | 48.4% | 25.9% | 29.0% | KILL | KILL | KILL |

---

## Plain-English Summary

**In plain English:** This study tested 5 pre-registered filter overlays on T2 tier-onset events across 2,498 US names (2015-2026) and 800 CN names (2016-2026). The base T2 population — unfiltered — shows near-zero benchmark-excess at 21 days with confidence intervals straddling zero and stop-out rates of ~56% (matching TIER_ENTRY_DEEPDIVE §3a).

**Overlays 3 and 4 were NOT-RUN:** OV3 (sector-cycle phase) requires point-in-time per-stock sector membership history, which does not exist — sector_holdings/ has only a 2026-06-11 snapshot. OV4 (NW L3 dispersion regime) requires a historical daily regime label series, which does not exist in data/neuralweb/. No proxies were improvised — the pre-registration prohibits this.

**Overlays 1, 2, and 5 ran.** Results by overlay:

- **OV1 (2W washout)** (overall KILL): US n=2763 (35% retained), excess=-0.0029 CI_lo=-0.0098, stop_out=57.2%, clean8=32.1%; CN n=685 (35% retained), excess=0.0108 CI_lo=-0.0041, stop_out=52.7%, clean8=37.4%. US verdict=KILL, CN verdict=NULL.
- **OV2 (turnover z>0)** (overall KILL): US n=2888 (36% retained), excess=-0.0046 CI_lo=-0.0122, stop_out=58.0%, clean8=28.8%; CN n=1344 (69% retained), excess=0.0063 CI_lo=-0.0055, stop_out=57.5%, clean8=36.5%. US verdict=KILL, CN verdict=KILL.
- **OV5 (fp20d<8%)** (overall KILL): US n=4195 (53% retained), excess=-0.0012 CI_lo=-0.0062, stop_out=47.4%, clean8=25.9%; CN n=1054 (54% retained), excess=-0.0006 CI_lo=-0.0097, stop_out=48.4%, clean8=29.0%. US verdict=KILL, CN verdict=KILL.

**Statistical decisiveness caveat:** The kills are triggered by the pre-registered relative rule (filtered excess ≤ base). Because the base excess itself has a CI straddling zero (~1pp wide), several kills — notably CN OV2 (7bp below base) — are not statistically distinguishable from the base; they are rule-triggered, not evidence of a statistically dead filter.

**Regime-change lens (OV1 and OV5 US):** OV1 and OV5 (US) show positive excess in the 2015–2021 half and negative in the 2021–2026 half. The kill is driven by second-half deterioration; this is consistent with regime change rather than a filter with no edge. These overlays are re-probe eligible with fresh forward data (come-back ≥2027-01) rather than permanently dead.

---

## Caveats

1. **CN survivorship bias.** CN universe is 2026-snapshot. Historical CN numbers are directionally informative but overstated vs. a PIT universe.
2. **OV3 / OV4 NOT-RUN.** Both overlays require historical time-series data that does not exist in backfillable form. These are flagged as data gaps — future builds must create archival sector-phase-per-stock and NW dispersion-regime series.
3. **OV1 w_setup is compute-intensive.** For each event, w_setup() is called on the truncated series close[:event_date]. This is PIT-safe but slow (~2-4s per ticker on average).
4. **Turnover z uses 60-bar rolling lookback.** Pre-registration says 'above-median volume on signal day'; z>0 is above the rolling mean which equals above-median under approximate normality. Window = 60 prior bars (about 3 months). **OV2 volume measurement caveat:** OV2 uses SHARE volume (not dollar turnover); z>0 means above the rolling MEAN, which is stricter than "above-median" for right-skewed volume distributions (the mean exceeds the median when the distribution is right-skewed, so z>0 is a higher bar than the pre-registration's "above-median" language implies).
5. **US PIT filter not applied.** US broad universe uses all baskets/ohlcv parquets; no SP1500 PIT survivorship filter applied, matching v3 baseline.
6. **Truncation.** Events after 2026-03-01 excluded from CI bootstrap (lack full 63d forward data).
7. **No VALIDATED language.** All metrics are descriptive. No signal has been promoted based on this study.

---
*Generated by scripts/_bt_g_t2x.py — G-T2X locked gauntlet, 2026-07-06.*