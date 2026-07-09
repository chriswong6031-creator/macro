# Stock-Personality Setup Compatibility — Phase 0

> **Pre-registration note:** trial family registered under `stock_personality_compat`
> in `data/trial_ledger.jsonl` BEFORE any outcome was read (R-SP11).
> Every null result is printed; no cell is silently dropped.
> FY2009+ archetype PIT coverage only (R-SP12).
> Survivorship-flagged: deep corpus is 220-name survivor panel.

## 1. Registration summary

- Registration date: 2026-07-07
- FDR family: `stock_personality_compat` | q=0.05
- Primary ruler: `clean15_126` (P(STOPPED) binary)
- Inference: two_way_cluster_bootstrap (ticker x quarter) — satisfies DT-R14 / #1841 time-confound law
- Minimum cell n: 50 (cells below this: insufficient_n, not tested)
- Archetype collapse min_n: 400 (merged into 'other_archetype')

**Corpus sizes (registered):**

| Corpus | n |
|--------|---|
| track_record | 26439 |
| gate_fires | 38250 |
| replay | 0 |

Total registered hypotheses: **48**

## 2. Analyzable-n per axis

### track_record (n_gradable=26108)

**chart_personality** label distribution:

| label | n | testable |
|-------|---|----------|
| mixed_chart | 17735 | yes |
| failed_breakout_trap | 3196 | yes |
| smooth_compounder_grind | 2037 | yes |
| stair_step_leader | 1569 | yes |
| mean_reversion_rubber_band | 1414 | yes |

**microstructure** label distribution:

| label | n | testable |
|-------|---|----------|
| tight_spread_absorber | 8905 | yes |
| wide_spread_impact | 7639 | yes |
| mixed_microstructure | 5909 | yes |
| slow_mean_reversion_liquidity | 3532 | yes |
| gap_discontinuity_risk | 123 | yes |

**archetype** label distribution:

| label | n | testable |
|-------|---|----------|
| mixed | 3088 | yes |
| rate_sensitive | 1342 | yes |
| cyclical | 1097 | yes |
| speculative_unprofitable | 772 | yes |
| financial | 637 | yes |
| other_archetype | 386 | yes |
| distressed | 366 | yes |
| high_beta_momentum | 280 | yes |
| secular_growth | 228 | yes |
| deep_value | 219 | yes |

### gate_fires (n_gradable=37727)

**chart_personality** label distribution:

| label | n | testable |
|-------|---|----------|
| mixed_chart | 24887 | yes |
| failed_breakout_trap | 4404 | yes |
| smooth_compounder_grind | 3260 | yes |
| stair_step_leader | 2688 | yes |
| mean_reversion_rubber_band | 1969 | yes |

**microstructure** label distribution:

| label | n | testable |
|-------|---|----------|
| tight_spread_absorber | 12820 | yes |
| wide_spread_impact | 11169 | yes |
| mixed_microstructure | 8453 | yes |
| slow_mean_reversion_liquidity | 5094 | yes |
| gap_discontinuity_risk | 191 | yes |

**archetype** label distribution:

| label | n | testable |
|-------|---|----------|
| mixed | 4429 | yes |
| rate_sensitive | 1924 | yes |
| cyclical | 1663 | yes |
| speculative_unprofitable | 1122 | yes |
| financial | 979 | yes |
| other_archetype | 591 | yes |
| distressed | 503 | yes |
| high_beta_momentum | 389 | yes |
| deep_value | 331 | yes |
| secular_growth | 291 | yes |

## 3. Primary results (P(STOPPED) delta, two-way cluster-robust)

> **Time-confound citation (DT-R14 / #1841):** ticker-cluster CIs WITHOUT
> time control are anti-conservative. The two-way (ticker × quarter) clustering
> below satisfies the calendar-time control law. Do NOT interpret one-way
> ticker-only CIs as the primary inference.

> **BH denominator = 40 tested cells** (insufficient_n cells are never
> tested per R-SP11 and excluded; 8 cells excluded on this basis).
> The registered budget is the conservative pre-declared upper bound covering all cells
> including those that turn out to have insufficient n.

| corpus | axis | label | n | delta | p_value | ci_lo | ci_hi | BH-reject | n_ticker_clust | n_quarter_clust | status |
|--------|------|-------|---|-------|---------|-------|-------|-----------|----------------|-----------------|--------|
| track_record | chart_personality | smooth_compounder_grind | 2037 | -0.0256 | 0.2720 | -0.0720 | 0.0205 | no | 219 | 253 | tested |
| track_record | chart_personality | stair_step_leader | 1569 | 0.0299 | 0.2225 | -0.0187 | 0.0775 | no | 219 | 253 | tested |
| track_record | chart_personality | volatile_momentum_vehicle | 0 | — | — | — | — | — | — | — | insufficient_n |
| track_record | chart_personality | mean_reversion_rubber_band | 1414 | -0.0210 | 0.4530 | -0.0755 | 0.0347 | no | 219 | 253 | tested |
| track_record | chart_personality | basing_accumulator | 0 | — | — | — | — | — | — | — | insufficient_n |
| track_record | chart_personality | event_gapper | 0 | — | — | — | — | — | — | — | insufficient_n |
| track_record | chart_personality | failed_breakout_trap | 3196 | -0.0077 | 0.6900 | -0.0481 | 0.0333 | no | 219 | 253 | tested |
| track_record | chart_personality | defensive_range_stock | 0 | — | — | — | — | — | — | — | insufficient_n |
| track_record | chart_personality | mixed_chart | 17735 | 0.0084 | 0.5110 | -0.0158 | 0.0353 | no | 219 | 253 | tested |
| track_record | microstructure | tight_spread_absorber | 8905 | -0.0052 | 0.8140 | -0.0484 | 0.0401 | no | 219 | 253 | tested |
| track_record | microstructure | wide_spread_impact | 7639 | -0.0159 | 0.4575 | -0.0572 | 0.0267 | no | 219 | 253 | tested |
| track_record | microstructure | gap_discontinuity_risk | 123 | 0.0165 | 0.8470 | -0.1910 | 0.2247 | no | 219 | 253 | tested |
| track_record | microstructure | slow_mean_reversion_liquidity | 3532 | 0.0062 | 0.7655 | -0.0341 | 0.0450 | no | 219 | 253 | tested |
| track_record | microstructure | mixed_microstructure | 5909 | 0.0208 | 0.2195 | -0.0144 | 0.0539 | no | 219 | 253 | tested |
| track_record | archetype | high_beta_momentum | 280 | 0.0400 | 0.4700 | -0.0832 | 0.1456 | no | 219 | 253 | tested |
| track_record | archetype | mixed | 3088 | -0.0497 | 0.0520 | -0.1008 | 0.0002 | no | 219 | 253 | tested |
| track_record | archetype | distressed | 366 | 0.0406 | 0.4945 | -0.0857 | 0.1644 | no | 219 | 253 | tested |
| track_record | archetype | rate_sensitive | 1342 | 0.0275 | 0.4635 | -0.0465 | 0.0999 | no | 219 | 253 | tested |
| track_record | archetype | financial | 637 | -0.0073 | 0.8740 | -0.0981 | 0.0849 | no | 219 | 253 | tested |
| track_record | archetype | cyclical | 1097 | 0.0261 | 0.4665 | -0.0461 | 0.0984 | no | 219 | 253 | tested |
| track_record | archetype | speculative_unprofitable | 772 | 0.0523 | 0.1650 | -0.0206 | 0.1233 | no | 219 | 253 | tested |
| track_record | archetype | other_archetype | 386 | -0.0287 | 0.5960 | -0.1280 | 0.0822 | no | 219 | 253 | tested |
| track_record | archetype | secular_growth | 228 | -0.0020 | 0.9825 | -0.1373 | 0.1440 | no | 219 | 253 | tested |
| track_record | archetype | deep_value | 219 | 0.0244 | 0.7426 | -0.1322 | 0.1674 | no | 219 | 253 | tested |
| gate_fires | chart_personality | smooth_compounder_grind | 3260 | -0.0303 | 0.1230 | -0.0703 | 0.0073 | no | 219 | 254 | tested |
| gate_fires | chart_personality | stair_step_leader | 2688 | 0.0345 | 0.0540 | -0.0002 | 0.0706 | no | 219 | 254 | tested |
| gate_fires | chart_personality | volatile_momentum_vehicle | 0 | — | — | — | — | — | — | — | insufficient_n |
| gate_fires | chart_personality | mean_reversion_rubber_band | 1969 | -0.0112 | 0.6470 | -0.0593 | 0.0342 | no | 219 | 254 | tested |
| gate_fires | chart_personality | basing_accumulator | 0 | — | — | — | — | — | — | — | insufficient_n |
| gate_fires | chart_personality | event_gapper | 0 | — | — | — | — | — | — | — | insufficient_n |
| gate_fires | chart_personality | failed_breakout_trap | 4404 | 0.0022 | 0.8920 | -0.0298 | 0.0365 | no | 219 | 254 | tested |
| gate_fires | chart_personality | defensive_range_stock | 0 | — | — | — | — | — | — | — | insufficient_n |
| gate_fires | chart_personality | mixed_chart | 24887 | -0.0010 | 0.9245 | -0.0217 | 0.0195 | no | 219 | 254 | tested |
| gate_fires | microstructure | tight_spread_absorber | 12820 | -0.0187 | 0.3570 | -0.0577 | 0.0240 | no | 219 | 254 | tested |
| gate_fires | microstructure | wide_spread_impact | 11169 | -0.0101 | 0.6135 | -0.0496 | 0.0276 | no | 219 | 254 | tested |
| gate_fires | microstructure | gap_discontinuity_risk | 191 | 0.0226 | 0.7829 | -0.1623 | 0.1786 | no | 219 | 254 | tested |
| gate_fires | microstructure | slow_mean_reversion_liquidity | 5094 | 0.0121 | 0.4755 | -0.0199 | 0.0456 | no | 219 | 254 | tested |
| gate_fires | microstructure | mixed_microstructure | 8453 | 0.0275 | 0.0850 | -0.0052 | 0.0580 | no | 219 | 254 | tested |
| gate_fires | archetype | high_beta_momentum | 389 | 0.0379 | 0.4290 | -0.0654 | 0.1401 | no | 219 | 254 | tested |
| gate_fires | archetype | mixed | 4429 | -0.0526 | 0.0395 | -0.1007 | -0.0036 | no | 219 | 254 | tested |
| gate_fires | archetype | distressed | 503 | 0.0365 | 0.4605 | -0.0666 | 0.1418 | no | 219 | 254 | tested |
| gate_fires | archetype | rate_sensitive | 1924 | 0.0192 | 0.5130 | -0.0353 | 0.0744 | no | 219 | 254 | tested |
| gate_fires | archetype | financial | 979 | -0.0255 | 0.5435 | -0.1128 | 0.0620 | no | 219 | 254 | tested |
| gate_fires | archetype | cyclical | 1663 | -0.0070 | 0.8270 | -0.0681 | 0.0573 | no | 219 | 254 | tested |
| gate_fires | archetype | speculative_unprofitable | 1122 | 0.0529 | 0.0920 | -0.0085 | 0.1136 | no | 219 | 254 | tested |
| gate_fires | archetype | other_archetype | 591 | -0.0300 | 0.4550 | -0.1042 | 0.0506 | no | 219 | 254 | tested |
| gate_fires | archetype | secular_growth | 291 | -0.0039 | 0.9520 | -0.1241 | 0.1291 | no | 219 | 254 | tested |
| gate_fires | archetype | deep_value | 331 | 0.0119 | 0.8319 | -0.0946 | 0.1255 | no | 219 | 254 | tested |

## 4. Disguise verdict (FDR survivors only)

Regression: `outcome ~ label + sector FE + log(mktcap) + era FE`, cluster-robust.
A label stamped `redundant_with_sector_size` is barred from chips implying differentiation.

> **log(mktcap) OMITTED** from disguise regression: `market_cap` column unavailable in archetype history for this run. Size confound is only partially controlled via sector fixed effects. Interpret disguise verdict with this caveat.

**No FDR survivors — all null (pre-committed expected outcome; descriptive card unchanged).**


## 5. Secondaries (descriptive)

Secondaries P(DEAD_MONEY), P(CLEAN_LIFTOFF), MAE/MFE are descriptive;
not tested for significance; not BH-corrected.

**P(DEAD_MONEY) by corpus:**
- gate_fires: 0.003
- track_record: 0.002

**P(CLEAN_LIFTOFF) by corpus:**
- gate_fires: 0.342
- track_record: 0.387

## 6. Honest limitations

- **gap-features-unavailable on deep corpus:** `data/stocks` has no `open` column.
  Features `event_gap_contrib_252` and `gap_share_252` are NaN for the deep 220-name
  panel; labels that depend on them (event_gapper) may be systematically unattached.
- **Survivorship bias:** deep 220-name corpus is today's survivors; pre-2009 fires
  are graded on survivor prices — counts are UPPER BOUNDS on favorable outcomes.
  Watermark: FY2009+ archetype PIT coverage only.
- **Two-way clustering (DT-R14 / #1841):** ticker × quarter clustering satisfies
  the time-confound law (#1841, Phase A gate amendments). Weakening to one-way
  ticker-only clustering is prohibited by house law.
- **PIT archetype join:** FY2009+ only; ~57% of deep-history fires pre-date the
  first attachable row and carry archetype_pit=null (printed per cell, never filled).
- **chart/micro labels:** available only for tickers in personality_pit_labels.parquet.
  If that file is absent, chart+micro axis cells will all be null.
- **dna_class / ownership_habitat:** NOT retro-attachable (partition history 2025-06;
  ownership stores snapshot-grade). Excluded from retro study; forward-ledger only.
- **Replay corpus:** skipped when --replay-root absent (SKIP noted here).
