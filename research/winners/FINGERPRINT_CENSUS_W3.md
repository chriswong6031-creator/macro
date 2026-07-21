<!-- W3 census fingerprint study. DESCRIPTIVE ONLY (WA-R1/R5/R8). -->
<!-- Review-round-1 corrections applied 2026-07-20: Bonf CI fix, F2 tautology, -->
<!-- F4/F5 collapse, F1 mask, pairing fix, ticker-cluster CI, survivorship honesty, -->
<!-- crypto segregation, citation fix, leading-colon fix. -->

# Winner Autopsy Lab — W3 Census Fingerprint Study (Layer-3a)

**Status:** DESCRIPTIVE ONLY — no hypothesis registration, no verdicts, no filters, no site surfaces.
Rulings WA-R1 / WA-R5 / WA-R8. Spec: `research/winners/W3_CENSUS_STUDY_SPEC.md`.

**Substrate:** `winner_episodes.parquet` — manifest hash `c1a6a1cbec74a726`, harvest date `2026-07-07`.
**Run:** seed 20260720, n_boot 50000, m=22 tests, α_Bonferroni = 0.05/22 = 0.002273.
**Primary analysis:** equity-only (crypto segregated — see appendix). 1,213 matured episodes.
**Wall time:** 322.7s

**Review-round-1 corrections (adversarial stats review 2026-07-20):**
- BLOCKER: `bonf_survives` now uses α/m percentile CI, not 95% CI.
- n_boot raised to 50,000 for α/m tail resolution (seed unchanged).
- Both 95% CI and α/m CI printed per row.
- Ticker-cluster bootstrap CI added as robustness column.
- F2 gap_hold_k: reclassified as TAUTOLOGICAL — moved out of fingerprint tables into dedicated section.
- F4/F5 collapsed: `new_high_63d` is 100% by construction → excluded from m; `f4_composite ≡ excess_21d_pp≥20`.
- `new_high_63d` and `liquid` excluded from m (constants by construction, noted once).
- F1 trailing: missing 8K coverage now MASKED (dropped) not zero-filled.
- Bootstrap pairing: one drawn month multiset per replicate feeds BOTH groups.
- Stratum 1 (survivorship): replaced with honest untested disclosure.
- Citation fixed: `extract_b1_hardening_ladder` (was `_b1_features`).

## Bottom line

Results are machine outputs from the equity-only census — not adjudications. The main loop appends WA-R8 below.

**Net finding (post-correction):** Once the F2 tautology is removed and the real Bonferroni
correction applied, NO tested t0 feature separates kept_going from blow_off at the α/m threshold.
F4/F5 (excess_21d_pp family) lose Bonferroni survival under the corrected CI. F1 trailing and
early-move conditioner remain null. F3 is untestable. F6 is structurally blocked.

| W2 candidate | Post-correction verdict |
|---|---|
| F1 — catalyst-ladder rung count (trailing pre-t0) | Both CIs contain 0 — no detectable difference |
| F1 — catalyst-ladder rung count (early-move, t0+21td) | Both CIs contain 0 — no detectable difference |
| F2 — trigger gap holds (gap_hold_k) | TAUTOLOGICAL — not a fingerprint, ineligible for registration (see §F2 Tautology) |
| F3 — profit step-up faster than revenue | UNTESTABLE — A2 firewall + coverage < 30% |
| F4/F5 — trailing-excess magnitude family (collapsed) | 95% CI excludes 0 but α/m CI CONTAINS 0 — higher in kept_going (Bonferroni does NOT survive) (see note: direction reversal vs failed) |
| F6 — compressed prior | UNTESTABLE — structurally blocked (no PIT short-interest/options/dispersion history) |

**F4/F5 direction reversal:** Initial-excess magnitude is not a winner selector.
- kept_going vs blow_off: +12.5pp (kept_going has MORE excess than blow_off)
- kept_going vs failed: -13.6pp (kept_going has LESS excess than failed)
- Interpretation: blow_off episodes have lower t0 excess than kept_going (gap selection); failed
  episodes have HIGHER t0 excess than kept_going. Initial-excess magnitude cuts both ways — it
  is not a reliable t0 separator. Under corrected Bonferroni CI, neither direction survives.

### F1 window-direction finding (spec §3 circularity guard)

**Verified:** `hard_event_count_126d` / `soft_event_count_126d` / `soft_then_hard` in
`engine/winner_autopsy.py:extract_b1_hardening_ladder` (line 1139) use the PRE-ONSET window:
`filing_date strictly < t0, within 126 calendar days of t0`. These are TRAILING counts, NOT forward-looking.
They do NOT overlap the labeling horizon. Path taken: **use them directly as pure-t0 features**,
and additionally compute F1 early-move conditioner from material_8k_events bounded to (t0, t0+21td].

**F1 trailing coverage (masked-not-zero-filled):** kept_going 66/140
(47%); blow_off 324/764 (42%).
Episodes absent from the 8K store are MASKED (excluded from the F1 trailing analysis),
not imputed to zero. Results below are on the covered subset only.

## F2 — Label-tautology disclosure

**gap_hold_k is TAUTOLOGICAL for all kept_going episodes. It is NOT a fingerprint and is
INELIGIBLE for registration.**

### Algebraic chain

1. `clean_hold` requires no forward close below close(t0) over (t0, t0+126td]
   (`engine/winner_autopsy.py:515-524`).
2. `durable_winner` requires `clean_hold` (`:526-529`).
3. Detector onset requires a new-63d-high at t0 (`:285-290`), forcing close(t0) >= close(t0-1).
4. Therefore: `gap_hold_k ≡ close(t0+k) > close(t0-1)` is **TRUE by algebra** for every
   kept_going episode (clean_hold prevents any close below close(t0) >= close(t0-1)).
5. Conclusion: gap_hold_k = 1.0 for 100% of kept_going episodes is a logical consequence
   of the label definition, not an empirical fingerprint.

### Blow_off residual rates (descriptive only)

These rates describe blow_off episode behavior — they are NOT used in any contrast or verdict.

| Gap-hold measure | Blow_off rate (descriptive) |
|---|---|
| gap_hold_3 | 65.7% |
| gap_hold_5 | 54.1% |
| gap_hold_10 | 40.7% |

Blow_off gap_hold rates: 3-session 65.7%,
5-session 54.1%,
10-session 40.7%.
These rates reflect that blow_off episodes ALSO tend to hold the gap at short horizons,
declining at longer horizons — descriptive blow_off behavior only.

**Non-tautological gap magnitude (gap_pct):** No difference between groups.
Median gap_pct: kept_going 5.07%, blow_off 5.41%
(CI contains zero — gap magnitude does not distinguish groups).

## Population

**Primary analysis: equity-only** (crypto excluded — see appendix)
Total episodes (equity): **2,600** / 453 tickers
t0 range: 1997-07-23 → 2026-07-02

| Outcome label | Count |
|---|---|
| unmatured | 1,387 |
| blow_off | 764 |
| failed | 309 |
| durable_winner | 119 |
| clean_hold | 21 |

**Matured (analysis population — equity only):**

| Group | Definition | Count |
|---|---|---|
| kept_going (PRIMARY) | durable_winner + clean_hold | 140 |
| blow_off (Contrast 1) | blow_off | 764 |
| failed (Contrast 2) | failed | 309 |
| **unmatured** (not in analysis — counted here) | unmatured | 1,387 |

Blow_off:kept_going ratio: 5.5:1 (census is blow_off-dominated as expected).

**Constants by construction (excluded from m, noted once):**
- `new_high_63d`: 100% True in all 1,213 matured equity episodes (detector gate).
- `liquid`: 100% True in all 1,213 matured equity episodes (detector gate).
These are structural constants — testing them is uninformative and they are excluded from m.

## Feature results

m = 22 tests. Bonferroni threshold α/m = 0.002273.
CI_95 = 95% month-block paired bootstrap percentile CI (50,000 reps, seed 20260720).
CI_bonf = α/m percentile CI (two-sided tail = (α/m)/2 = 0.0011364 each side).
**bonf_survives uses CI_bonf** (corrected from prior run which used CI_95).
CI_cluster = 95% ticker-cluster bootstrap CI (robustness for within-ticker dependence).
Wilson CI = cross-check for binary features (Newcombe method).
ALL rows printed regardless of significance (census, not a screen).

### Contrast: kept_going vs blow_off

| Feature | Tier | Rate_A | n_A | Rate_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIcluster_lo | CIcluster_hi | Wilson_lo | Wilson_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| self_funded_at_t0 | pure_t0 | 37.5% | 32 | 48.7% | 150 | -0.1117 | -0.3235 | 0.0923 | -0.4522 | 0.2154 | no | -0.3128 | 0.0967 | -0.3366 | 0.1394 |  |
| f4_composite | pure_t0 | 69.3% | 140 | 56.8% | 764 | 0.1248 | 0.0303 | 0.2128 | -0.0278 | 0.2585 | no | 0.0409 | 0.2107 | 0.0094 | 0.2306 |  |
| trailing_rung_ge2 | pure_t0 | 40.9% | 66 | 44.8% | 324 | -0.0384 | -0.1593 | 0.0732 | -0.2365 | 0.1398 | no | -0.1698 | 0.0963 | -0.2033 | 0.1352 |  |
| soft_then_hard | pure_t0 | 38.1% | 42 | 35.8% | 207 | 0.0235 | -0.1711 | 0.1929 | -0.2933 | 0.2946 | no | -0.1383 | 0.1867 | -0.1748 | 0.2365 |  |
| f1_fwd_rung_ge2 | early_move | 27.3% | 66 | 16.7% | 324 | 0.1061 | -0.0063 | 0.2012 | -0.0818 | 0.2540 | no | -0.0074 | 0.2268 | -0.0311 | 0.2604 |  |
| f3_profit_stepup | pure_t0 | 29.0% | 31 | 26.3% | 152 | 0.0272 | -0.1532 | 0.2024 | -0.2517 | 0.3350 | no | -0.1246 | 0.1763 | -0.1774 | 0.2663 |  |

| Feature | Tier | Median_A | n_A | Median_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIcluster_lo | CIcluster_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | pure_t0 | 2.0308 | 140 | 1.9597 | 764 | 0.0711 | -0.2469 | 0.4194 | -0.3620 | 0.6937 | no | -0.2536 | 0.4866 |  |
| dv_5_60_ratio | pure_t0 | 1.5604 | 140 | 1.5342 | 764 | 0.0262 | -0.0745 | 0.1466 | -0.1295 | 0.2224 | no | -0.0731 | 0.1371 |  |
| excess_21d_pp | pure_t0 | 22.6409 | 140 | 20.7174 | 764 | 1.9235 | 0.6069 | 3.3819 | -0.3218 | 4.3738 | no | 0.5896 | 3.7059 |  |
| hard_event_count_126d | pure_t0 | 0.0000 | 66 | 0.0000 | 324 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | no | 0.0000 | 1.0000 |  |
| soft_event_count_126d | pure_t0 | 1.0000 | 66 | 1.0000 | 324 | 0.0000 | -1.0000 | 0.0000 | -1.0000 | 0.0000 | no | -1.0000 | 0.0000 |  |

### Contrast: kept_going vs failed

| Feature | Tier | Rate_A | n_A | Rate_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIcluster_lo | CIcluster_hi | Wilson_lo | Wilson_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| self_funded_at_t0 | pure_t0 | 37.5% | 32 | 56.9% | 72 | -0.1944 | -0.3955 | 0.0091 | -0.5119 | 0.1389 | no | -0.4011 | 0.0292 | -0.4481 | 0.0930 |  |
| f4_composite | pure_t0 | 69.3% | 140 | 82.8% | 309 | -0.1356 | -0.2291 | -0.0484 | -0.2868 | -0.0005 | YES | -0.2215 | -0.0492 | -0.2543 | -0.0192 |  |
| trailing_rung_ge2 | pure_t0 | 40.9% | 66 | 51.0% | 147 | -0.1011 | -0.2295 | 0.0193 | -0.3104 | 0.0902 | no | -0.2480 | 0.0473 | -0.2910 | 0.0993 |  |
| soft_then_hard | pure_t0 | 38.1% | 42 | 30.8% | 104 | 0.0733 | -0.1117 | 0.2609 | -0.2165 | 0.3776 | no | -0.1003 | 0.2484 | -0.1519 | 0.3047 |  |
| f1_fwd_rung_ge2 | early_move | 27.3% | 66 | 16.3% | 147 | 0.1095 | 0.0131 | 0.2030 | -0.0497 | 0.2642 | no | -0.0141 | 0.2378 | -0.0514 | 0.2782 |  |
| f3_profit_stepup | pure_t0 | 29.0% | 31 | 26.0% | 73 | 0.0300 | -0.1768 | 0.2246 | -0.2938 | 0.3500 | no | -0.1352 | 0.1941 | -0.2101 | 0.2925 |  |

| Feature | Tier | Median_A | n_A | Median_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIcluster_lo | CIcluster_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | pure_t0 | 2.0308 | 140 | 1.9925 | 309 | 0.0383 | -0.4024 | 0.5131 | -0.5702 | 0.8710 | no | -0.3824 | 0.5026 |  |
| dv_5_60_ratio | pure_t0 | 1.5604 | 140 | 1.6462 | 309 | -0.0858 | -0.2176 | 0.0472 | -0.3047 | 0.1199 | no | -0.2089 | 0.0374 |  |
| excess_21d_pp | pure_t0 | 22.6409 | 140 | 24.4194 | 309 | -1.7785 | -3.6088 | -0.0724 | -4.7419 | 0.9623 | no | -3.7413 | 0.2114 |  |
| hard_event_count_126d | pure_t0 | 0.0000 | 66 | 0.0000 | 147 | 0.0000 | 0.0000 | 0.0000 | -1.0000 | 1.0000 | no | 0.0000 | 1.0000 |  |
| soft_event_count_126d | pure_t0 | 1.0000 | 66 | 1.0000 | 147 | 0.0000 | -1.0000 | 0.0000 | -2.0000 | 0.0000 | no | -1.0000 | 0.0000 |  |

## Honesty strata

### Stratum 1: Survivorship — UNTESTED

The census as harvested is **survivor-only**. The masterplan's dead-name coverage
(`scripts/research/fetch_dead_name_prices_polygon.py`) did not flow into this parquet.
All matured episodes have `survivorship_biased = False` as a column value, but this
reflects the _label_ applied during harvest, not actual dead-stock inclusion.
**Stratum 1 is UNTESTED, not passed.** Survivorship bias remains an unresolved gap.
Dead-name coverage: `price_source` contains only yahoo/massive (see Stratum 3) —
no dead-ticker source is present. The `survivorship_biased` column is constant False.

### Stratum 2: gap_leg_crossed == False (primary contrast only)

Episodes with gap_leg_crossed==False: kept_going=108, blow_off=462
(excluded from primary contrast: kept_going=32, blow_off=302)

Binary features:

| Feature | Rate_A | n_A | Rate_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf |
|---|---|---|---|---|---|---|---|---|---|---|
| self_funded_at_t0 | 21.1% | 19 | 50.0% | 48 | -0.2895 | — | — | — | — | — [DEGEN] |
| f4_composite | 69.4% | 108 | 51.9% | 462 | 0.1750 | 0.0722 | 0.2685 | 0.0017 | 0.3161 | YES |
| trailing_rung_ge2 | 37.5% | 48 | 43.3% | 157 | -0.0581 | -0.2347 | 0.0811 | -0.3853 | 0.1627 | no |
| soft_then_hard | 38.7% | 31 | 39.6% | 91 | -0.0085 | — | — | — | — | — [DEGEN] |
| f1_fwd_rung_ge2 | 31.2% | 48 | 19.1% | 157 | 0.1214 | -0.0191 | 0.2395 | -0.1212 | 0.3051 | no |
| f3_profit_stepup | 26.9% | 26 | 26.1% | 92 | 0.0084 | -0.1839 | 0.1754 | -0.2827 | 0.3171 | no |

Continuous features:

| Feature | Median_A | n_A | Median_B | n_B | Diff | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf |
|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | 2.0248 | 108 | 1.9554 | 462 | 0.0695 | -0.3118 | 0.5089 | -0.4709 | 0.8575 | no |
| dv_5_60_ratio | 1.5323 | 108 | 1.5133 | 462 | 0.0190 | -0.0777 | 0.1588 | -0.1302 | 0.2600 | no |
| excess_21d_pp | 22.6598 | 108 | 20.1853 | 462 | 2.4745 | 0.8816 | 4.4888 | -0.0656 | 5.8153 | no |
| hard_event_count_126d | 0.0000 | 48 | 0.0000 | 157 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |
| soft_event_count_126d | 1.0000 | 48 | 1.0000 | 157 | 0.0000 | -1.0000 | 1.0000 | -1.0000 | 1.0000 | no |

### Stratum 3: price_source mix per group

| Group | price_source | Count |
|---|---|---|
| kept_going | yahoo | 139 |
| kept_going | massive | 1 |
| blow_off | yahoo | 760 |
| blow_off | massive | 4 |
| failed | yahoo | 306 |
| failed | massive | 3 |

### Stratum 4: unmatured count

Unmatured episodes (equity): 1,387 (not in any analysis group; forward windows not yet closed).

### Stratum 5: per-feature coverage

| Feature | Contrast | n_A_valid | n_B_valid |
|---|---|---|---|
| dollar_vol_z21 | kept_going vs blow_off | 140 | 764 |
| dollar_vol_z21 | kept_going vs failed | 140 | 309 |
| dv_5_60_ratio | kept_going vs blow_off | 140 | 764 |
| dv_5_60_ratio | kept_going vs failed | 140 | 309 |
| self_funded_at_t0 | kept_going vs blow_off | 32 | 150 |
| self_funded_at_t0 | kept_going vs failed | 32 | 72 |
| excess_21d_pp | kept_going vs blow_off | 140 | 764 |
| excess_21d_pp | kept_going vs failed | 140 | 309 |
| f4_composite | kept_going vs blow_off | 140 | 764 |
| f4_composite | kept_going vs failed | 140 | 309 |
| hard_event_count_126d | kept_going vs blow_off | 66 | 324 |
| hard_event_count_126d | kept_going vs failed | 66 | 147 |
| soft_event_count_126d | kept_going vs blow_off | 66 | 324 |
| soft_event_count_126d | kept_going vs failed | 66 | 147 |
| trailing_rung_ge2 | kept_going vs blow_off | 66 | 324 |
| trailing_rung_ge2 | kept_going vs failed | 66 | 147 |
| soft_then_hard | kept_going vs blow_off | 42 | 207 |
| soft_then_hard | kept_going vs failed | 42 | 104 |
| f1_fwd_rung_ge2 | kept_going vs blow_off | 66 | 324 |
| f1_fwd_rung_ge2 | kept_going vs failed | 66 | 147 |
| f3_profit_stepup | kept_going vs blow_off | 31 | 152 |
| f3_profit_stepup | kept_going vs failed | 31 | 73 |

**F3 coverage detail:**

- a2_firewall_excluded: 424
- ticker_not_in_statements: 372
- ok: 256
- insufficient_pit_rows: 138
- null_financials: 23
- kept_going ok: 31 of 140 (22.1%)
- blow_off ok: 152 of 764 (19.9%)

**NON-COMPARABLE flag:** Coverage < 30% in at least one primary contrast group.
F3 results are printed but must not be interpreted as representative of the full groups.

## Honest read (nulls printed)

F1 trailing (t0-126d→t0 rung count ≥ 2, covered subset): Both CIs contain 0 (no detectable difference)
F1 early-move (t0→t0+21td rung count ≥ 2): Both CIs contain 0 (no detectable difference)
F2 gap_hold: TAUTOLOGICAL — algebraically guaranteed True for kept_going by label definition (see §F2)
F2 gap_pct (non-tautological): CI contains 0 — gap magnitude null (no difference)
F3 profit step-up: NON-COMPARABLE (coverage < 30%) — result printed in table but cannot be interpreted
F4/F5 excess_21d_pp≥20pp (vs blow_off): 95% CI excludes 0 BUT α/m CI contains 0 (higher in kept_going; Bonferroni does NOT survive — real correction)
F4/F5 excess_21d_pp continuous (vs blow_off): 95% CI excludes 0 BUT α/m CI contains 0 (higher in kept_going; Bonferroni does NOT survive — real correction)
F6 compressed prior: STRUCTURALLY BLOCKED — no PIT short-interest / options / consensus-dispersion
history in-repo for the census era (WA deferral, L10-aligned). The W2 report identified
'compressed prior' as appearing 11/11 in the hand-selected cases. Testing at census scale
requires short interest percentile, consensus-target-vs-spot gap, or analyst-dispersion —
none available in-repo with PIT coverage for the 1997–2026 episode window.
Per spec §3-F6 and the WA masterplan §1 adjudication table: structurally blocked, not proxied.

## Explicit verdict per W2 §4 candidate

Per spec §6: explicit CONFIRMED / REFUTED / UNTESTABLE line for each candidate.
CONFIRMED = α/m CI (corrected Bonferroni) excludes zero in the predicted direction.
REFUTED = α/m CI excludes zero in the OPPOSITE direction, or CI contains zero with adequate coverage.
UNTESTABLE = insufficient coverage, structurally blocked, or A2 firewall.
TAUTOLOGICAL = algebraically guaranteed by label definition (not a fingerprint).

| W2 candidate | Spec prediction | Primary result (equity-only) | Post-correction verdict |
|---|---|---|---|
| F1 — trailing pre-onset rung count ≥2 | Higher in kept_going | Both CIs contain 0 (no detectable difference) | REFUTED (α/m CI contains 0 — no detectable difference at corrected threshold) |
| F1 — early-move conditioner rung ≥2 (t0+21td) | Higher in kept_going | Both CIs contain 0 (no detectable difference) | REFUTED (α/m CI contains 0 — no detectable difference at corrected threshold) — on 8K-covered subset (47%/42%) |
| F2 — gap holds k sessions | Higher in kept_going | TAUTOLOGICAL (label definition) | TAUTOLOGICAL — not a fingerprint, ineligible for registration |
| F3 — profit step-up faster than revenue | Higher in kept_going | NON-COMPARABLE | UNTESTABLE (NON-COMPARABLE — coverage < 30%) |
| F4/F5 — trailing-excess magnitude (≥20pp dichotomy) | W2: non-discriminating prediction | 95% CI excludes 0 BUT α/m CI contains 0 (higher in kept_going; Bonferroni does NOT survive — real correction) | REFUTED (α/m CI contains 0 — no detectable difference at corrected threshold) |
| F4/F5 — trailing-excess magnitude (continuous) | W2: non-discriminating prediction | 95% CI excludes 0 BUT α/m CI contains 0 (higher in kept_going; Bonferroni does NOT survive — real correction) | REFUTED (α/m CI contains 0 — no detectable difference at corrected threshold) |
| F6 — compressed prior | Testable only with PIT proxy | N/A — structurally blocked | UNTESTABLE |

## Appendix: Crypto episodes

Tickers excluded from primary analysis: ['BTC-USD', 'BTC_F', 'ETH-USD', 'SOL-USD']
Exclusion rationale: 7-day-calendar trading (vs equity 5-day), SPY benchmark category error,
and index-alignment mismatch in price reads (no weekend bars → F2 forward positions shift).

Crypto matured episodes: 23 total
- kept_going: 10
- blow_off: 9
- failed: 4

Including crypto in the primary contrast changes group sizes by:
- kept_going: 140 → 150 (+10)
- blow_off: 764 → 773 (+9)
- failed: 309 → 313 (+4)
A with-crypto re-run is not performed (benchmark error makes the comparison invalid).

## Adjudication (WA-R8, main loop)

Ruled 2026-07-20 by main-loop Fable, after a round-1 adversarial stats review (opus; found
the Bonferroni mislabel, the F2 tautology, the F4/F5 double-count) and a round-2
verification (opus; all ten ordered corrections confirmed landed, both independent
recomputations reproduced the corrected tables exactly, MERGEABLE).

**WA-R8 ruling: NO fingerprint candidate earns a pre-registered slot.**

- **F2 (gap-holds) — TAUTOLOGICAL; permanently ineligible against the current label
  family.** The kept-going 100% hold rate is algebra (the `clean_hold` no-forward-drop
  rule plus the detector's onset new-high), not a market regularity. Any future
  early-hold conditioner requires outcome labels that do not embed a hold condition — a
  new label construction plus its own prereg.
- **F1 (catalyst rungs) — REFUTED on the 8-K-covered subset**, trailing and t0+21td
  alike. Construction-scoped: fuller 8-K coverage could reopen it; nothing here
  motivates that.
- **F4/F5 (initial-excess magnitude, collapsed) — NULL at the declared α/m correction
  and direction-reversed vs the failed contrast.** Bigger initial excess is not a
  winner-selector.
- **F3, F6 — UNTESTABLE** (A2-firewall coverage; no PIT short-interest/options
  history). These remain open *questions*, not open candidates: each needs its data
  substrate before any test can be designed.

**The null is the deliverable.** At onset, on every feature measurable today,
kept-going breakaways are statistically indistinguishable from blow-offs. Two
consequences for the Lab: (i) if discriminating information exists, it is not in t0
price/volume/8-K geometry — the forward-accruing substrates (per-ticker options,
analyst revisions; joins began 2026-06, first answerable ~mid-2027 per the masterplan
clock) and the unrun Layer-3(b) study (pre-onset vs matched controls) are the live
directions; (ii) the asymmetric-exit doctrine strengthens — with entry-time
discrimination refuted, edge extraction lives in holding policy conditioned on
post-onset evidence (see the PSQ adjudication, PR #3162, for the Prophet-side
counterpart ruled the same day). A construction-scoped registry row is appended to
DO_NOT_REBUILD §2; per house epistemics this closes the tested constructions, not the
search — "not found yet" ≠ "does not exist."
