# data/stock_events — Signal Episode Atlas event library

- taxonomy_version: `sea.v1`
- universe_basis: `2026-08 basket membership — survivor-biased backfill`
- tier: display / MEASUREMENT. Authority block all-false — this library
  ranks nothing, gates nothing, sizes nothing, escalates nothing.
- program: `research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md`

## Files

- `events_backfill.parquet` — written ONCE by
  `python -m scripts.backfill_stock_events --run`; FROZEN thereafter.
  Contains only events older than the 26-week maturation window, so every
  outcome cell is complete at write time.
- `live/YYYY-MM.parquet` — monthly parts. Appended nightly (keep-first on
  `(ticker, grid, date, direction)`); outcome cells filled in place by
  `mature_outcomes()`. Only these small parts are ever rewritten.

## Honesty

- Survivorship: the universe is TODAY's basket membership, so the
  backfilled history inherits survivorship. Widening to the full panel is
  a later, separately-adjudicated step.
- Clustering: events overlap in time within and across names. Cells print
  `n_distinct_years` beside `n`; promotion-grade inference is
  pre-specified as date-blocked bootstrap, never pooled t on raw events.
- Era: DT-R16 (#1751) forbids pooling across the 2010 regime break — every
  row carries `era`, and atlas cells report pooled AND post2010.
- No look-ahead: `depth_pctile` reads a trailing window only; forward
  outcomes exist only for matured events; archetype labels are PIT.

## Canon parameter snapshot

```json
{
  "conf_w": 8,
  "depth_window_bars": {
    "2B": 1260,
    "3B": 840,
    "W": 520
  },
  "grids": [
    "2B",
    "3B",
    "W"
  ],
  "macd_fast": 14,
  "macd_signal": 5,
  "macd_slow": 60,
  "ob": 80,
  "os": 20,
  "rsi_len": 14,
  "weekly_rule": "W-FRI"
}
```

## Build stamp

```json
{
  "built_at_data_asof": "2026-08-04",
  "events_backfill": 380607,
  "events_live_seed": 9192,
  "events_total": 389799,
  "split_cutoff": "2026-02-03"
}
```
