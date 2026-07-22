<!-- W4 matched-controls fingerprint study (Layer-3b). DESCRIPTIVE ONLY (WA-R1/R5/R8). -->
<!-- Machine outputs. No registration, no filters, no site surfaces. -->

# Winner Autopsy Lab — W4 Matched-Controls Fingerprint Study (Layer-3b)

**Status:** DESCRIPTIVE ONLY — no hypothesis registration, no verdicts, no filters, no site surfaces.
Rulings WA-R1 / WA-R5 / WA-R8. Spec: `research/winners/W4_CONTROLS_STUDY_SPEC.md`.
Question (Layer-3b): pre-onset, what separated eventual breakaway names from matched
controls sampled the SAME calendar day — the watchlist-formation question. Distinct
from W3 (`FINGERPRINT_CENSUS_W3.md`, WA-R8 null: winners ≈ blow-offs at onset).

**Substrate:** `winner_episodes.parquet` — manifest hash `c1a6a1cbec74a726`, harvest date `2026-07-07` (frozen; no re-harvest — spec §1).
**Run:** seed 20260722, n_boot 50,000, m=36 tests, α_Bonferroni = 0.05/36 = 0.001389.
**Estimator:** matched-set Δ = value(E,t0) − median(value(controls,t0)); month-block bootstrap with the matched set as the resampling atom (spec §4).
**Wall time:** 288.9s

## Bottom line

Machine outputs — not adjudications. The main loop appends the ruling below.

**12 feature × contrast cell(s) SEPARATE** at the α/m threshold (α/m CI excludes 0), across features: dollar_vol_z21, drawdown_from_252d_high_at_t0m21, dv_5_60_ratio, realized_vol_63d, updown_dollar_vol_ratio. See per-feature verdict lines.

**Construction caveat (mechanical, not an adjudication):** the separators are dominated by volume / realized-vol features. Of these, dollar_vol_z21, dv_5_60_ratio are DETECTOR-GATE ECHOES — the onset condition requires `dollar_vol_z21 ≥ 1 OR dv_5_60_ratio ≥ 1.5`, which holds for 100% of episodes by construction while controls are ungated on volume (see 'Volume-confirm selection linkage'). Weigh those like `excess_21d_pp`. The non-gate separators (`updown_dollar_vol_ratio`, `realized_vol_63d`, `drawdown_from_252d_high_at_t0m21`) are not direct gate echoes. Every 8-K density and RS-turn cell is NULL; `self_funded_at_t0` and `close_location_value` are UNTESTABLE (coverage).

## Population & control pool

- Equity matured episodes considered: **1,213** (crypto segregated — see honesty section).
- Included (≥ 3 eligible controls, bars present): **591**
  - of which kept_going label: 75; blow_off label: 369
- Excluded — < 3 eligible controls: **622**
- Excluded — no bars for episode ticker: **0**
- Unmatured (equity, not in analysis): 1,387
- Crypto matured (excluded from primary): 23

**Control-pool size distribution** (per episode, over episodes actually sampled):

| n_sampled | min | p25 | median | mean | p75 | max | =20 (capped) | <3 (excluded) |
|---|---|---|---|---|---|---|---|---|
| 1213 | 0 | 0.0 | 1.0 | 8.11 | 20.0 | 20 | 404 | 622 |

## Parity check (spec §3 — control-side implementation pinned to census definitions)

Episode-side recompute of `excess_21d_pp`, `dollar_vol_z21`, `dv_5_60_ratio` (via the `detect_episodes` code path: bench-aligned common index, value at t0) vs the committed parquet columns, tolerance 1e-06:

- Cells checked: **1,773**
- Pass: **1,773**
- Fail: **0**

**PASS** — recomputed trio is byte-for-value identical to the committed columns within tolerance. The one feature code path applied to controls matches the census's own definitions.

## Per-feature results (matched-set Δ)

Δ = median across episodes of [ value(E,t0) − median(value(controls,t0)) ] (continuous) or [ 1{E} − mean_j 1{C_j} ] (binary). Positive Δ = episode side higher.
CI95 = 95% month-block matched bootstrap; CIbonf = α/m percentile CI of the SAME draws (bonf_survives uses CIbonf, never CI95 — spec §0.1); CIcluster = ticker-cluster bootstrap robustness. `cov` = covered episodes / distinct t0 months.

### Contrast 1 (PRIMARY): all matured episodes vs matched controls

| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIclus_lo | CIclus_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | continuous | 1.8920 | 591 | 194 | 1.7212 | 2.0522 | 1.6467 | 2.1721 | yes | 1.7212 | 2.0459 |  |
| dv_5_60_ratio | continuous | 0.5411 | 591 | 194 | 0.4910 | 0.6011 | 0.4525 | 0.6389 | yes | 0.4928 | 0.5954 |  |
| drawdown_from_252d_high_at_t0m21 | continuous | -2.7489 | 591 | 194 | -4.6908 | -1.2226 | -6.3536 | -0.3581 | yes | -4.7485 | -1.2399 |  |
| days_below_200dma | continuous | 0.0000 | 563 | 192 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| updown_dollar_vol_ratio | continuous | 0.1427 | 591 | 194 | 0.1103 | 0.1547 | 0.0913 | 0.1718 | yes | 0.1103 | 0.1574 |  |
| close_location_value | continuous | 0.0717 | 4 | 4 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |
| realized_vol_63d | continuous | 12.6077 | 589 | 194 | 11.4424 | 14.0860 | 10.2909 | 16.0572 | yes | 10.8794 | 15.5939 |  |
| hard_event_count_126d | continuous | 0.0000 | 339 | 107 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| soft_event_count_126d | continuous | 0.0000 | 339 | 107 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| rs_turn_21_63 | binary | 0.0000 | 588 | 193 | -0.1750 | 0.2222 | -0.2500 | 0.2500 | no | -0.1339 | 0.2000 |  |
| trailing_rung_ge2 | binary | -0.1500 | 339 | 107 | -0.2353 | -0.0500 | -0.2941 | 0.0000 | no | -0.2744 | 0.0000 |  |
| self_funded_at_t0 | binary | — | 0 | 0 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |

### Contrast 2: kept_going episodes vs matched controls

| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIclus_lo | CIclus_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | continuous | 2.1603 | 75 | 46 | 1.8103 | 2.6621 | 1.3871 | 3.3661 | yes | 1.8103 | 2.6297 |  |
| dv_5_60_ratio | continuous | 0.5735 | 75 | 46 | 0.5149 | 0.7469 | 0.3595 | 0.9526 | yes | 0.5210 | 0.6988 |  |
| drawdown_from_252d_high_at_t0m21 | continuous | -0.7527 | 75 | 46 | -7.4472 | 3.5372 | -10.6242 | 5.5588 | no | -8.8302 | 3.3695 |  |
| days_below_200dma | continuous | 0.0000 | 73 | 45 | -8.5000 | 0.0000 | -14.0000 | 0.0000 | no | -7.0000 | 0.0000 |  |
| updown_dollar_vol_ratio | continuous | 0.0988 | 75 | 46 | 0.0244 | 0.1485 | -0.0067 | 0.2271 | no | 0.0262 | 0.1491 |  |
| close_location_value | continuous | — | 0 | 0 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |
| realized_vol_63d | continuous | 11.4115 | 75 | 46 | 7.7394 | 15.5939 | 4.9249 | 19.8262 | yes | 7.6809 | 15.8958 |  |
| hard_event_count_126d | continuous | 0.0000 | 50 | 27 | 0.0000 | 1.0000 | 0.0000 | 1.0000 | no | 0.0000 | 1.0000 |  |
| soft_event_count_126d | continuous | 0.0000 | 50 | 27 | -1.0000 | 0.0000 | -1.0000 | 0.5000 | no | -1.0000 | 0.0000 |  |
| rs_turn_21_63 | binary | -0.3000 | 74 | 45 | -0.4143 | 0.1000 | -0.4500 | 0.4000 | no | -0.4393 | 0.1000 |  |
| trailing_rung_ge2 | binary | -0.2566 | 50 | 27 | -0.3730 | 0.0000 | -0.5000 | 0.3889 | no | -0.3889 | 0.1500 |  |
| self_funded_at_t0 | binary | — | 0 | 0 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |

### Contrast 3: blow_off episodes vs matched controls

| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIclus_lo | CIclus_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | continuous | 1.9016 | 369 | 153 | 1.7128 | 2.0668 | 1.6344 | 2.2205 | yes | 1.7128 | 2.0586 |  |
| dv_5_60_ratio | continuous | 0.4886 | 369 | 153 | 0.4361 | 0.5738 | 0.3998 | 0.6143 | yes | 0.4361 | 0.5662 |  |
| drawdown_from_252d_high_at_t0m21 | continuous | -1.9503 | 369 | 153 | -3.8613 | 0.1085 | -5.2029 | 0.9368 | no | -3.8613 | 0.0489 |  |
| days_below_200dma | continuous | 0.0000 | 351 | 151 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| updown_dollar_vol_ratio | continuous | 0.1428 | 369 | 153 | 0.1096 | 0.1724 | 0.0728 | 0.1920 | yes | 0.1097 | 0.1724 |  |
| close_location_value | continuous | -0.0400 | 1 | 1 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |
| realized_vol_63d | continuous | 13.1003 | 367 | 153 | 11.2708 | 14.4915 | 9.5568 | 16.8951 | yes | 10.4063 | 16.8725 |  |
| hard_event_count_126d | continuous | 0.0000 | 196 | 83 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| soft_event_count_126d | continuous | 0.0000 | 196 | 83 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| rs_turn_21_63 | binary | 0.1667 | 367 | 153 | -0.1000 | 0.2500 | -0.2000 | 0.2857 | no | 0.0000 | 0.2500 |  |
| trailing_rung_ge2 | binary | -0.1303 | 196 | 83 | -0.2500 | 0.0000 | -0.3000 | 0.2105 | no | -0.3000 | 0.1000 |  |
| self_funded_at_t0 | binary | — | 0 | 0 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |

## Contrast 2 / 3 vs Contrast 1 (motion vs quality)

Spec §2: if Contrasts 2/3 mirror Contrast 1 (expected under the W3 null), that is itself the finding — pre-onset structure predicts *motion* (any breakaway onset), not *quality* (kept_going vs blow_off).

| Feature | C1 Δ | C1 bonf | C2 Δ | C2 bonf | C3 Δ | C3 bonf | mirrors C1? |
|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | 1.8920 | yes | 2.1603 | yes | 1.9016 | yes | yes |
| dv_5_60_ratio | 0.5411 | yes | 0.5735 | yes | 0.4886 | yes | yes |
| drawdown_from_252d_high_at_t0m21 | -2.7489 | yes | -0.7527 | no | -1.9503 | no | NO |
| days_below_200dma | 0.0000 | no | 0.0000 | no | 0.0000 | no | yes |
| updown_dollar_vol_ratio | 0.1427 | yes | 0.0988 | no | 0.1428 | yes | NO |
| close_location_value | 0.0717 | — | — | — | -0.0400 | — | yes |
| realized_vol_63d | 12.6077 | yes | 11.4115 | yes | 13.1003 | yes | yes |
| hard_event_count_126d | 0.0000 | no | 0.0000 | no | 0.0000 | no | yes |
| soft_event_count_126d | 0.0000 | no | 0.0000 | no | 0.0000 | no | yes |
| rs_turn_21_63 | 0.0000 | no | -0.3000 | no | 0.1667 | no | yes |
| trailing_rung_ge2 | -0.1500 | no | -0.2566 | no | -0.1303 | no | yes |
| self_funded_at_t0 | — | — | — | — | — | — | yes |

**Contrasts 2/3 do NOT fully mirror Contrast 1** — at least one feature's bonf verdict differs across the quality split. See the differing rows above.

## excess_21d_pp — tautology disclosure (parity-only, NOT a fingerprint)

`excess_21d_pp` is the detector's primary selection variable (breakaway onset ≡ excess crossing ≥20pp, or 42d ≥25pp). Controls are sampled to NOT be in candidate state within ±21td of t0. Comparing episode-vs-control excess is therefore guaranteed-positive by construction — TAUTOLOGICAL (spec §3 exclusion / §0.2), not a market regularity. It is recomputed above only to pin the parity check; it earns no fingerprint slot and is excluded from m.

Descriptive (all matured, matched-set Δ, n=591): median Δ = 19.8100 pp (episode side higher by construction).

### Volume-confirm selection linkage (construction note, NOT an adjudication)

The detector's candidate condition is `liquid & rel_breakaway & new_high & vol_confirm`, where `vol_confirm = (dollar_vol_z21 ≥ 1) OR (dv_5_60_ratio ≥ 1.5)`. That gate holds for 100% of episodes by construction, while controls are NOT gated on volume (only on excess / candidate-state). So the SEPARATES verdicts on `dollar_vol_z21` and `dv_5_60_ratio` are SELECTION-LINKED in the same way `excess_21d_pp` is — an episode is admitted partly *because* one of these was elevated at t0. Read them as detector-gate echoes, not discovered fingerprints; the main-loop ruling should weigh them accordingly. `updown_dollar_vol_ratio` and `realized_vol_63d` are NOT in the candidate condition, so their separation is not a direct gate echo (though volume/vol elevation is correlated with the excess move that IS gated). This note states a construction fact; it does not change any SEPARATES/NULL/UNTESTABLE cell above.

## Honesty section

### Survivor-only (spec §0.5)

The census and its control pool are survivor-lean: the `survivorship_biased` column is an unpopulated constant (False), and no dead-name price source is present in this parquet's `price_source` (yahoo/massive only). No survivorship stratum is tested or claimed — the gap is stated, not resolved.

### Per-feature coverage (episode-side AND control-side)

| Feature | ep covered | ep total | ep % | ctrl covered | ctrl total | ctrl % |
|---|---|---|---|---|---|---|
| dollar_vol_z21 | 591 | 591 | 100% | 9793 | 9813 | 100% |
| dv_5_60_ratio | 591 | 591 | 100% | 9732 | 9813 | 99% |
| drawdown_from_252d_high_at_t0m21 | 591 | 591 | 100% | 9746 | 9813 | 99% |
| days_below_200dma | 564 | 591 | 95% | 9076 | 9813 | 92% |
| updown_dollar_vol_ratio | 591 | 591 | 100% | 9746 | 9813 | 99% |
| close_location_value | 4 | 591 | 1% | 2938 | 9813 | 30% |
| realized_vol_63d | 590 | 591 | 100% | 9586 | 9813 | 98% |
| hard_event_count_126d | 340 | 591 | 58% | 6517 | 9813 | 66% |
| soft_event_count_126d | 340 | 591 | 58% | 6517 | 9813 | 66% |
| rs_turn_21_63 | 589 | 591 | 100% | 9581 | 9813 | 98% |
| trailing_rung_ge2 | 340 | 591 | 58% | 6517 | 9813 | 66% |
| self_funded_at_t0 | 254 | 591 | 43% | 0 | 9813 | 0% |

**NON-COMPARABLE:** `self_funded_at_t0` (B2 fundamentals) coverage is below 30% on at least one side — printed in the tables but must not be interpreted as representative. Control-side B2 is not joined at census scale here (statements panel + A2 firewall), so this feature is UNTESTABLE for the contrast.

### Excluded-episode counts

- < 3 eligible controls: 622
- no bars for episode ticker: 0
- crypto (7-day calendar + SPY benchmark category error): 23 matured
- unmatured (forward windows not closed): 1,387

### gap_leg_crossed == False stratum (Contrast 1 rerun)

| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | continuous | 1.9217 | 369 | 157 | 1.7194 | 2.1362 | 1.6247 | 2.2723 | yes |  |
| dv_5_60_ratio | continuous | 0.5018 | 369 | 157 | 0.4516 | 0.5827 | 0.4153 | 0.6277 | yes |  |
| drawdown_from_252d_high_at_t0m21 | continuous | -2.0273 | 369 | 157 | -3.6799 | 0.0791 | -4.9412 | 0.9435 | no |  |
| days_below_200dma | continuous | 0.0000 | 360 | 155 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |  |
| updown_dollar_vol_ratio | continuous | 0.1268 | 369 | 157 | 0.0767 | 0.1505 | 0.0605 | 0.1825 | yes |  |
| close_location_value | continuous | -0.0400 | 1 | 1 | — | — | — | — | — | insufficient covered episodes (<5) |
| realized_vol_63d | continuous | 11.4850 | 368 | 157 | 9.4220 | 12.9971 | 7.6809 | 14.2179 | yes |  |
| hard_event_count_126d | continuous | 0.0000 | 176 | 71 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |  |
| soft_event_count_126d | continuous | 0.0000 | 176 | 71 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |  |
| rs_turn_21_63 | binary | 0.0000 | 367 | 156 | -0.2000 | 0.2000 | -0.2857 | 0.2500 | no |  |
| trailing_rung_ge2 | binary | -0.1500 | 176 | 71 | -0.2500 | -0.0526 | -0.3158 | 0.0000 | no |  |
| self_funded_at_t0 | binary | — | 0 | 0 | — | — | — | — | — | insufficient covered episodes (<5) |

### What W4 cannot see

Per-ticker options positioning, analyst-revision breadth, and PIT short-interest are still forward-accruing (joins began ~2026-06 per the masterplan clock; first answerable ~2027-06). W4 tests only t0 price/volume geometry and trailing 8-K density — the substrates that exist today. A null here closes the tested constructions, not the search space (house epistemics: 'not found yet' ≠ 'does not exist').

## Per-feature verdicts (SEPARATES / NULL / UNTESTABLE)

SEPARATES = α/m CI excludes 0; NULL = α/m CI contains 0 with adequate coverage; UNTESTABLE = insufficient coverage / degenerate (no CI) / NON-COMPARABLE.

**Contrast 1 (PRIMARY): all matured episodes vs matched controls**

- dollar_vol_z21 [all_matured]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=1.8920, α/m [1.6467, 2.1721])
- dv_5_60_ratio [all_matured]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=0.5411, α/m [0.4525, 0.6389])
- drawdown_from_252d_high_at_t0m21 [all_matured]: SEPARATES — α/m CI excludes 0 (lower in episodes; Δ=-2.7489, α/m [-6.3536, -0.3581])
- days_below_200dma [all_matured]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- updown_dollar_vol_ratio [all_matured]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=0.1427, α/m [0.0913, 0.1718])
- close_location_value [all_matured]: UNTESTABLE (insufficient covered episodes (<5))
- realized_vol_63d [all_matured]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=12.6077, α/m [10.2909, 16.0572])
- hard_event_count_126d [all_matured]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- soft_event_count_126d [all_matured]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- rs_turn_21_63 [all_matured]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [-0.1750, 0.2222])
- trailing_rung_ge2 [all_matured]: NULL — α/m CI contains 0 (Δ=-0.1500, 95% [-0.2353, -0.0500])
- self_funded_at_t0 [all_matured]: UNTESTABLE (insufficient covered episodes (<5))

**Contrast 2: kept_going episodes vs matched controls**

- dollar_vol_z21 [kept_going]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=2.1603, α/m [1.3871, 3.3661])
- dv_5_60_ratio [kept_going]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=0.5735, α/m [0.3595, 0.9526])
- drawdown_from_252d_high_at_t0m21 [kept_going]: NULL — α/m CI contains 0 (Δ=-0.7527, 95% [-7.4472, 3.5372])
- days_below_200dma [kept_going]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [-8.5000, 0.0000])
- updown_dollar_vol_ratio [kept_going]: NULL — α/m CI contains 0 (Δ=0.0988, 95% [0.0244, 0.1485])
- close_location_value [kept_going]: UNTESTABLE (insufficient covered episodes (<5))
- realized_vol_63d [kept_going]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=11.4115, α/m [4.9249, 19.8262])
- hard_event_count_126d [kept_going]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 1.0000])
- soft_event_count_126d [kept_going]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [-1.0000, 0.0000])
- rs_turn_21_63 [kept_going]: NULL — α/m CI contains 0 (Δ=-0.3000, 95% [-0.4143, 0.1000])
- trailing_rung_ge2 [kept_going]: NULL — α/m CI contains 0 (Δ=-0.2566, 95% [-0.3730, 0.0000])
- self_funded_at_t0 [kept_going]: UNTESTABLE (insufficient covered episodes (<5))

**Contrast 3: blow_off episodes vs matched controls**

- dollar_vol_z21 [blow_off]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=1.9016, α/m [1.6344, 2.2205])
- dv_5_60_ratio [blow_off]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=0.4886, α/m [0.3998, 0.6143])
- drawdown_from_252d_high_at_t0m21 [blow_off]: NULL — α/m CI contains 0 (Δ=-1.9503, 95% [-3.8613, 0.1085])
- days_below_200dma [blow_off]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- updown_dollar_vol_ratio [blow_off]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=0.1428, α/m [0.0728, 0.1920])
- close_location_value [blow_off]: UNTESTABLE (insufficient covered episodes (<5))
- realized_vol_63d [blow_off]: SEPARATES — α/m CI excludes 0 (higher in episodes; Δ=13.1003, α/m [9.5568, 16.8951])
- hard_event_count_126d [blow_off]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- soft_event_count_126d [blow_off]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- rs_turn_21_63 [blow_off]: NULL — α/m CI contains 0 (Δ=0.1667, 95% [-0.1000, 0.2500])
- trailing_rung_ge2 [blow_off]: NULL — α/m CI contains 0 (Δ=-0.1303, 95% [-0.2500, 0.0000])
- self_funded_at_t0 [blow_off]: UNTESTABLE (insufficient covered episodes (<5))

## Adjudication (main loop)

PENDING

