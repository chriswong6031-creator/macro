# keystone_tr0 — W0.4 keystone-gate research cohort

**basis:** `tr`  **epoch:** `tr_v0`  **RESEARCH-ONLY** (masterplan ruling A1 — no
user-facing badge may ever cite this TR cohort).

Produced by `scripts/keystone_position_gate_phase0.py` (Cycle Intelligence Masterplan
Wave W0.4). Answers the program's keystone question: *does cycle POSITION / PHASE predict
forward drawdown-adjusted returns?*

## Files

- **`backfill.parquet`** — one row per PIT stamp: for each month-end × (11 US SPDR sector
  ETFs + 24 single-country iShares ETFs), the engine's own cycle read
  (`pos, phase, signal, timing_state, osc_slope, proj_central, dc_phase, action,
  above200d`) computed on tape ≤ the stamp date, joined to bar-i+1 forward outcomes
  (`fwd_ret_{21,63,126}`, `fwd_maxdd_{21,63,126}`). Basis/epoch stamped on every row.
- **`study_tables.json`** — the aggregated study: per position-decile and per phase,
  forward drawdown-adjusted outcomes (mean fwd return, p10 drawdown, hit-rate vs base)
  with month-block bootstrap CIs, split `full` / `pre_2018` / `post_2018`, plus the
  inversion test per horizon.
- **`manifest.json`** — run provenance: universe, horizons, walk-forward split, bootstrap
  params, PIT spot-checks, git sha.

## Conventions (copied from the china grader, `engine/china_sector_cycles_grader.py`)

- **Forward anchor = bar i+1**: `first_close_strictly_after_stamp`
  (`searchsorted(side="right")`). No partial windows; a window that has not fully matured
  is dropped, never estimated.
- **CIs are month-block bootstrap** (resample whole stamp MONTHS, 800 draws, seed 7): the
  cross-section within a month is correlated, so we resample DATES, not rows (masterplan
  ruling A2). Every reported cell counts **n_months, not n_rows**.

## Regenerate

```
python -m scripts.keystone_position_gate_phase0            # full study (~20 min)
python -m scripts.keystone_position_gate_phase0 --verify   # PIT spot-checks only
python -m scripts.keystone_position_gate_phase0 --quick    # smoke (2022+ slice)
```

The script drives `engine.sector_cycles.build_sector` / `engine.country_cycles._build_one`
on a PIT-sliced close panel — the compute-frugal path (19× cheaper than the basket-building
`compute(asof=)`) that produces byte-identical `now` fields. Deterministic given the same
`data/yahoo/*.parquet` tape and seed.
