<!-- W3 census fingerprint study. DESCRIPTIVE ONLY (WA-R1/R5/R8). -->

# Winner Autopsy Lab — W3 Census Fingerprint Study (Layer-3a)

**Status:** DESCRIPTIVE ONLY — no hypothesis registration, no verdicts, no filters, no site surfaces.
Rulings WA-R1 / WA-R5 / WA-R8. Spec: `research/winners/W3_CENSUS_STUDY_SPEC.md`.

**Substrate:** `winner_episodes.parquet` — manifest hash `c1a6a1cbec74a726`, harvest date `2026-07-07`.
**Run:** seed 20260720, n_boot 10000, m=34 tests, α_Bonferroni = 0.05/34 = 0.00147.
**Wall time:** 75.8s

## Bottom line

Results are machine outputs from the full census — not adjudications. The main loop appends WA-R8 below.

| W2 candidate | Census verdict |
|---|---|
| F1 — catalyst-ladder rung count (trailing pre-t0) | CI CONTAINS ZERO — no detectable difference at 95% |
| F1 — catalyst-ladder rung count (early-move, t0+21td) | CI CONTAINS ZERO — no detectable difference at 95% |
| F2 — trigger gap holds (gap_hold_5) | CI EXCLUDES ZERO — higher in kept_going (Bonferroni survives) |
| F3 — profit step-up faster than revenue | UNTESTABLE — A2 firewall excludes t0>=2024; coverage < 30% in primary group (NON-COMPARABLE) |
| F4 — new 63d high AND excess_21d≥20pp | CI EXCLUDES ZERO — higher in kept_going (Bonferroni survives) |
| F5 — sector beta ruled out (excess_21d_pp) | CI EXCLUDES ZERO — higher in kept_going (Bonferroni survives) |
| F6 — compressed prior | UNTESTABLE — structurally blocked (no PIT short-interest/options/dispersion history) |

### F1 window-direction finding (spec §3 circularity guard)

**Verified:** `hard_event_count_126d` / `soft_event_count_126d` / `soft_then_hard` in
`engine/winner_autopsy.py:_b1_features` use the PRE-ONSET window: `filing_date strictly < t0,
within 126 calendar days of t0` (lines 1228-1230). These are TRAILING counts, NOT forward-looking.
They do NOT overlap the labeling horizon. Path taken: **use them directly as pure-t0 features**,
and additionally compute F1 early-move conditioner from material_8k_events bounded to (t0, t0+21td].

## Population

Total episodes (full census): **2,650** / 457 tickers
t0 range: 1997-07-23 → 2026-07-02

| Outcome label | Count |
|---|---|
| unmatured | 1,414 |
| blow_off | 773 |
| failed | 313 |
| durable_winner | 129 |
| clean_hold | 21 |

**Matured (analysis population):**

| Group | Definition | Count |
|---|---|---|
| kept_going (PRIMARY) | durable_winner + clean_hold | 150 |
| blow_off (Contrast 1) | blow_off | 773 |
| failed (Contrast 2) | failed | 313 |
| **unmatured** (not in analysis — counted here) | unmatured | 1,414 |

Blow_off:kept_going ratio: 5.2:1 (census is blow_off-dominated as expected).

## Feature results

m = 34 tests. Bonferroni threshold α/m = 0.00147.
CI = 95% month-block paired bootstrap percentile CI (10,000 reps, seed 20260720).
Wilson CI = cross-check for binary features (Newcombe method).
ALL rows printed regardless of significance (census, not a screen).

### Contrast: kept_going vs blow_off

| Feature | Tier | Rate A | n_A | Rate B | n_B | Diff | CI_lo | CI_hi | Bonf | Wilson_lo | Wilson_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| new_high_63d | pure_t0 | 100.0% | 150 | 100.0% | 773 | 0.0000 | 0.0000 | 0.0000 | no | -0.0250 | 0.0049 |  |
| liquid | pure_t0 | 100.0% | 150 | 100.0% | 773 | 0.0000 | 0.0000 | 0.0000 | no | -0.0250 | 0.0049 |  |
| self_funded_at_t0 | pure_t0 | 37.5% | 32 | 48.7% | 150 | -0.1117 | -0.3221 | 0.0857 | no | -0.3366 | 0.1394 |  |
| f4_composite | pure_t0 | 69.3% | 150 | 57.2% | 773 | 0.1215 | 0.0280 | 0.2076 | YES | 0.0092 | 0.2249 |  |
| trailing_rung_ge2 | pure_t0 | 20.9% | 129 | 23.8% | 610 | -0.0284 | -0.1124 | 0.0533 | no | -0.1250 | 0.0818 |  |
| soft_then_hard | pure_t0 | 38.1% | 42 | 35.8% | 207 | 0.0235 | -0.1684 | 0.1960 | no | -0.1748 | 0.2365 |  |
| f1_fwd_rung_ge2 | early_move | 27.3% | 66 | 16.7% | 324 | 0.1061 | -0.0049 | 0.2017 | no | -0.0311 | 0.2604 |  |
| gap_hold_3 | early_move | 100.0% | 150 | 66.0% | 773 | 0.3402 | 0.3003 | 0.3823 | YES | 0.2827 | 0.3743 |  |
| gap_hold_5 | early_move | 100.0% | 150 | 54.3% | 773 | 0.4567 | 0.4119 | 0.5043 | YES | 0.3969 | 0.4919 |  |
| gap_hold_10 | early_move | 100.0% | 150 | 40.8% | 773 | 0.5925 | 0.5501 | 0.6352 | YES | 0.5325 | 0.6266 |  |
| f3_profit_stepup | pure_t0 | 29.0% | 31 | 26.3% | 152 | 0.0272 | -0.1533 | 0.2059 | no | -0.1774 | 0.2663 |  |

| Feature | Tier | Median A | n_A | Median B | n_B | Diff | CI_lo | CI_hi | Bonf | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| excess_21d_pp | pure_t0 | 22.6409 | 150 | 20.7436 | 773 | 1.8973 | 0.6027 | 3.2920 | YES |  |
| dollar_vol_z21 | pure_t0 | 2.0459 | 150 | 1.9529 | 773 | 0.0929 | -0.1963 | 0.5124 | no |  |
| dv_5_60_ratio | pure_t0 | 1.5561 | 150 | 1.5332 | 773 | 0.0229 | -0.0690 | 0.1404 | no |  |
| hard_event_count_126d | pure_t0 | 0.0000 | 66 | 0.0000 | 324 | 0.0000 | 0.0000 | 0.0000 | no |  |
| soft_event_count_126d | pure_t0 | 1.0000 | 66 | 1.0000 | 324 | 0.0000 | -1.0000 | 0.0000 | no |  |
| gap_pct | early_move | 5.0683 | 150 | 5.4079 | 773 | -0.3396 | -1.2572 | 1.1736 | no |  |

### Contrast: kept_going vs failed

| Feature | Tier | Rate A | n_A | Rate B | n_B | Diff | CI_lo | CI_hi | Bonf | Wilson_lo | Wilson_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| new_high_63d | pure_t0 | 100.0% | 150 | 100.0% | 313 | 0.0000 | 0.0000 | 0.0000 | no | -0.0250 | 0.0121 |  |
| liquid | pure_t0 | 100.0% | 150 | 100.0% | 313 | 0.0000 | 0.0000 | 0.0000 | no | -0.0250 | 0.0121 |  |
| self_funded_at_t0 | pure_t0 | 37.5% | 32 | 56.9% | 72 | -0.1944 | -0.4000 | 0.0062 | no | -0.4481 | 0.0930 |  |
| f4_composite | pure_t0 | 69.3% | 150 | 82.8% | 313 | -0.1341 | -0.2248 | -0.0484 | YES | -0.2498 | -0.0202 |  |
| trailing_rung_ge2 | pure_t0 | 20.9% | 129 | 28.7% | 261 | -0.0781 | -0.1640 | 0.0019 | no | -0.1970 | 0.0515 |  |
| soft_then_hard | pure_t0 | 38.1% | 42 | 30.8% | 104 | 0.0733 | -0.1150 | 0.2604 | no | -0.1519 | 0.3047 |  |
| f1_fwd_rung_ge2 | early_move | 27.3% | 66 | 16.3% | 147 | 0.1095 | 0.0146 | 0.2029 | YES | -0.0514 | 0.2782 |  |
| gap_hold_3 | early_move | 100.0% | 150 | 87.9% | 313 | 0.1214 | 0.0844 | 0.1642 | YES | 0.0648 | 0.1622 |  |
| gap_hold_5 | early_move | 100.0% | 150 | 85.9% | 313 | 0.1406 | 0.0989 | 0.1879 | YES | 0.0814 | 0.1835 |  |
| gap_hold_10 | early_move | 100.0% | 150 | 86.3% | 313 | 0.1374 | 0.0985 | 0.1818 | YES | 0.0786 | 0.1799 |  |
| f3_profit_stepup | pure_t0 | 29.0% | 31 | 26.0% | 73 | 0.0300 | -0.1806 | 0.2260 | no | -0.2101 | 0.2925 |  |

| Feature | Tier | Median A | n_A | Median B | n_B | Diff | CI_lo | CI_hi | Bonf | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| excess_21d_pp | pure_t0 | 22.6409 | 150 | 24.4684 | 313 | -1.8275 | -3.6722 | -0.1605 | YES |  |
| dollar_vol_z21 | pure_t0 | 2.0459 | 150 | 1.9925 | 313 | 0.0533 | -0.3671 | 0.6015 | no |  |
| dv_5_60_ratio | pure_t0 | 1.5561 | 150 | 1.6520 | 313 | -0.0959 | -0.2187 | 0.0374 | no |  |
| hard_event_count_126d | pure_t0 | 0.0000 | 66 | 0.0000 | 147 | 0.0000 | 0.0000 | 0.0000 | no |  |
| soft_event_count_126d | pure_t0 | 1.0000 | 66 | 1.0000 | 147 | 0.0000 | -1.0000 | 0.0000 | no |  |
| gap_pct | early_move | 5.0683 | 150 | 5.6974 | 313 | -0.6291 | -1.7025 | 1.2626 | no |  |

## Honesty strata

### Stratum 1: survivorship_biased == False

All 1,236 matured episodes have `survivorship_biased = False` in this census.
This stratum equals the full analysis population — no separate table needed.

### Stratum 2: gap_leg_crossed == False (primary contrast only)

Episodes with gap_leg_crossed==False: kept_going=114, blow_off=471
(excluded from primary contrast: kept_going=36, blow_off=302)

Binary features:

| Feature | Rate A | n_A | Rate B | n_B | Diff | CI_lo | CI_hi | Bonf |
|---|---|---|---|---|---|---|---|---|
| new_high_63d | 100.0% | 114 | 100.0% | 471 | 0.0000 | 0.0000 | 0.0000 | no |
| liquid | 100.0% | 114 | 100.0% | 471 | 0.0000 | 0.0000 | 0.0000 | no |
| self_funded_at_t0 | 21.1% | 19 | 50.0% | 48 | -0.2895 | — | — | — [DEGEN] |
| f4_composite | 68.4% | 114 | 52.6% | 471 | 0.1577 | 0.0514 | 0.2526 | YES |
| trailing_rung_ge2 | 19.4% | 93 | 22.1% | 308 | -0.0272 | -0.1468 | 0.0732 | no |
| soft_then_hard | 38.7% | 31 | 39.6% | 91 | -0.0085 | — | — | — [DEGEN] |
| f1_fwd_rung_ge2 | 31.2% | 48 | 19.1% | 157 | 0.1214 | -0.0179 | 0.2393 | no |
| gap_hold_3 | 100.0% | 114 | 66.0% | 471 | 0.3397 | 0.2919 | 0.3887 | YES |
| gap_hold_5 | 100.0% | 114 | 56.7% | 471 | 0.4331 | 0.3804 | 0.4925 | YES |
| gap_hold_10 | 100.0% | 114 | 41.8% | 471 | 0.5817 | 0.5307 | 0.6327 | YES |
| f3_profit_stepup | 26.9% | 26 | 26.1% | 92 | 0.0084 | -0.1847 | 0.1756 | no |

Continuous features:

| Feature | Median A | n_A | Median B | n_B | Diff | CI_lo | CI_hi | Bonf |
|---|---|---|---|---|---|---|---|---|
| excess_21d_pp | 22.6598 | 114 | 20.2446 | 471 | 2.4152 | 0.6853 | 4.2019 | YES |
| dollar_vol_z21 | 2.0459 | 114 | 1.9511 | 471 | 0.0948 | -0.2294 | 0.6316 | no |
| dv_5_60_ratio | 1.5323 | 114 | 1.5130 | 471 | 0.0194 | -0.0697 | 0.1533 | no |
| hard_event_count_126d | 0.0000 | 48 | 0.0000 | 157 | 0.0000 | 0.0000 | 0.0000 | no |
| soft_event_count_126d | 1.0000 | 48 | 1.0000 | 157 | 0.0000 | -1.0000 | 1.0000 | no |
| gap_pct | 4.9119 | 114 | 5.2853 | 471 | -0.3734 | -1.4353 | 1.3373 | no |

### Stratum 3: price_source mix per group

| Group | price_source | Count |
|---|---|---|
| kept_going | yahoo | 149 |
| kept_going | massive | 1 |
| blow_off | yahoo | 769 |
| blow_off | massive | 4 |
| failed | yahoo | 310 |
| failed | massive | 3 |

### Stratum 4: unmatured count

Unmatured episodes: 1,414 (not in any analysis group; forward windows not yet closed).

### Stratum 5: per-feature coverage

| Feature | Contrast | n_A_valid | n_B_valid |
|---|---|---|---|
| excess_21d_pp | kept_going vs blow_off | 150 | 773 |
| excess_21d_pp | kept_going vs failed | 150 | 313 |
| dollar_vol_z21 | kept_going vs blow_off | 150 | 773 |
| dollar_vol_z21 | kept_going vs failed | 150 | 313 |
| dv_5_60_ratio | kept_going vs blow_off | 150 | 773 |
| dv_5_60_ratio | kept_going vs failed | 150 | 313 |
| new_high_63d | kept_going vs blow_off | 150 | 773 |
| new_high_63d | kept_going vs failed | 150 | 313 |
| liquid | kept_going vs blow_off | 150 | 773 |
| liquid | kept_going vs failed | 150 | 313 |
| self_funded_at_t0 | kept_going vs blow_off | 32 | 150 |
| self_funded_at_t0 | kept_going vs failed | 32 | 72 |
| f4_composite | kept_going vs blow_off | 150 | 773 |
| f4_composite | kept_going vs failed | 150 | 313 |
| hard_event_count_126d | kept_going vs blow_off | 66 | 324 |
| hard_event_count_126d | kept_going vs failed | 66 | 147 |
| soft_event_count_126d | kept_going vs blow_off | 66 | 324 |
| soft_event_count_126d | kept_going vs failed | 66 | 147 |
| trailing_rung_ge2 | kept_going vs blow_off | 129 | 610 |
| trailing_rung_ge2 | kept_going vs failed | 129 | 261 |
| soft_then_hard | kept_going vs blow_off | 42 | 207 |
| soft_then_hard | kept_going vs failed | 42 | 104 |
| f1_fwd_rung_ge2 | kept_going vs blow_off | 66 | 324 |
| f1_fwd_rung_ge2 | kept_going vs failed | 66 | 147 |
| gap_pct | kept_going vs blow_off | 150 | 773 |
| gap_pct | kept_going vs failed | 150 | 313 |
| gap_hold_3 | kept_going vs blow_off | 150 | 773 |
| gap_hold_3 | kept_going vs failed | 150 | 313 |
| gap_hold_5 | kept_going vs blow_off | 150 | 773 |
| gap_hold_5 | kept_going vs failed | 150 | 313 |
| gap_hold_10 | kept_going vs blow_off | 150 | 773 |
| gap_hold_10 | kept_going vs failed | 150 | 313 |
| f3_profit_stepup | kept_going vs blow_off | 31 | 152 |
| f3_profit_stepup | kept_going vs failed | 31 | 73 |

**F3 coverage detail:**

- a2_firewall_excluded: 426
- ticker_not_in_statements: 393
- ok: 256
- insufficient_pit_rows: 138
- null_financials: 23
- kept_going ok: 31 of 150 (20.7%)
- blow_off ok: 152 of 773 (19.7%)

**NON-COMPARABLE flag:** Coverage < 30% in at least one primary contrast group.
F3 results are printed but must not be interpreted as representative of the full groups.

## Honest read (nulls printed)

F1 trailing (t0-126d→t0 rung count ≥ 2): CI contains 0 (no detectable difference)
F1 early-move (t0→t0+21td rung count ≥ 2): CI contains 0 (no detectable difference)
F2 gap_hold_3: CI excludes 0 (higher in kept_going; survives Bonferroni)
F2 gap_hold_5: CI excludes 0 (higher in kept_going; survives Bonferroni)
F2 gap_hold_10: CI excludes 0 (higher in kept_going; survives Bonferroni)
F3 profit step-up: NON-COMPARABLE (coverage < 30%) — result printed in table but cannot be interpreted
F4 composite (new_high_63d AND excess_21d≥20pp): CI excludes 0 (higher in kept_going; survives Bonferroni)
F5 proxy (excess_21d_pp, continuous): CI excludes 0 (higher in kept_going; survives Bonferroni)
F6 compressed prior: STRUCTURALLY BLOCKED — no PIT short-interest / options / consensus-dispersion
history in-repo for the census era (WA deferral, L10-aligned). One paragraph: the W2 report
identified 'compressed prior' (the market was actively doubting something) as appearing 11/11
in the hand-selected cases. Testing this at census scale requires a machinable proxy — short
interest percentile, consensus-target-vs-spot gap, or analyst-dispersion — none of which are
available in-repo with PIT coverage for the 1997–2026 episode window. Per spec §3-F6 and the
WA masterplan §1 adjudication table, this column is structurally blocked and not proxied.

## Explicit verdict per W2 §4 candidate

Per spec §6: explicit CONFIRMED / REFUTED / UNTESTABLE line for each candidate.
CONFIRMED = CI excludes zero in the predicted direction, survives Bonferroni.
REFUTED = CI excludes zero in the OPPOSITE direction, or CI contains zero with adequate coverage.
UNTESTABLE = insufficient coverage, structurally blocked, or A2 firewall.

| W2 candidate | Spec prediction | Primary result | Verdict |
|---|---|---|---|
| F1 — trailing pre-onset rung count ≥2 | Higher in kept_going | : CI contains 0 (no detectable difference) | REFUTED (CI contains 0 — no detectable difference) |
| F1 — early-move conditioner rung ≥2 (t0+21td) | Higher in kept_going | : CI contains 0 (no detectable difference) | REFUTED (CI contains 0 — no detectable difference) |
| F2 — gap holds 3 sessions | Higher in kept_going | : CI excludes 0 (higher in kept_going; survives Bonferroni) | CONFIRMED (CI excludes 0, Bonferroni survives) |
| F2 — gap holds 5 sessions | Higher in kept_going | : CI excludes 0 (higher in kept_going; survives Bonferroni) | CONFIRMED (CI excludes 0, Bonferroni survives) |
| F2 — gap holds 10 sessions | Higher in kept_going | : CI excludes 0 (higher in kept_going; survives Bonferroni) | CONFIRMED (CI excludes 0, Bonferroni survives) |
| F3 — profit step-up faster than revenue | Higher in kept_going (fundamental subgroup) | NON-COMPARABLE if flagged | UNTESTABLE (NON-COMPARABLE — coverage < 30%) |
| F4 — new 63d high AND excess_21d≥20pp | W2 predicted: likely non-discriminating at t0 | : CI excludes 0 (higher in kept_going; survives Bonferroni) | CONFIRMED (CI excludes 0, Bonferroni survives) |
| F5 — sector beta ruled out / idiosyncratic excess | W2 predicted: non-discriminating (both groups defined on excess) | : CI excludes 0 (higher in kept_going; survives Bonferroni) | CONFIRMED (CI excludes 0, Bonferroni survives) |
| F6 — compressed prior | Predicted: testable only with PIT short-interest proxy | N/A — structurally blocked | UNTESTABLE |

## Adjudication (WA-R8, main loop)

PENDING
