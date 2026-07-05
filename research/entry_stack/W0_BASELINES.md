# W0 Incumbent Baselines — Entry-Stack Expansion

**Status:** W0 recompute under the program grader (RUL-9).
All numbers here use `engine.grading` barrier definitions:
- Rotational: liftoff 1.08×, horizon 21d, stop 0.95×, cushion 1.05×
- Positional:  liftoff 1.15×, horizon 126d, stop 0.95×, cushion 1.05×

Wave1-era numbers (clean15=1.20+durable-hold) are historical context only
and may NOT satisfy any promotion bar (RUL-9).

---

## Trial Registration

All program families registered at W0 run time (idempotent, appended to
`data/trial_ledger.jsonl`):

| Family | Budget | Basis |
|---|---|---|
| `esx_null_competitors` | 6 | 2 NC x 3 panels |
| `esx_ev_blackout` | 9 | k in {1,2,3} x 3 panels (k=3 primary) |
| `esx_ur_phase0` | 36 | 2 lows x 3 reclaim windows x 2 depth-arms x 3 forms; ATR mult frozen 1.0 |
| `esx_sq_phase0` | 12 | frozen state grid x 2 panels x 3 forms + 3 named sensitivities |
| `esx_lq_bands` | 12 | 2 proxies x 3 fixed-tercile bands x 2 panels |
| `esx_ql_overlay` | 12 | 3 quality defs (Piotroski, Altman, Sloan-tercile) x 2 horizons x 2 forms |
| `esx_ts_adx` | 4 | 1 def x 2 panels x 2 era-splits |
| `esx_appendix` | 24 | capped; unlocked only after F-tier verdicts filed |

---

## FE Granularity Choices (Frozen per RUL-12)

| Panel | fe_granularity | Sector coverage | Sector fallback? |
|---|---|---|---|
| deep | `date` | 100% | No |
| baskets | `date` | 20% | YES — date-only episode blocks |

Post-hoc switching between FE granularities is banned (RUL-12).

---

## Panel: deep

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only. Comparisons within-era are directionally valid.

- Total fires loaded: 38,250
- Gradable (both horizons matured): 37,722
- Sector coverage: 100%
- FE granularity: `date`

### Tier Summary (all eras, gradable fires)

| Tier | N fires | Stop5 rate | Rot liftoff | Pos liftoff | Dead money | MAE63 mean | MFE63 mean |
|---|---|---|---|---|---|---|---|
| T1 | 33,604 | 11.6% | 24.7% | 34.4% | 0.3% | -0.0831 | 0.1275 |
| T2 | 2,622 | 12.0% | 26.5% | 32.5% | 0.3% | -0.0870 | 0.1364 |
| T3 | 1,496 | 13.0% | 24.8% | 32.8% | 0.1% | -0.0886 | 0.1326 |

### Era × Tier Table (program eras: 2012-2026)

| era | tier | n_fires | stop5_rate | rot_liftoff_rate | pos_liftoff_rate | dead_money_rate | mae63_mean | days_to_10_median |
|---|---|---|---|---|---|---|---|---|
| 2012-2015 | T1 | 3384 | 6.2% | 15.7% | 34.0% | 0.3% | -0.0624 | 51d |
| 2012-2015 | T2 | 215 | 8.4% | 20.9% | 31.2% | 0.9% | -0.0631 | 38d |
| 2012-2015 | T3 | 126 | 7.9% | 15.9% | 34.9% | 0.0% | -0.0650 | 50d |
| 2016-2019 | T1 | 3363 | 7.5% | 18.5% | 33.5% | 0.2% | -0.0689 | 49d |
| 2016-2019 | T2 | 215 | 7.9% | 20.0% | 28.8% | 0.0% | -0.0793 | 40d |
| 2016-2019 | T3 | 137 | 6.6% | 19.0% | 26.3% | 0.7% | -0.0824 | 41d |
| 2020-2022 | T1 | 2644 | 14.6% | 30.4% | 32.9% | 0.0% | -0.0960 | 30d |
| 2020-2022 | T2 | 200 | 13.5% | 28.5% | 31.0% | 0.0% | -0.1014 | 34d |
| 2020-2022 | T3 | 129 | 10.8% | 21.7% | 27.9% | 0.0% | -0.1057 | 40d |
| 2023-2026 | T1 | 2727 | 9.7% | 26.2% | 36.4% | 0.0% | -0.0767 | 36d |
| 2023-2026 | T2 | 209 | 9.6% | 22.0% | 31.1% | 0.0% | -0.0816 | 39d |
| 2023-2026 | T3 | 93 | 14.0% | 20.4% | 28.0% | 0.0% | -0.0869 | 38d |


## Panel: baskets

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only. Comparisons within-era are directionally valid.

- Total fires loaded: 113,542
- Gradable (both horizons matured): 107,127
- Sector coverage: 20%
- FE granularity: `date`

### Tier Summary (all eras, gradable fires)

| Tier | N fires | Stop5 rate | Rot liftoff | Pos liftoff | Dead money | MAE63 mean | MFE63 mean |
|---|---|---|---|---|---|---|---|
| T1 | 92,021 | 20.0% | 29.9% | 31.1% | 0.2% | -0.1245 | 0.1873 |
| T2 | 8,604 | 20.6% | 29.8% | 30.8% | 0.4% | -0.1323 | 0.1998 |
| T3 | 6,502 | 18.4% | 32.4% | 33.1% | 0.5% | -0.1267 | 0.1777 |

### Era × Tier Table (program eras: 2012-2026)

| era | tier | n_fires | stop5_rate | rot_liftoff_rate | pos_liftoff_rate | dead_money_rate | mae63_mean | days_to_10_median |
|---|---|---|---|---|---|---|---|---|
| 2012-2015 | T1 | 7528 | 17.9% | 18.3% | 20.3% | 0.5% | -0.1202 | 39d |
| 2012-2015 | T2 | 1260 | 14.0% | 26.7% | 27.5% | 0.6% | -0.1238 | 39d |
| 2012-2015 | T3 | 2092 | 10.5% | 32.5% | 35.9% | 0.3% | -0.0999 | 36d |
| 2016-2019 | T1 | 29381 | 14.1% | 26.6% | 32.8% | 0.3% | -0.1040 | 34d |
| 2016-2019 | T2 | 2317 | 15.8% | 25.9% | 34.3% | 0.5% | -0.1123 | 32d |
| 2016-2019 | T3 | 1493 | 15.5% | 29.4% | 32.3% | 0.4% | -0.1234 | 32d |
| 2020-2022 | T1 | 25734 | 26.1% | 33.0% | 29.6% | 0.2% | -0.1436 | 22d |
| 2020-2022 | T2 | 2488 | 25.6% | 32.5% | 29.6% | 0.5% | -0.1515 | 25d |
| 2020-2022 | T3 | 1572 | 27.0% | 34.2% | 31.1% | 1.2% | -0.1563 | 24d |
| 2023-2026 | T1 | 29378 | 21.1% | 33.5% | 33.5% | 0.1% | -0.1294 | 25d |
| 2023-2026 | T2 | 2539 | 23.4% | 32.3% | 30.5% | 0.0% | -0.1358 | 24d |
| 2023-2026 | T3 | 1345 | 23.8% | 33.6% | 31.7% | 0.0% | -0.1376 | 23d |


---

## Statistical notes

### days_to_10 — descriptive only, excluded from FDR promotion panel

`days_to_10` (median bars to +10% gain) is computed and reported in the era × tier
tables as a descriptive speed metric.  It is **not** included in the `effect_table`
BH-corrected FDR panel.

Reason: `days_to_10` is defined only for fires that *reached* +10%, making it a
selection-biased (collider) outcome.  Whether a fire ever reaches +10% is itself
a near-equivalent of the positional-liftoff endpoint.  Conditioning on "reached +10%"
opens a selection channel: the stratum coefficient in the conditional population is
not a clean causal stratum effect.  This does not affect the primary endpoint
(`stop5`) or the other FDR-panelled outcomes.

Correct interpretation: the `days_to_10_median` column in the era table shows the
**conditional speed** (given the fire reaches +10%), stratified by era and tier.
Comparison across tiers should be read as "among fires that did reach +10%, how
quickly did each tier reach it?" — not as an unconditional stratum causal effect.

---

## Deferrals

### NC-2 Entry Quality Bands (RUL-3)

**DEFERRED to W1/S-UR study PR.**

`engine.cycles.entry_quality()` requires per-fire computation of cyc/mtf/early/regime
dicts — each a full cycles.py call chain — making per-fire band assignment too heavy
for W0 baseline computation (~224 tickers × ~38k fires on deep panel).

The hook is present in `r1_estimate(entry_quality_bands=True)` and the loader
interface is defined (pass `eq_band` column in graded DataFrame). The NC-2
marginality test (coefficient survives eq-band FE) runs in W1 when the first
candidate study generates per-fire eq-band labels efficiently (e.g., as a
batch-computed lookup table per ticker×year-quarter).

### COILED/COILED-FIRE Recall Recompute

**DEFERRED to S-UR study PR.**

The COILED state is computed via engine/cycles.py which requires the full
per-ticker cycle state stack. Recomputing recall under the program grader
requires running the full cycle pipeline over all fire dates — scoped to
the S-UR phase0 PR where the COILED∩S-UR intersection is the primary subject.

---

*Generated by `scripts/research/entry_strata_phase0.py --baselines`*
*Grader: engine/grading.py (barriers above). Wave1 numbers = historical context only.*