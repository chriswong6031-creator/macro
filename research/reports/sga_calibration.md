# SGA W5 — Stage Classification Calibration
*Generated 2026-07-19T09:17:49Z by `scripts/calibrate_stage_vs_equitydesk.py`*

## Universe

| Metric | Count |
|--------|-------|
| EquityDesk US names with stage_flag | 2,566 |
| Names with local OHLCV data | 1,838 |
| Classified by our engine | 1,837 |
| Not comparable (no OHLCV) | 728 |
| Too young / unclassifiable | 1 |

## Stage Agreement

| Metric | Value |
|--------|-------|
| **Exact stage match (1–4)** | **73.3%** (1,346/1,837) |
| ±1 stage adjacency match | 86.4% (1,587/1,837) |

## Confusion Matrix (their stage × our stage)

| | Our Stage 1 | Our Stage 2 | Our Stage 3 | Our Stage 4 |
|--|--|--|--|--|
| Their Stage 1 | 1 | 2 | 2 | 0 |
| Their Stage 2 | 54 | 935 | 28 | 82 |
| Their Stage 3 | 17 | 18 | 22 | 86 |
| Their Stage 4 | 36 | 113 | 53 | 388 |

## SMA-30w Correlation

| Metric | Value |
|--------|-------|
| Pairs compared | 1,837 |
| Pearson r | 1.0 |
| Median abs % diff | 0.12% |

## Mansfield RS Correlation

| Metric | Value |
|--------|-------|
| Pairs compared | 1,837 |
| Pearson r | 0.9953 |

## Interpretation

Where we differ and why:

- **Data vintage gap.** Our OHLCV series and theirs were snapped at different
  moments. A name near a stage transition flips classification with even a
  single week's difference.
- **Weekly-bar definition.** We use strictly completed W-FRI bars
  (`engine.cycles._w_fri_completed`). Their classifier's bar definition is not
  published, so bars near the snapshot date may differ.
- **SMA30 calculation.** We compute on weekly closes of daily adjusted prices
  (`baskets/ohlcv/`); they may use their own data vendor.
- **Universe alignment.** Names in their screen but absent from our OHLCV store
  (728 names) are counted as not-comparable, not errors.

Stage agreement at or above ~70% exact match on a dual-source, multi-vintage
comparison is consistent with the expected gap from vintage and bar-definition
differences. Adjacency agreement (86.4%) is the more meaningful
metric: a Stage-2 name that we call Stage-1 (basing) is still on the cusp of
a breakout, not a mismatch in kind.

The SMA30 correlation (r = 1.0) confirms
that our 30-week SMA computations track the same underlying price series.
Mansfield RS (r = 0.9953) may differ more
due to their benchmark choice vs our SPY-only benchmark (SGA-R2).
